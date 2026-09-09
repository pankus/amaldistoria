"""Import periodico degli iscritti e geocodifica degli indirizzi a livello di via.

Quattro comandi, da lanciare in quest'ordine la prima volta:

    flask stradario-sync                       # elenco vie reali da OpenStreetMap
    flask strade-cleanup                       # pulizia privacy e duplicati sullo storico
    flask import-alunni data/<file>.xls        # una annata per volta
    flask geocode --anno 2024-2025             # collega gli alunni alle vie

La geocodifica procede a stadi, dal piu' economico al piu' costoso:

    0. NORMALIZZA   token, abbreviazioni, apostrofi, rimozione civico    (locale)
    1. STRADARIO    espandi 'G.' -> 'GIUSEPPE' contro le vie reali       (locale)
    2. RIUSO        (via canonica, CAP) gia' in `strada`? -> collega     (locale)
    3. NOMINATIM    solo per le coppie nuove, con la via gia' pulita     (rete)
    4. CODA         cio' che resta -> CSV di revisione, mai indovinato

Vincolo di dominio: si geocodifica **solo il nome della via**, mai il civico.
La residenza degli studenti deve restare irrintracciabile sulle mappe pubbliche.
"""

import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import subprocess
from collections import Counter, defaultdict, namedtuple
from datetime import datetime

import click
from flask.cli import with_appcontext
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import text

from app import toponimi
from app.extensions import db
from app.models import Alunno, Strada, Stradario

UA = 'amaldistoria-import/1.0 (Centro di Documentazione Liceo Amaldi, Roma)'
PAUSA_NOMINATIM = 1.1          # la policy d'uso chiede al massimo 1 richiesta/secondo

# data/ e' divisa per natura del contenuto, non per comando che la produce:
#   input/  i file .xls consegnati dalla segreteria, uno per anno scolastico
#   geo/    le sorgenti geografiche scaricate (Geofabrik, ISTAT) e i loro estratti
#   esiti/  cio' che i comandi producono: log, correzioni, code di revisione
CARTELLA_DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
DATI_INPUT = os.path.join(CARTELLA_DATI, 'input')
DATI_GEO = os.path.join(CARTELLA_DATI, 'geo')
DATI_ESITI = os.path.join(CARTELLA_DATI, 'esiti')
CACHE = DATI_GEO

# Lo stradario si costruisce da due scaricamenti interi, non da un'API a query.
# Overpass accoda le richieste pesanti e arriva a rifiutare l'IP a meta' lavoro:
# e' successo, con la perdita di Roma (il 97% degli indirizzi). Questi due file
# si scaricano una volta sola, non hanno limiti di frequenza e danno sempre lo
# stesso risultato.
GEOFABRIK = 'https://download.geofabrik.de/europe/italy/centro-latest-free.shp.zip'
GEOFABRIK_STRADE = 'gis_osm_roads_free_1'
ISTAT = ('https://www.istat.it/storage/cartografia/confini_amministrativi/'
         'generalizzati/2024/Limiti01012024_g.zip')
ISTAT_COMUNI = 'Com01012024_g_WGS84'

# Colonne dell'export Spaggiari/Infoschool -> colonne di `alunni`.
# Restano deliberatamente fuori: Seconda Cittadinanza, Cod Alunno Sidi
# (identificativo nazionale dello studente), Frazione Residenza, Convittore,
# Obbligo Formativo, Tempo Scuola, Codice Fiscale Scuola, Fratello Minore.
MAPPA = {
    'Id Alunno': 'id_alunno',
    'Sesso': 'sesso',
    'Luogo Nascita': 'luogo_nascita',
    'Provincia Nascita': 'provincia_nascita',
    'Stato Nascita': 'stato_nascita',
    'Descr Cittadinanza': 'descr_cittadinanza',
    'Matricola': 'matricola',
    'Comune Residenza': 'comune_residenza',
    'Provincia Residenza': 'provincia_residenza',
    'Indirizzo Residenza': 'indirizzo_residenza',
    'Cap Residenza': 'cap_residenza',
    'Stato Alunno': 'stato_alunno',
    'Tipologia Stato Alunno': 'tipologia_stato_alunno',
    'Data Inizio': 'data_inizio',
    'Data Fine': 'data_fine',
    'Numero Volte Iscrizione': 'numero_volte_iscrizione',
    'Fornito Di': 'fornito_di',
    'Scuola Provenienza': 'scuola_provenienza',
    'Poszione': 'posizione',                 # il refuso e' nell'export, non nostro
    'Religione Cattolica': 'religione_cattolica',
    'Attivita Alternativa': 'attivita_alternativa',
    'Educazione Fisica': 'educazione_fisica',
    'Esito Finale': 'esito_finale',
    'Esito Sospeso': 'esito_sospeso',
    'Media Voti': 'media_voti',
    'Scuola Trasferimento': 'scuola_trasferimento',
    'Punteggio Esame Stato': 'punteggio_esame',
    'Anno Corso': 'anno_corso',
    'Anno Sigla': 'anno_sigla',
    'Sezione': 'sezione',
    'Classe': 'classe',
    'Indirizzo Studi': 'indirizzo_studi',
    'Classificazione Ministeriale': 'classificazione_ministeriale',
    'Indirizzo Ministeriale': 'indirizzo_ministeriale',
    'Sede': 'sede',
    'Scuola': 'scuola',
    'Cod Meccanografico': 'cod_meccanografico',
    'Piano Studio': 'piano_studio',
}

INTERI = {'id_alunno', 'numero_volte_iscrizione', 'anno_corso', 'anno_sigla'}
DATE = {'data_inizio', 'data_fine'}
DECIMALI = {'media_voti'}
LUNGHEZZA_MAX = 128


# ---------------------------------------------------------------------------
# Utilita'
# ---------------------------------------------------------------------------

def _percorso_dati(nome):
    """Dove va un file prodotto da un comando: sempre in data/esiti/."""
    os.makedirs(DATI_ESITI, exist_ok=True)
    return os.path.join(DATI_ESITI, nome)


def _scrivi_csv(nome, intestazione, righe):
    percorso = _percorso_dati(nome)
    with open(percorso, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(intestazione)
        w.writerows(righe)
    return percorso


SENTINELLE = {'', 'empty', 'none', 'null', 'nan', '-'}


def _utile(valore):
    """Scarta i valori che in questo DB fanno da segnaposto di "vuoto".

    Vecchi import hanno lasciato la stringa letterale 'empty' in osm_city e
    osm_house_number: passata a Nominatim manda a vuoto la query strutturata.
    """
    if valore is None:
        return None
    v = str(valore).strip()
    return None if v.lower() in SENTINELLE else v


def _scarica(url, nome, riscarica=False):
    """Scarica in cache, saltando il lavoro se il file c'e' gia'."""
    os.makedirs(CACHE, exist_ok=True)
    dest = os.path.join(CACHE, nome)
    if os.path.exists(dest) and not riscarica:
        click.echo(f"  {nome}: gia' in cache ({os.path.getsize(dest) / 1e6:.0f} MB)")
        return dest
    click.echo(f'  {nome}: scarico da {url.split("/")[2]}...')
    # Si scarica su un file provvisorio e si rinomina solo alla fine: un
    # download interrotto non deve lasciare in cache un file parziale che il
    # lancio successivo scambierebbe per buono.
    parziale = dest + '.parziale'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r, open(parziale, 'wb') as f:
            atteso = int(r.headers.get('Content-Length') or 0)
            while True:
                pezzo = r.read(1 << 20)
                if not pezzo:
                    break
                f.write(pezzo)
        scaricato = os.path.getsize(parziale)
        if atteso and scaricato != atteso:
            raise click.ClickException(
                f'{nome}: scaricati {scaricato} byte su {atteso} attesi, download incompleto')
        os.replace(parziale, dest)
    finally:
        if os.path.exists(parziale):
            os.remove(parziale)
    click.echo(f'  {nome}: {os.path.getsize(dest) / 1e6:.0f} MB')
    return dest


def _estrai(zip_path, prefisso):
    """Estrae i file dello shapefile che iniziano con `prefisso`; ritorna il .shp."""
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        membri = [m for m in z.namelist() if os.path.basename(m).startswith(prefisso)]
        if not membri:
            raise click.ClickException(
                f'{prefisso} non trovato in {os.path.basename(zip_path)}')
        z.extractall(CACHE, membri)
    shp = [m for m in membri if m.endswith('.shp')]
    if not shp:
        raise click.ClickException(f'nessuno .shp fra i file {prefisso}')
    return os.path.join(CACHE, shp[0])


def _pg_ogr():
    """La stringa di connessione nel formato che vuole ogr2ogr."""
    from flask import current_app
    u = urllib.parse.urlparse(current_app.config['SQLALCHEMY_DATABASE_URI'])
    pezzi = [f'dbname={u.path.lstrip(chr(47))}']
    if u.hostname:
        pezzi.append(f'host={u.hostname}')
    if u.port:
        pezzi.append(f'port={u.port}')
    if u.username:
        pezzi.append(f'user={u.username}')
    if u.password:
        pezzi.append(f'password={u.password}')
    return 'PG:' + ' '.join(pezzi)


def _ogr2ogr(shp, tabella, extra=()):
    """Carica uno shapefile in PostGIS riproiettato in WGS84."""
    comando = ['ogr2ogr', '-f', 'PostgreSQL', _pg_ogr(), shp,
               '-nln', tabella, '-overwrite', '-t_srs', 'EPSG:4326',
               '-lco', 'GEOMETRY_NAME=geom', '-lco', 'FID=id',
               '-lco', 'SPATIAL_INDEX=GIST', *extra]
    esito = subprocess.run(comando, capture_output=True, text=True)
    if esito.returncode:
        raise click.ClickException(
            f'ogr2ogr su {tabella} fallito:\n{esito.stderr[-1500:]}')


_geolocator = None


# Il liceo, usato come riferimento per il controllo di plausibilita'.
SCUOLA = (41.867626, 12.634917)
RAGGIO_MAX_KM = 120        # oltre, senza un comune dichiarato, il risultato non e' credibile


def _km_dalla_scuola(lat, lon):
    from math import radians, sin, cos, asin, sqrt
    la1, lo1, la2, lo2 = map(radians, (SCUOLA[0], SCUOLA[1], lat, lon))
    a = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def _nominatim(via, cap=None, comune=None):
    """Query strutturata: la via arriva qui gia' canonica, mai abbreviata.

    Serve almeno un vincolo di localita' (comune o CAP): senza, "Via degli
    Ulivi" esiste in mezza Italia e Nominatim ne restituisce una a caso. Un
    risultato lontanissimo ottenuto col solo CAP viene comunque scartato.

    Ritorna (lat, lon, dati_osm) oppure None.
    """
    global _geolocator
    comune, cap = _utile(comune), _utile(cap)
    if not comune and not cap:
        return None
    if _geolocator is None:
        from geopy.geocoders import Nominatim
        _geolocator = Nominatim(user_agent=UA)

    richiesta = {'street': via}
    if comune:
        richiesta['city'] = comune
    if cap:
        richiesta['postalcode'] = cap
    try:
        loc = _geolocator.geocode(richiesta, addressdetails=True, timeout=20)
    except Exception as e:                      # timeout, servizio giu', quota
        click.echo(f'    Nominatim: {type(e).__name__} su {via!r}')
        return None
    finally:
        time.sleep(PAUSA_NOMINATIM)
    if not loc:
        return None
    if not comune and _km_dalla_scuola(loc.latitude, loc.longitude) > RAGGIO_MAX_KM:
        click.echo(f'    scartato: {via!r} col solo CAP {cap} finisce a '
                   f'{_km_dalla_scuola(loc.latitude, loc.longitude):.0f} km dalla scuola')
        return None
    return loc.latitude, loc.longitude, (loc.raw.get('address') or {})


# ---------------------------------------------------------------------------
# flask stradario-sync
# ---------------------------------------------------------------------------

def _comuni_da_coprire():
    """I comuni che compaiono davvero nei dati, non tutti quelli d'Italia."""
    righe = db.session.execute(text(
        "select distinct comune_residenza from alunni "
        "where comune_residenza is not null and comune_residenza <> ''")).fetchall()
    return sorted({r[0].strip() for r in righe if r[0] and r[0].strip()})


@click.command('stradario-sync')
@click.option('--riscarica', is_flag=True, help='Riscarica i file anche se sono in cache.')
@with_appcontext
def stradario_sync(riscarica):
    """Costruisce l'elenco delle vie reali dei comuni presenti nei dati.

    Due sorgenti scaricate per intero, non interrogate a query: le strade OSM
    del Centro Italia da Geofabrik e i confini comunali ufficiali da ISTAT. Il
    comune di ogni via si ricava per contenimento geometrico, che e' piu'
    preciso delle aree amministrative di OpenStreetMap.

    I file restano in data/stradario_cache/: rilanciare il comando non
    riscarica nulla se non si passa --riscarica.
    """
    Stradario.__table__.create(db.engine, checkfirst=True)

    click.echo('Sorgenti:')
    zip_strade = _scarica(GEOFABRIK, 'centro-free.shp.zip', riscarica)
    zip_comuni = _scarica(ISTAT, 'istat_comuni.zip', riscarica)

    click.echo('Carico in PostGIS...')
    _ogr2ogr(_estrai(zip_comuni, ISTAT_COMUNI), 'istat_comuni',
             ['-nlt', 'MULTIPOLYGON', '-select', 'COMUNE,PRO_COM_T,COD_PROV'])
    _ogr2ogr(_estrai(zip_strade, GEOFABRIK_STRADE), 'osm_strade_raw',
             ['-nlt', 'MULTILINESTRING', '-select', 'osm_id,name,fclass',
              '-where', "name IS NOT NULL"])
    n_strade = db.session.execute(text('select count(*) from osm_strade_raw')).scalar()
    n_comuni = db.session.execute(text('select count(*) from istat_comuni')).scalar()
    click.echo(f'  strade con nome: {n_strade} | comuni: {n_comuni}')

    # I nomi dei comuni vanno riconciliati fuori da SQL: in `alunni` c'e'
    # 'MONTECOMPATRI', in ISTAT 'Monte Compatri'.
    istat = db.session.execute(text('select pro_com_t, comune from istat_comuni')).fetchall()
    per_chiave = {}
    for codice, nome in istat:
        per_chiave.setdefault(toponimi.chiave_comune(nome), (codice, nome))

    voluti, fuori = [], []
    for c in _comuni_da_coprire():
        trovato = per_chiave.get(toponimi.chiave_comune(c))
        (voluti if trovato else fuori).append(trovato or c)
    if fuori:
        click.echo(f'Comuni non riconosciuti in ISTAT (resteranno a Nominatim): '
                   f'{", ".join(sorted(fuori))}')
    codici = [c for c, _ in voluti]
    click.echo(f'Comuni da coprire: {len(codici)}')

    # ST_PointOnSurface cade sempre sulla linea, a differenza del baricentro che
    # su una strada a U puo' finire in un altro comune.
    click.echo('Assegno il comune e aggrego per via...')
    righe = db.session.execute(text("""
        select r.name, c.comune,
               ST_Y(ST_Centroid(ST_Collect(r.geom))) as lat,
               ST_X(ST_Centroid(ST_Collect(r.geom))) as lon,
               count(*) as segmenti
        from osm_strade_raw r
        join istat_comuni c
          on c.pro_com_t = any(:codici)
         and ST_Contains(c.geom, ST_PointOnSurface(r.geom))
        group by 1, 2
    """), {'codici': codici}).fetchall()
    click.echo(f'  vie distinte: {len(righe)}')

    # Una via compare in OSM anche con grafie diverse ('Via Fontana Delle
    # Cannetacce' / 'Via Fontana delle Cannetacce'): si tiene la piu' diffusa.
    agg = {}
    for nome, comune, lat, lon, segmenti in righe:
        chiave = (toponimi.chiave(nome), comune)
        voce = agg.setdefault(chiave, {'grafie': Counter(), 'lat': 0.0,
                                       'lon': 0.0, 'peso': 0})
        voce['grafie'][nome] += segmenti
        voce['lat'] += lat * segmenti
        voce['lon'] += lon * segmenti
        voce['peso'] += segmenti

    db.session.execute(text('delete from stradario'))
    for (nome_norm, comune), v in agg.items():
        lat, lon = v['lat'] / v['peso'], v['lon'] / v['peso']
        db.session.add(Stradario(
            nome=v['grafie'].most_common(1)[0][0][:256],
            nome_norm=nome_norm[:256],
            comune=(comune or '')[:128],
            osm_ids=v['peso'],
            geom=from_shape(Point(lon, lat), srid=4326)))
    db.session.commit()

    coperti = db.session.execute(text(
        'select count(distinct comune) from stradario')).scalar()
    click.echo(f'\nStradario: {len(agg)} vie in {coperti} comuni.')
    if coperti < len(codici):
        # Un comune senza nemmeno una via significa quasi sempre che sta fuori
        # dall'estratto Geofabrik scaricato.
        mancanti = {n for _, n in voluti} - {r[0] for r in db.session.execute(
            text('select distinct comune from stradario')).fetchall()}
        click.echo(f'Senza vie nell\'estratto: {", ".join(sorted(mancanti))}')


# ---------------------------------------------------------------------------
# flask import-alunni
# ---------------------------------------------------------------------------

def anno_da_nome_file(percorso):
    """'RMII0063_AC_2024-25_data...xls' -> '2024-2025'."""
    m = re.search(r'AC[_-](\d{4})-(\d{2})', os.path.basename(percorso))
    if not m:
        return None
    inizio = int(m.group(1))
    return f'{inizio}-{inizio + 1}'


def _valore(campo, grezzo, avvisi):
    if grezzo is None:
        return None
    v = str(grezzo).strip()
    if v == '' or v.lower() == 'nan':
        return None
    if campo in INTERI:
        try:
            return int(float(v))
        except ValueError:
            avvisi.append((campo, v, 'intero non valido'))
            return None
    if campo in DECIMALI:
        try:
            return float(v.replace(',', '.'))
        except ValueError:
            avvisi.append((campo, v, 'decimale non valido'))
            return None
    if campo in DATE:
        for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
            try:
                return datetime.strptime(v, formato)
            except ValueError:
                continue
        avvisi.append((campo, v, 'data non valida'))
        return None
    if len(v) > LUNGHEZZA_MAX:
        avvisi.append((campo, v, f'troncato a {LUNGHEZZA_MAX} caratteri'))
        return v[:LUNGHEZZA_MAX]
    return v


@click.command('import-alunni')
@click.argument('percorso', type=click.Path())
@click.option('--anno', help="Anno scolastico 'AAAA-AAAA'; se assente si deduce dal nome file.")
@click.option('--dry-run', is_flag=True, help='Analizza e scrive il log senza toccare il DB.')
@with_appcontext
def import_alunni(percorso, anno, dry_run):
    """Importa un export Spaggiari (.xls) di una annata."""
    import pandas as pd

    # Comodita' per chi lavora dalla cartella sbagliata: basta il nome del file
    # se sta in data/input/.
    if not os.path.isfile(percorso):
        candidato = os.path.join(DATI_INPUT, os.path.basename(percorso))
        if os.path.isfile(candidato):
            percorso = candidato
        else:
            raise click.ClickException(
                f'File non trovato: {percorso}\n'
                f'I file della segreteria vanno messi in {DATI_INPUT}/')

    anno = anno or anno_da_nome_file(percorso)
    if not anno or not re.fullmatch(r'\d{4}-\d{4}', anno):
        raise click.ClickException(
            "Anno non deducibile dal nome file: passalo con --anno AAAA-AAAA")
    click.echo(f'Annata: {anno}')

    # `ignore_workbook_corruption`: l'header OLE scritto da Spaggiari fa fallire
    # xlrd con "Workbook corruption", ma il contenuto del foglio e' integro.
    df = pd.read_excel(percorso, dtype=str, engine='xlrd',
                       engine_kwargs={'ignore_workbook_corruption': True})
    mancanti = [c for c in MAPPA if c not in df.columns]
    if mancanti:
        click.echo(f'Colonne assenti nel file (verranno lasciate vuote): {", ".join(mancanti)}')

    esistenti = {r[0] for r in db.session.execute(
        text('select id_alunno from alunni where anno_ref = :a'), {'a': anno}).fetchall()}
    click.echo(f'Righe nel file: {len(df)} | gia\' in DB per questa annata: {len(esistenti)}')

    log, nuovi, visti = [], [], set()
    for posizione, riga in df.iterrows():
        avvisi = []
        dati = {}
        for colonna, campo in MAPPA.items():
            if colonna in df.columns:
                dati[campo] = _valore(campo, riga[colonna], avvisi)

        id_alunno = dati.get('id_alunno')
        if id_alunno is None:
            log.append([posizione + 2, '', anno, 'scartata', 'Id Alunno assente o non numerico'])
            continue
        if id_alunno in esistenti:
            log.append([posizione + 2, id_alunno, anno, 'saltata',
                        'coppia (anno_ref, id_alunno) gia\' presente in DB'])
            continue
        if id_alunno in visti:
            # Non capita nei file attuali (Id Alunno e' unico per file), ma una
            # doppia iscrizione nello stesso anno esiste davvero nello storico.
            log.append([posizione + 2, id_alunno, anno, 'saltata',
                        'Id Alunno ripetuto dentro lo stesso file'])
            continue
        visti.add(id_alunno)

        dati['anno_ref'] = anno
        dati['via'] = toponimi.via_pulita(dati.get('indirizzo_residenza'))
        dati['esito_finale_norm'] = toponimi.norm_esito(dati.get('esito_finale'))
        dati['indirizzo_studi_norm'] = toponimi.norm_indirizzo_studi(dati.get('indirizzo_studi'))
        dati['sede_norm'] = toponimi.norm_sede(dati.get('sede'))

        cap_grezzo = dati.get('cap_residenza')
        if cap_grezzo and toponimi.normalizza_cap(cap_grezzo) is None:
            log.append([posizione + 2, id_alunno, anno, 'avviso',
                        f'CAP inutilizzabile: {cap_grezzo!r} (non 5 cifre)'])
        for campo, valore, motivo in avvisi:
            log.append([posizione + 2, id_alunno, anno, 'avviso', f'{campo}={valore!r}: {motivo}'])

        nuovi.append(Alunno(**dati))

    percorso_log = _scrivi_csv(
        f'log_import_{anno}.csv',
        ['riga_file', 'id_alunno', 'anno_ref', 'esito', 'motivo'], log)

    saltate = sum(1 for r in log if r[3] in ('saltata', 'scartata'))
    if dry_run:
        click.echo(f'\n[dry-run] da inserire: {len(nuovi)} | saltate: {saltate}')
    else:
        db.session.bulk_save_objects(nuovi)
        db.session.commit()
        click.echo(f'\nInserite: {len(nuovi)} | saltate: {saltate}')
    click.echo(f'Log: {percorso_log}')


# ---------------------------------------------------------------------------
# flask geocode
# ---------------------------------------------------------------------------

class _Indice:
    """Indice in memoria dello stradario, per generare i candidati.

    Due chiavi: il token esatto (caso normale) e il prefisso di quattro lettere
    (serve ai refusi, dove il token scritto male non e' nell'indice: cercare
    'MONTEMILITTO' non trova nulla, cercare 'MONT' trova 'MONTEMILETTO').
    """

    SOGLIA_TOKEN_COMUNE = 500       # oltre questa frequenza il token non discrimina

    def __init__(self, righe):
        self.righe = righe
        self.per_token = defaultdict(list)
        self.per_prefisso = defaultdict(list)
        # Senza spazi: 'ROCCA MORICE' e 'ROCCAMORICE' hanno zero token in
        # comune, quindi per_token non li fa mai incontrare.
        self.per_join = defaultdict(list)
        for r in righe:
            token = r.nome_norm.split()
            for t in token:
                self.per_token[t].append(r)
            if token:
                self.per_prefisso[token[-1][:4]].append(r)
                self.per_join[''.join(token)].append(r)

    def candidati(self, nome):
        visti, fuori = set(), []
        for r in self.per_join.get(''.join(nome), ()):
            if r.id not in visti:
                visti.add(r.id)
                fuori.append(r)
        for t in nome:
            lista = self.per_token.get(t, ())
            if 0 < len(lista) <= self.SOGLIA_TOKEN_COMUNE:
                for r in lista:
                    if r.id not in visti:
                        visti.add(r.id)
                        fuori.append(r)
        if fuori:
            return fuori
        for t in nome:
            for r in self.per_prefisso.get(t[:4], ()):
                if r.id not in visti:
                    visti.add(r.id)
                    fuori.append(r)
        return fuori


VieStradario = namedtuple('VieStradario', 'id nome nome_norm comune lat lon')


def _riga_stradario(righe, comune):
    """Fra piu' vie omonime sceglie quella del comune dichiarato; mai a caso."""
    if not righe:
        return None
    con_punto = [r for r in righe if r.lat is not None]
    if not con_punto:
        return None
    if comune:
        # Comune dichiarato: o la via e' li', o non e' questa. Il ripiego
        # sull'unica omonima altrove piazzava 'Via Capizzi' di uno studente di
        # Frascati sulla Via Capizzi di Roma, ed e' stata la fonte principale
        # dei collegamenti fuori comune sopravvissuti alla rigeocodifica.
        c = toponimi.chiave_comune(comune)
        stesso = [r for r in con_punto if toponimi.chiave_comune(r.comune) == c]
        return stesso[0] if stesso else None
    return con_punto[0] if len(con_punto) == 1 else None


def _carica_stradario():
    """Lo stradario in memoria, con le coordinate gia' estratte dalla geometria.

    Si evita l'ORM perche' servono solo pochi campi su decine di migliaia di
    righe e il punto va letto una volta sola, non una query per via.

    `nome_norm` viene ricalcolato qui invece di leggere la colonna: quella
    conserva la normalizzazione in vigore al momento del sync, e ogni modifica
    alle regole in toponimi.py la renderebbe silenziosamente obsoleta.
    """
    righe = db.session.execute(text(
        'select id, nome, comune, ST_Y(geom), ST_X(geom) from stradario')).fetchall()
    return [VieStradario(i, nome, toponimi.chiave(nome), comune, lat, lon)
            for i, nome, comune, lat, lon in righe]


def _comuni_istat():
    """chiave_comune -> codice ISTAT, per verificare dove cade un punto.

    Vuoto se `stradario-sync` non e' mai stato lanciato: in quel caso la
    verifica di contenimento viene semplicemente saltata.
    """
    try:
        righe = db.session.execute(text(
            'select pro_com_t, comune from istat_comuni')).fetchall()
    except Exception:
        db.session.rollback()
        return {}
    mappa = {}
    for codice, nome in righe:
        mappa.setdefault(toponimi.chiave_comune(nome), codice)
    return mappa


# Quanto puo' sporgere oltre il confine un punto che appartiene comunque al
# comune dichiarato. Non e' un allentamento del vincolo: quello che si salva e'
# il baricentro della via, e su una strada a cavallo del confine il baricentro
# cade dall'altra parte. 'Via Torre dello Stinco' e' Roma per OSM e per la
# segreteria, e il suo punto sta 40 cm dentro Frascati; l'omonima di un altro
# comune, che e' l'errore da fermare, sta a chilometri (Nerola, 47 km).
TOLLERANZA_CONFINE_M = 100


def _dentro_comune(lat, lon, codice):
    """Il punto cade davvero dentro il comune dichiarato?

    Serve perche' Nominatim, quando non trova la via nel comune richiesto,
    allenta il vincolo invece di rispondere "non trovata": 'Via dei
    Giardinetti' a Roma torna come la via omonima di Nerola, 47 km piu' in la'.
    Il confine ISTAT e' il giudice, non il nome di citta' restituito, che
    spesso e' una frazione ('Setteville' per Guidonia).

    Il confine si prende con `TOLLERANZA_CONFINE_M` di margine: senza, una via
    a cavallo del confine e' irrecuperabile: nessun candidato passa e la coda
    di revisione non offre alcuna via d'uscita.
    """
    return bool(db.session.execute(text(
        'select ST_Contains(geom, ST_SetSRID(ST_Point(:lon, :lat), 4326)) '
        '    or ST_DWithin(geom::geography, '
        '                  ST_SetSRID(ST_Point(:lon, :lat), 4326)::geography, :tol) '
        'from istat_comuni where pro_com_t = :c'),
        {'lat': lat, 'lon': lon, 'c': codice,
         'tol': TOLLERANZA_CONFINE_M}).scalar())


def _strada_nel_comune(id_strada, codice, cache):
    """La `strada` gia' in archivio cade dentro il comune dichiarato?

    Stesso giudice di `_dentro_comune`, ma sulla geometria gia' salvata. La
    cache evita di ripetere la stessa query per ogni gruppo di indirizzi che
    riusa la stessa via.
    """
    k = (id_strada, codice)
    if k not in cache:
        cache[k] = bool(db.session.execute(text(
            'select ST_Contains(c.geom, s.geom) from istat_comuni c, strada s '
            'where c.pro_com_t = :c and s.id = :s'),
            {'c': codice, 's': id_strada}).scalar())
    return cache[k]


def _prima_nel_comune(righe, codice, cache):
    """La prima `strada` fra `righe` che sta nel comune dichiarato, o None.

    Il riuso senza questo controllo aggancia la via omonima del comune accanto
    ogni volta che il CAP combacia: 'Via Casilina' attraversa davvero Roma e
    Monte Compatri, e 17 studenti romani stavano sul punto di Monte Compatri.
    Se il comune non e' riconosciuto (`codice` None) non c'e' nulla da
    verificare e vale la prima riga, come prima.
    """
    for s in righe or ():
        if codice is None or _strada_nel_comune(s.id, codice, cache):
            return s
    return None


def _strade_per_chiave():
    """Le `strada` gia' presenti, indicizzate per (nome normalizzato, CAP) e per sola via.

    Il secondo indice serve quando il CAP dichiarato e' inutilizzabile: meglio
    riusare la via gia' nota che creare una riga doppia senza CAP.
    """
    per_via_cap, per_via = defaultdict(list), defaultdict(list)
    for s in Strada.query.all():
        if s.osm_road:
            k = toponimi.chiave(s.osm_road)
            per_via_cap[(k, (s.osm_postcode or '').strip())].append(s)
            per_via[k].append(s)
    return per_via_cap, per_via


@click.command('geocode')
@click.option('--anno', help="Annata da trattare, 'AAAA-AAAA'.")
@click.option('--tutti', is_flag=True, help='Tutte le annate con alunni non collegati.')
@click.option('--limite', type=int, help='Ferma dopo N gruppi di indirizzi (per provare).')
@with_appcontext
def geocode(anno, tutti, limite):
    """Collega gli alunni a una `strada` geocodificata a livello di via."""
    if not anno and not tutti:
        raise click.ClickException('Serve --anno AAAA-AAAA oppure --tutti')

    condizione = '' if tutti else 'and a.anno_ref = :anno'
    righe = db.session.execute(text(f"""
        select a.id, a.anno_ref, a.indirizzo_residenza, a.cap_residenza, a.comune_residenza
        from alunni a
        where not exists (select 1 from rel_alunno_strada r where r.alunno_id = a.id)
          and a.indirizzo_residenza is not null and a.indirizzo_residenza <> ''
          {condizione}
    """), {'anno': anno}).fetchall()

    gruppi = defaultdict(list)
    for id_alunno, _anno, indirizzo, cap, comune in righe:
        gruppi[(indirizzo.strip(), (cap or '').strip(), (comune or '').strip())].append(id_alunno)
    click.echo(f'Alunni senza indirizzo collegato: {len(righe)} '
               f'in {len(gruppi)} indirizzi distinti')

    stradario = _carica_stradario()
    if not stradario:
        click.echo('Stradario vuoto: lancia prima `flask stradario-sync`.')
    # Vie omonime esistono in comuni diversi: la chiave non puo' essere il solo nome.
    per_nome = defaultdict(list)
    for r in stradario:
        per_nome[r.nome].append(r)
    indice = _Indice(stradario)
    strade, strade_per_via = _strade_per_chiave()
    comuni_istat = _comuni_istat()
    click.echo(f'Stradario: {len(stradario)} vie | strade gia\' geocodificate: '
               f'{sum(len(v) for v in strade.values())}')

    conteggi = defaultdict(int)
    coda, collegamenti, correzioni = [], [], []
    dentro_cache = {}
    ordinati = sorted(gruppi.items(), key=lambda kv: -len(kv[1]))
    if limite:
        ordinati = ordinati[:limite]

    with click.progressbar(ordinati, label='Geocodifica') as barra:
        for (indirizzo, cap_grezzo, comune), alunni in barra:
            cap = toponimi.normalizza_cap(cap_grezzo)
            _tipo, nome = toponimi.normalizza(indirizzo)
            if not nome:
                conteggi['illeggibile'] += 1
                coda.append([indirizzo, cap_grezzo, comune, '', '',
                             'indirizzo illeggibile', len(alunni)])
                continue

            # Stadio 1: canonicalizzazione contro le vie reali.
            esito = toponimi.risolvi(nome, indice.candidati(nome), comune=comune)
            if esito and esito.regola == 'ambigua':
                conteggi['ambigua'] += 1
                coda.append([indirizzo, cap_grezzo, comune, ' '.join(nome),
                             ' | '.join(esito.ambigui), 'piu\' vie compatibili', len(alunni)])
                continue
            canonico = esito.nome if esito else None
            regola = esito.regola if esito else 'nessuna'
            # Ogni regola diversa da 'esatta' ha cambiato la via scritta dalla
            # segreteria: va nel CSV delle correzioni, che e' cio' che si
            # controlla a mano dopo un giro di geocodifica.
            if canonico and regola != 'esatta':
                conteggi[f'corretta ({regola})'] += 1
                correzioni.append([indirizzo, ' '.join(nome), canonico, regola,
                                   cap_grezzo, comune, len(alunni)])

            # Il comune dichiarato giudica sia il riuso (stadio 2) sia la
            # risposta di Nominatim (stadio 3).
            codice = comuni_istat.get(toponimi.chiave_comune(comune))

            # Stadio 2: riuso di una `strada` gia' presente con lo stesso CAP.
            chiave_via = toponimi.chiave(canonico) if canonico else ' '.join(nome)
            esistente = strade.get((chiave_via, cap or ''))
            if not esistente and not cap:
                # CAP inutilizzabile: si riusa la via nota invece di duplicarla.
                esistente = strade_per_via.get(chiave_via)
            riusabile = _prima_nel_comune(esistente, codice, dentro_cache)
            if riusabile is not None:
                conteggi['riuso'] += 1
                for a in alunni:
                    collegamenti.append((a, riusabile.id))
                continue
            if esistente:
                # La via esiste ma sta in un altro comune: si prosegue allo
                # stadio 3, che creera' il punto giusto per questo comune.
                conteggi['riuso scartato (fuori dal comune)'] += 1

            # Stadio 3: Nominatim, con la via ormai pulita.
            etichetta = canonico or f'{_tipo or "Via"} {" ".join(nome)}'.title()
            risposta = _nominatim(etichetta, cap, comune or None)
            if risposta is None and cap:
                risposta = _nominatim(etichetta, None, comune or None)

            # Nominatim puo' rispondere con una via omonima di un altro comune:
            # il confine ISTAT dice se il punto e' dove lo studente abita.
            if risposta and codice and not _dentro_comune(risposta[0], risposta[1], codice):
                conteggi['scartata (fuori dal comune)'] += 1
                risposta = None
            fonte = 'nominatim'
            if risposta:
                lat, lon, osm = risposta
                citta = _utile(osm.get('city') or osm.get('town')
                               or osm.get('village') or comune)
                cap_osm = osm.get('postcode')
                sobborgo = osm.get('suburb')
            elif _riga_stradario(per_nome.get(canonico), comune):
                # Stadio 3 fallito ma la via esiste nello stradario: si usa il suo
                # baricentro, meno preciso sul settore ma nel posto giusto.
                riga = _riga_stradario(per_nome.get(canonico), comune)
                lat, lon = riga.lat, riga.lon
                citta, cap_osm, sobborgo, fonte = riga.comune, cap, None, 'stradario'
            else:
                conteggi['non risolta'] += 1
                coda.append([indirizzo, cap_grezzo, comune, ' '.join(nome),
                             canonico or '',
                             'nessun riscontro nel comune dichiarato',
                             len(alunni)])
                continue

            nuova = Strada(
                osm_road=(canonico or etichetta)[:128],
                osm_postcode=(cap or cap_osm or None),
                osm_suburb=sobborgo,
                osm_city=citta,
                osm_lat=lat,
                osm_lon=lon,
                geom=from_shape(Point(lon, lat), srid=4326))
            db.session.add(nuova)
            db.session.flush()
            strade[(toponimi.chiave(nuova.osm_road), nuova.osm_postcode or '')].append(nuova)
            strade_per_via[toponimi.chiave(nuova.osm_road)].append(nuova)
            conteggi[f'nuova via ({fonte})'] += 1
            for a in alunni:
                collegamenti.append((a, nuova.id))

    for id_alunno, id_strada in collegamenti:
        db.session.execute(text(
            'insert into rel_alunno_strada (alunno_id, strada_id) values (:a, :s) '
            'on conflict do nothing'), {'a': id_alunno, 's': id_strada})
    db.session.commit()

    correzioni.sort(key=lambda r: -r[-1])
    percorso_corr = _scrivi_csv(
        f'correzioni_{anno or "tutti"}.csv',
        ['indirizzo_grezzo', 'token', 'via_canonica', 'regola', 'cap', 'comune', 'n_alunni'],
        correzioni)

    coda.sort(key=lambda r: -r[-1])
    percorso = _scrivi_csv(
        f'da_rivedere_{anno or "tutti"}.csv',
        ['indirizzo_grezzo', 'cap', 'comune', 'token', 'candidati', 'motivo', 'n_alunni'],
        coda)

    click.echo(f'\nAlunni collegati: {len(collegamenti)}')
    for k in sorted(conteggi):
        click.echo(f'  {k:28} {conteggi[k]}')
    click.echo(f'Correzioni applicate: {len(correzioni)} -> {percorso_corr}')
    click.echo(f'Da rivedere: {len(coda)} indirizzi '
               f'({sum(r[-1] for r in coda)} alunni) -> {percorso}')


# ---------------------------------------------------------------------------
# flask strade-cleanup
# ---------------------------------------------------------------------------

@click.command('strade-cleanup')
@click.option('--dry-run', is_flag=True, help='Mostra cosa farebbe, senza scrivere.')
@with_appcontext
def strade_cleanup(dry_run):
    """Una tantum: privacy sui civici, unione dei doppioni, sede_norm sullo storico."""
    con_civico = db.session.execute(text(
        "select id, osm_road, osm_postcode, osm_city from strada "
        "where osm_house_number is not null and osm_house_number not in ('', 'empty')"
    )).fetchall()
    # La chiave naturale include il comune: 'Via Casilina' con lo stesso CAP
    # esiste davvero a Roma e a Monte Compatri, e sono due punti diversi. Il
    # comune e' quello che contiene il punto, non `osm_city`, che riporta la
    # risposta di Nominatim e a volte sbaglia (la `Via Osini` di Monte
    # Compatri e' salvata come 'Roma').
    doppioni = db.session.execute(text("""
        select s.osm_road, coalesce(s.osm_postcode,''), coalesce(c.comune,'')
        from strada s left join istat_comuni c on ST_Contains(c.geom, s.geom)
        group by 1, 2, 3 having count(*) > 1""")).fetchall()
    click.echo(f'Strade con civico (punto sulla casa): {len(con_civico)}')
    click.echo(f'Gruppi duplicati (via, CAP, comune): {len(doppioni)}')

    if dry_run:
        click.echo('[dry-run] nessuna modifica applicata.')
        return

    # 1. Il civico sparisce dal DB: da qui in poi si geocodifica solo la via.
    db.session.execute(text(
        "update strada set osm_house_number = null, osm_house_number_dev = null "
        "where osm_house_number is not null"))
    db.session.commit()

    # 2. Unione dei doppioni: i collegamenti passano alla riga superstite.
    uniti = 0
    for via, cap, comune in doppioni:
        ids = [r[0] for r in db.session.execute(text("""
            select s.id from strada s
            left join istat_comuni c on ST_Contains(c.geom, s.geom)
            where s.osm_road = :v and coalesce(s.osm_postcode,'') = :c
              and coalesce(c.comune,'') = :t
            order by s.id"""), {'v': via, 'c': cap, 't': comune}).fetchall()]
        sopravvive, altri = ids[0], ids[1:]
        db.session.execute(text(
            'insert into rel_alunno_strada (alunno_id, strada_id) '
            'select alunno_id, :vive from rel_alunno_strada where strada_id = any(:altri) '
            'on conflict do nothing'), {'vive': sopravvive, 'altri': altri})
        db.session.execute(text('delete from rel_alunno_strada where strada_id = any(:a)'),
                           {'a': altri})
        db.session.execute(text('delete from strada where id = any(:a)'), {'a': altri})
        uniti += len(altri)
    db.session.commit()
    click.echo(f'Righe `strada` eliminate per unione: {uniti}')

    # 3. I punti che erano sulla casa vanno riportati sulla via.
    sopravvissuti = [r for r in db.session.execute(text(
        "select id, osm_road, osm_postcode, osm_city from strada where id = any(:ids)"),
        {'ids': [r[0] for r in con_civico]}).fetchall()]
    rifatti, falliti = 0, []
    with click.progressbar(sopravvissuti, label='Ri-geocodifica a livello via') as barra:
        for id_strada, via, cap, citta in barra:
            risposta = _nominatim(via, cap, citta)
            if not risposta and _utile(cap) and _utile(citta):
                risposta = _nominatim(via, None, citta)   # riprova col solo comune
            if not risposta:
                falliti.append([id_strada, via, cap, citta,
                                'Nominatim non ha risolto: il punto resta quello della casa'])
                continue
            lat, lon, _osm = risposta
            db.session.execute(text(
                'update strada set osm_lat = :la, osm_lon = :lo, '
                'geom = ST_SetSRID(ST_Point(:lo, :la), 4326) where id = :i'),
                {'la': lat, 'lo': lon, 'i': id_strada})
            rifatti += 1
    db.session.commit()
    click.echo(f'Punti riportati sulla via: {rifatti}/{len(sopravvissuti)}')
    if falliti:
        percorso = _scrivi_csv('strade_da_rigeocodificare.csv',
                               ['id_strada', 'via', 'cap', 'citta', 'motivo'], falliti)
        click.echo(f'ATTENZIONE: {len(falliti)} righe puntano ancora sulla casa -> {percorso}')

    # 4. sede_norm, finora vuota su tutte le righe.
    esito = db.session.execute(text("""
        update alunni set sede_norm = case
            when upper(sede) like '%%SUCC%%' then 'SUCCURSALE'
            else 'CENTRALE' end
        where sede is not null and sede <> ''"""))
    db.session.commit()
    click.echo(f'sede_norm popolata su {esito.rowcount} righe')


# ---------------------------------------------------------------------------
# flask audit-geo
# ---------------------------------------------------------------------------

@click.command('audit-geo')
@click.option('--scollega', is_flag=True,
              help='Rimuove i collegamenti sbagliati, poi rilancia `geocode --tutti`.')
@with_appcontext
def audit_geo(scollega):
    """Trova gli alunni collegati a una via che sta fuori dal loro comune.

    Stessa verifica che `geocode` fa sui risultati nuovi, applicata a tutto
    l'archivio: il punto di ogni `strada` viene confrontato col confine ISTAT
    del comune dichiarato dallo studente. Serve perche' i collegamenti fatti a
    mano negli anni contengono errori dello stesso tipo che Nominatim produce
    da solo -- 28 studenti di Via Corvara a Roma puntati alla Via Corvara di
    Nettuno, 60 km piu' in la'.
    """
    if not _comuni_istat():
        raise click.ClickException(
            'Confini ISTAT assenti: lancia prima `flask stradario-sync`.')

    # Il comune vero di ogni strada, una volta sola: sono poche migliaia di
    # punti contro poligoni indicizzati.
    reale, nome_via, confinanti = {}, {}, {}
    for id_strada, via, comune in db.session.execute(text("""
        select s.id, s.osm_road, c.comune
        from strada s left join istat_comuni c on ST_Contains(c.geom, s.geom)
        where s.geom is not null""")).fetchall():
        reale[id_strada] = comune
        nome_via[id_strada] = via or '?'

    # I comuni che il punto sfiora entro la tolleranza: su una via a cavallo del
    # confine il baricentro sta nel comune accanto, ma la via e' quella giusta.
    # 'Via Torre dello Stinco' e' Roma e il suo punto cade 40 cm dentro Frascati.
    for id_strada, comune in db.session.execute(text("""
        select s.id, c.comune
        from strada s join istat_comuni c
          on ST_DWithin(c.geom::geography, s.geom::geography, :tol)
        where s.geom is not null"""), {'tol': TOLLERANZA_CONFINE_M}).fetchall():
        confinanti.setdefault(id_strada, set()).add(toponimi.chiave_comune(comune))

    coppie = db.session.execute(text("""
        select r.strada_id, upper(trim(a.comune_residenza)) as comune,
               count(*) as n, bool_or(r.forzato) as forzato
        from rel_alunno_strada r
        join alunni a on a.id = r.alunno_id
        where a.comune_residenza is not null and a.comune_residenza <> ''
        group by 1, 2""")).fetchall()

    istat = _comuni_istat()
    sbagliate, senza_punto, forzate, non_verificabili = [], [], [], 0
    for id_strada, dichiarato, n, forzato in coppie:
        if id_strada not in reale:
            # `strada` senza geometria: il collegamento esiste ma non colloca
            # nessuno. In archivio c'e' una riga segnaposto tutta vuota usata
            # storicamente per "indirizzo non risolto".
            senza_punto.append((id_strada, dichiarato, n))
            continue
        if toponimi.chiave_comune(dichiarato) not in istat:
            non_verificabili += n           # comune estero o fuori Italia
            continue
        effettivo = reale.get(id_strada)
        if not effettivo or toponimi.chiave_comune(effettivo) == toponimi.chiave_comune(dichiarato):
            continue
        if toponimi.chiave_comune(dichiarato) in confinanti.get(id_strada, ()):
            continue                        # via a cavallo del confine, non un errore
        if forzato:
            forzate.append((id_strada, dichiarato, effettivo, n))
        else:
            sbagliate.append((id_strada, dichiarato, effettivo, n))

    sbagliate.sort(key=lambda x: -x[3])
    forzate.sort(key=lambda x: -x[3])
    righe = [[i, nome_via.get(i, '?'), eff, dich, n, forzato]
             for elenco, forzato in ((sbagliate, ''), (forzate, 'si'))
             for i, dich, eff, n in elenco]
    percorso = _scrivi_csv('audit_geo.csv',
                           ['id_strada', 'via', 'comune_del_punto',
                            'comune_dichiarato', 'n_alunni', 'forzato'], righe)

    tot = sum(x[3] for x in sbagliate)
    click.echo(f'Collegamenti fuori dal comune dichiarato: {tot} '
               f'su {len(sbagliate)} coppie via/comune')
    for i, dich, eff, n in sbagliate[:15]:
        click.echo(f'  {n:4} alunni  {nome_via.get(i, "?"):32} '
                   f'punto in {eff!r}, dichiarato {dich!r}')
    if forzate:
        click.echo(f'\nCollegamenti forzati a mano da /revisione: '
                   f'{sum(x[3] for x in forzate)} alunni su {len(forzate)} '
                   f'coppie via/comune. Sono decisioni prese guardando il caso, '
                   f'non errori: `--scollega` non li tocca.')
        for i, dich, eff, n in forzate[:15]:
            click.echo(f'  {n:4} alunni  {nome_via.get(i, "?"):32} '
                       f'punto in {eff!r}, dichiarato {dich!r}')
    if senza_punto:
        vuote = sorted({x[0] for x in senza_punto})
        click.echo(f'Collegamenti a `strada` senza geometria: '
                   f'{sum(x[2] for x in senza_punto)} alunni '
                   f'(righe {", ".join(str(v) for v in vuote)}) '
                   f'- risultano geocodificati ma non hanno un punto')
    if non_verificabili:
        click.echo(f'Non verificabili (comune non in ISTAT): {non_verificabili} alunni')
    click.echo(f'Dettaglio: {percorso}')

    if not scollega:
        click.echo('\nNessuna modifica. Usa --scollega per rimuovere i collegamenti '
                   'sbagliati, poi rilancia `flask geocode --tutti`.')
        return

    rimossi = 0
    for id_strada, dichiarato, _n in senza_punto:
        esito = db.session.execute(text(
            'delete from rel_alunno_strada where strada_id = :s and not forzato'),
            {'s': id_strada})
        rimossi += esito.rowcount
    db.session.execute(text(
        'delete from strada where geom is null and coalesce(osm_road, :v) = :v'), {'v': ''})
    for id_strada, dichiarato, _eff, _n in sbagliate:
        esito = db.session.execute(text("""
            delete from rel_alunno_strada
            where strada_id = :s and not forzato and alunno_id in (
                select id from alunni where upper(trim(comune_residenza)) = :c)"""),
            {'s': id_strada, 'c': dichiarato})
        rimossi += esito.rowcount
    db.session.commit()
    click.echo(f'\nCollegamenti rimossi: {rimossi}. '
               f'Ora lancia `flask geocode --tutti` per rifarli.')


def registra_cli(app):
    for comando in (stradario_sync, import_alunni, geocode, strade_cleanup, audit_geo):
        app.cli.add_command(comando)
