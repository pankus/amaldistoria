"""Revisione manuale degli indirizzi rimasti senza punto sulla mappa.

Blueprint indipendente, visibile al solo ruolo `adm`. Fa tre cose che il
pannello Flask-Admin non fa:

1. mostra il **gruppo** di alunni che condividono lo stesso indirizzo, non le
   righe una per una: 'VIA RADDUSA 55' e 'VIA RADDUSA, 12' sono una decisione
   sola da 45 alunni, non venti decisioni;
2. propone i candidati gia' pronti, presi dallo stradario OSM del comune
   dichiarato, invece di farli cercare a mano;
3. **rifiuta** un collegamento il cui punto cade fuori dal comune dichiarato.
   E' l'errore che `flask audit-geo` ha trovato 891 volte nello storico, tutte
   correzioni fatte a mano negli anni: 134 alunni di Via Santa Rita da Cascia
   puntati a Pomezia, 105 di Via Anteo ad Anzio.

La coda si ricalcola dal database a ogni richiesta. Non si legge
`data/esiti/da_rivedere_*.csv`: quello viene riscritto a ogni `flask geocode`
e invecchia in fretta.
"""

from collections import Counter, defaultdict
from functools import wraps

from flask import (abort, flash, jsonify, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required
from flask_wtf.csrf import generate_csrf, validate_csrf
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import text
from wtforms.validators import ValidationError

from app import toponimi
from app.extensions import db
from app.importer import (_Indice, _carica_stradario, _comuni_istat,
                          _dentro_comune)
from app.models import Strada
from app.revisione import bp


def solo_adm(f):
    """Il pannello tocca i collegamenti di tutto l'archivio: solo `adm`."""
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != 'adm':
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# Lo stradario sono 26.712 righe e costa ~0,7s caricarlo: si tiene in memoria
# per processo. Cambia solo con `flask stradario-sync`, dopo il quale l'app va
# riavviata.
# ponytail: cache di processo, senza invalidazione. Se un giorno lo stradario
# cambiasse a caldo, servira' un contatore di versione sulla tabella.
_CACHE = {}


def _indice():
    if 'indice' not in _CACHE:
        stradario = _carica_stradario()
        _CACHE['stradario'] = stradario
        _CACHE['indice'] = _Indice(stradario)
        _CACHE['istat'] = _comuni_istat()
    return _CACHE['indice']


def _codice_comune(comune):
    _indice()
    return _CACHE['istat'].get(toponimi.chiave_comune(comune))


def _centro_e_zoom(proposte, esistenti, cap, comune):
    """Dove aprire la mappa, e quanto stretta.

    Lo zoom segue la qualita' del centro: su una via candidata si e' gia' sul
    posto, sul baricentro di un CAP si e' nel raggio di un paio di chilometri,
    sul comune si e' solo dentro i confini. Aprire stretti su un centro largo
    mostrerebbe un isolato a caso.
    """
    if proposte:
        return [proposte[0]['lat'], proposte[0]['lon']], 17
    if esistenti:
        return [esistenti[0]['lat'], esistenti[0]['lon']], 17
    punto = _centro_cap(cap)
    if punto:
        return punto, 15
    return _centro_comune(comune) or [41.9028, 12.4964], 13


def _centro_cap(cap):
    """Il baricentro delle vie gia' note con quel CAP.

    E' il ripiego che conta davvero: una via che nessuna fonte conosce non ha
    candidati per definizione, e senza questo la mappa si aprirebbe sul centro
    del comune -- per 'Via Raddusa' a 15 km dal suo quartiere.
    """
    if not cap:
        return None
    riga = db.session.execute(text("""
        select ST_Y(ST_Centroid(ST_Collect(geom))), ST_X(ST_Centroid(ST_Collect(geom)))
        from strada where osm_postcode = :cap and geom is not null"""),
        {'cap': cap}).first()
    return list(riga) if riga and riga[0] is not None else None


def _centro_comune(comune):
    """Un punto dentro il comune, per centrare la mappa quando non c'e' altro.

    `ST_PointOnSurface` e non il baricentro: su un comune concavo il baricentro
    puo' cadere fuori. E' la stessa ragione per cui `stradario-sync` lo usa per
    attribuire il comune a una via.
    """
    riga = db.session.execute(text(
        'select ST_Y(p), ST_X(p) from (select ST_PointOnSurface(geom) p '
        'from istat_comuni where pro_com_t = :c) t'),
        {'c': _codice_comune(comune)}).first() if _codice_comune(comune) else None
    return list(riga) if riga else None


def _comune_del_punto(lat, lon):
    """In quale comune cade il punto, per dirlo quando il vincolo rifiuta.

    «cade fuori da ROMA» non basta a decidere: 'Via Aci Platani' cade ad Aci
    Catena, provincia di Catania, ed e' l'omonimia che il vincolo esiste per
    fermare; 'Via Torre dello Stinco' cade a Frascati per 40 cm ed e' la stessa
    strada. Il nome del comune separa i due casi a colpo d'occhio.
    """
    return db.session.execute(text(
        'select comune from istat_comuni '
        'where ST_Contains(geom, ST_SetSRID(ST_Point(:lon, :lat), 4326))'),
        {'lat': lat, 'lon': lon}).scalar()


def _coda():
    """I gruppi di alunni senza punto, uno per (via normalizzata, comune)."""
    righe = db.session.execute(text("""
        select a.id, a.indirizzo_residenza, a.cap_residenza, a.comune_residenza
        from alunni a
        where not exists (select 1 from rel_alunno_strada r where r.alunno_id = a.id)
          and a.indirizzo_residenza is not null and a.indirizzo_residenza <> ''
    """)).fetchall()

    gruppi = defaultdict(lambda: {'alunni': [], 'indirizzi': Counter(),
                                  'cap': Counter(), 'comuni': Counter()})
    for id_alunno, indirizzo, cap, comune in righe:
        via = toponimi.chiave(indirizzo)
        g = gruppi[(via, toponimi.chiave_comune(comune))]
        g['alunni'].append(id_alunno)
        g['indirizzi'][indirizzo.strip()] += 1
        if toponimi.normalizza_cap(cap):
            g['cap'][toponimi.normalizza_cap(cap)] += 1
        if comune and comune.strip():
            g['comuni'][comune.strip()] += 1
    return gruppi


def _regola_fra(nome, altro):
    """Quale regola del normalizzatore lega i due nomi, se ne lega una.

    Serve a separare i candidati compatibili dal resto: l'indice restituisce
    tutto cio' che condivide un token, quindi per 'LAGO DI BOLSENA' propone
    anche 'Via Lago di Bracciano'. Mostrarli allo stesso livello significa
    mettere l'errore sotto il primo bottone.
    """
    for regola, test in toponimi.REGOLE:
        if test(tuple(nome), tuple(altro)):
            return regola
    return None


def _proposta(via, comune):
    """Cosa direbbe il normalizzatore su questo gruppo, oggi."""
    nome = tuple(via.split())
    if not nome:
        return None, 'indirizzo illeggibile', ()
    esito = toponimi.risolvi(nome, _indice().candidati(nome), comune=comune)
    if esito is None:
        return None, 'nessun candidato nel comune', ()
    if esito.regola == 'ambigua':
        return None, 'piu\' vie compatibili', esito.ambigui
    return esito.nome, esito.regola, ()


@bp.route('/')
@solo_adm
def coda():
    gruppi = _coda()
    righe = []
    for (via, _ck), g in gruppi.items():
        comune = g['comuni'].most_common(1)[0][0] if g['comuni'] else ''
        proposta, motivo, ambigui = _proposta(via, comune)
        righe.append({
            'via': via,
            'comune': comune,
            'cap': ' · '.join(c for c, _ in g['cap'].most_common()),
            'n': len(g['alunni']),
            'esempio': g['indirizzi'].most_common(1)[0][0] if g['indirizzi'] else '',
            'proposta': proposta,
            'motivo': motivo,
            'ambigui': ambigui,
        })
    righe.sort(key=lambda r: -r['n'])
    return render_template('revisione/coda.html', righe=righe,
                           totale=sum(r['n'] for r in righe))


@bp.route('/gruppo')
@solo_adm
def gruppo():
    via = request.args.get('via', '').strip()
    comune = request.args.get('comune', '').strip()
    dati = _coda().get((via, toponimi.chiave_comune(comune)))
    if not dati:
        flash('Gruppo non piu\' in coda: forse e\' gia\' stato collegato.', 'info')
        return redirect(url_for('revisione.coda'))

    nome = tuple(via.split())
    candidati = _indice().candidati(nome) if nome else []
    chiave_com = toponimi.chiave_comune(comune)
    nel_comune = [c for c in candidati
                  if toponimi.chiave_comune(c.comune) == chiave_com]
    proposta, motivo, _amb = _proposta(via, comune)

    # Le `strada` gia' in archivio con lo stesso nome: si riusano, non si
    # duplicano. Il punto deve comunque cadere nel comune dichiarato.
    codice = _codice_comune(comune)
    nomi = {toponimi.chiave(c.nome) for c in nel_comune} | {via}
    esistenti = []
    for s in Strada.query.filter(Strada.osm_road.isnot(None)).all():
        if toponimi.chiave(s.osm_road) in nomi and s.osm_lat and s.osm_lon:
            esistenti.append({
                'id': s.id, 'road': s.osm_road, 'cap': s.osm_postcode,
                'cap_alunni': dati['cap'].get(
                    toponimi.normalizza_cap(s.osm_postcode) or '', 0),
                'city': s.osm_city, 'alunni': s.alunni_nr,
                'lat': s.osm_lat, 'lon': s.osm_lon,
                'regola': _regola_fra(nome, toponimi.chiave(s.osm_road).split()),
                'ok': codice is None or _dentro_comune(s.osm_lat, s.osm_lon, codice),
            })
    if esistenti:
        dove = dict(db.session.execute(text(
            'select s.id, c.comune from strada s '
            'left join istat_comuni c on ST_Contains(c.geom, s.geom) '
            'where s.id = any(:ids)'),
            {'ids': [e['id'] for e in esistenti]}).fetchall())
        for e in esistenti:
            e['comune_punto'] = dove.get(e['id'])
    esistenti.sort(key=lambda x: (not x['ok'], x['regola'] is None,
                                  -x['cap_alunni'], x['road']))

    # Vie reali del comune, quelle che un punto ce l'hanno gia'.
    proposte = [{'id': c.id, 'nome': c.nome, 'comune': c.comune,
                 'lat': c.lat, 'lon': c.lon,
                 'regola': _regola_fra(nome, c.nome_norm.split())}
                for c in nel_comune if c.lat is not None]
    proposte.sort(key=lambda x: (x['regola'] is None, x['nome'] != proposta,
                                 x['nome']))
    caps = dati['cap'].most_common()
    cap_gruppo = caps[0][0] if caps else ''
    centro, zoom = _centro_e_zoom(proposte, esistenti, cap_gruppo, comune)

    return render_template(
        'revisione/gruppo.html', via=via, comune=comune,
        indirizzi=dati['indirizzi'].most_common(),
        n=len(dati['alunni']),
        cap=cap_gruppo, caps=caps,
        proposta=proposta, motivo=motivo,
        esistenti=[e for e in esistenti if e['regola']],
        esistenti_altre=[e for e in esistenti if not e['regola']],
        proposte=[p for p in proposte if p['regola']],
        altre=[p for p in proposte if not p['regola']][:40],
        centro=centro, zoom=zoom,
        nome_suggerito=(toponimi.via_pulita(
            dati['indirizzi'].most_common(1)[0][0]) or via).title(),
        csrf=generate_csrf())


@bp.route('/vicine')
@solo_adm
def vicine():
    """Le vie note dentro il riquadro visibile, per orientarsi mentre si piazza
    un punto: 'Via Raddusa' si colloca guardando Troina, Riposto e Partanna.
    """
    try:
        s_, o_, n_, e_ = (float(request.args[k]) for k in ('s', 'o', 'n', 'e'))
    except (KeyError, ValueError):
        return jsonify([])
    righe = db.session.execute(text("""
        select nome, ST_Y(geom), ST_X(geom) from stradario
        where geom && ST_MakeEnvelope(:o, :s, :e, :n, 4326)
        limit 300"""), {'s': s_, 'o': o_, 'n': n_, 'e': e_}).fetchall()
    return jsonify([{'nome': r[0], 'lat': r[1], 'lon': r[2]} for r in righe])


@bp.route('/dove')
@solo_adm
def dove():
    """Dove cade ciascun punto, prima di provare a salvarlo.

    Serve a mettere il bottone giusto sotto ogni risultato invece di far
    scoprire il rifiuto dopo il click: 'Via Aci Platani' che Nominatim descrive
    come 'Municipio Roma VI, Villa Verde, Roma, Roma Capitale' cade in Frascati,
    145 m oltre il confine. Sola lettura, quindi GET e niente CSRF.
    """
    codice = _codice_comune(request.args.get('comune', ''))
    esiti = []
    for coppia in request.args.getlist('p')[:10]:
        try:
            lat, lon = (float(x) for x in coppia.split(','))
        except ValueError:
            esiti.append(None)
            continue
        # `ok` passa da _dentro_comune: una seconda nozione di "dentro" finirebbe
        # per divergere da quella che poi rifiuta davvero il salvataggio.
        dentro = codice is None or _dentro_comune(lat, lon, codice)
        metri = 0
        if codice and not dentro:
            metri = db.session.execute(text(
                'select round(ST_Distance(ST_Transform(geom, 3857), '
                '  ST_Transform(ST_SetSRID(ST_Point(:lon, :lat), 4326), 3857))) '
                'from istat_comuni where pro_com_t = :c'),
                {'lat': lat, 'lon': lon, 'c': codice}).scalar()
        esiti.append({'comune': _comune_del_punto(lat, lon),
                      'ok': bool(dentro), 'metri': int(metri or 0)})
    return jsonify(esiti)


def _valida_csrf():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        abort(400)


def _collega(via, comune, strada, forza=False):
    """Attacca tutti gli alunni del gruppo a `strada`, se il punto ci sta.

    `forza` scavalca il vincolo di comune. Non lo cancella: il collegamento
    viene marcato `forzato` in `rel_alunno_strada`, cosi' `audit-geo` lo elenca
    a parte e `--scollega` non lo rimuove insieme agli errori veri.
    """
    codice = _codice_comune(comune)
    fuori = bool(codice and strada.osm_lat and strada.osm_lon
                 and not _dentro_comune(strada.osm_lat, strada.osm_lon, codice))
    if fuori and not forza:
        dove = _comune_del_punto(strada.osm_lat, strada.osm_lon)
        flash(f'«{strada.osm_road}» cade {"in " + dove if dove else "fuori"}, non '
              f'in {comune}: collegamento rifiutato. E\' l\'errore piu\' frequente '
              f'fatto a mano. Se e\' comunque la via giusta, usa «Collega comunque» '
              f'sulla riga.', 'danger')
        return False
    dati = _coda().get((via, toponimi.chiave_comune(comune)))
    if not dati:
        flash('Gruppo non piu\' in coda.', 'info')
        return False
    for id_alunno in dati['alunni']:
        db.session.execute(text(
            'insert into rel_alunno_strada (alunno_id, strada_id, forzato) '
            'values (:a, :s, :f) on conflict do nothing'),
            {'a': id_alunno, 's': strada.id, 'f': fuori})
    db.session.commit()
    if fuori:
        flash(f'{len(dati["alunni"])} alunni collegati a «{strada.osm_road}» '
              f'FORZANDO il vincolo: il punto non cade in {comune}. '
              f'Il collegamento resta segnato come anomalia e `flask audit-geo` '
              f'lo elenchera\' a ogni esecuzione.', 'warning')
    else:
        flash(f'{len(dati["alunni"])} alunni collegati a «{strada.osm_road}».',
              'success')
    return True


@bp.route('/collega', methods=['POST'])
@solo_adm
def collega():
    _valida_csrf()
    via = request.form.get('via', '').strip()
    comune = request.form.get('comune', '').strip()
    strada = db.session.get(Strada, request.form.get('strada_id', type=int))
    if strada is None:
        abort(404)
    _collega(via, comune, strada, forza=bool(request.form.get('forza')))
    return redirect(url_for('revisione.coda'))


@bp.route('/crea', methods=['POST'])
@solo_adm
def crea():
    """Crea la `strada` da una via dello stradario o da un risultato Nominatim.

    In entrambi i casi il civico non si tocca: si geocodifica la via.
    """
    _valida_csrf()
    via = request.form.get('via', '').strip()
    comune = request.form.get('comune', '').strip()
    nome = request.form.get('nome', '').strip()
    cap = toponimi.normalizza_cap(request.form.get('cap'))
    citta = request.form.get('citta', '').strip() or comune
    if request.form.get('fonte') == 'manuale':
        # Il comune arriva da `alunni`, dove e' scritto in maiuscolo; le righe
        # di OSM sono 'Roma', 'Monte Compatri'. Uniformare tiene confrontabile
        # la chiave (via, CAP, comune) fra righe manuali e righe OSM.
        citta = citta.title()
    try:
        lat = float(request.form['lat'])
        lon = float(request.form['lon'])
    except (KeyError, TypeError, ValueError):
        flash('Coordinate mancanti.', 'danger')
        return redirect(url_for('revisione.gruppo', via=via, comune=comune))

    forza = bool(request.form.get('forza'))
    codice = _codice_comune(comune)
    if codice and not _dentro_comune(lat, lon, codice) and not forza:
        punto = _comune_del_punto(lat, lon)
        flash(f'«{nome}» cade {"in " + punto if punto else "fuori"}, non in '
              f'{comune}: non creata. Se e\' comunque la via giusta, usa il '
              f'bottone rosso «comunque» accanto al risultato: la forzatura '
              f'resta registrata.', 'danger')
        return redirect(url_for('revisione.gruppo', via=via, comune=comune))

    # Chiave naturale (via, CAP, comune): stesso nome e stesso CAP in due
    # comuni diversi sono due punti, non un doppione.
    esistente = Strada.query.filter_by(
        osm_road=nome[:128], osm_postcode=cap, osm_city=citta).first()
    if esistente is None:
        # `osm_type` tiene la provenienza: 'way'/'node' vengono da OSM, 'manuale'
        # e' un punto messo a mano perche' nessuna fonte conosce quella via.
        fonte = 'manuale' if request.form.get('fonte') == 'manuale' else None
        esistente = Strada(osm_road=nome[:128], osm_postcode=cap,
                           osm_city=citta, osm_lat=lat, osm_lon=lon,
                           osm_type=fonte,
                           geom=from_shape(Point(lon, lat), srid=4326))
        db.session.add(esistente)
        db.session.commit()
        flash(f'Creata la via «{nome}» ({citta}).', 'success')
    _collega(via, comune, esistente, forza=forza)
    return redirect(url_for('revisione.coda'))
