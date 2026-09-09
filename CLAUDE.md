# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AmaldiStoria — Flask web app for the Liceo Edoardo Amaldi (Rome) documentation center. Digital archive of student enrollment statistics, geocoded addresses, oral history video interviews, and historical photos, built for the Liceo Amaldi / CNR-ISMed MDHLab project. Full description (Italian + English) in `README.md`.

UI strings, flash messages, code comments, and column names are Italian. Keep new code consistent with that.

## Commands

There is no test framework, linter, or build tooling. The single automated check is
`python test_toponimi.py` (plain `assert`s over `app/toponimi.py`); everything else is
verified by exercising the app.

```bash
# Setup (il .venv di questa copia non ha pip: usa uv, che è già sul PATH)
python3 -m venv .venv && source .venv/bin/activate
uv pip install --python .venv/bin/python -r requirements.txt

# Run dev server (reads FLASK_APP/FLASK_DEBUG from .flaskenv)
flask run

# Flask shell (auto-imports db, User, Alunno, Indirizzo, Strada — see amaldistoria.py)
flask shell

# L'unica verifica automatica del repo
python test_toponimi.py

# Import & geocoding pipeline (see "Import & geocodifica" below)
flask stradario-sync                        # street gazetteer (scarica da solo le mappe)
flask import-alunni data/input/<file>.xls   # one school year per file, idempotente
flask geocode --anno 2024-2025              # link students to street-level points
flask audit-geo                             # verifica: ogni alunno nel suo comune?
flask strade-cleanup                        # one-off historical cleanup, già eseguito
```

Requires local PostgreSQL with the PostGIS extension enabled; connection string comes from `DATABASE_URL` in `.flaskenv`.

**This working copy has no `.git`.** Don't assume git commands are available; check first.

**Migrazioni.** `migrations/` parte da `schema iniziale`, che ricostruisce lo schema **da
zero** (verificata su un database vuoto); il database di sviluppo era marcato lì con
`flask db stamp head`. Segue `collegamenti forzati`, che aggiunge
`rel_alunno_strada.forzato`. Tre trappole già disinnescate, da non reintrodurre:

- Flask-Migrate genera `geoalchemy2.types.Geometry` **senza importare `geoalchemy2`**: ogni
  migrazione che tocca una colonna `geom` va in `NameError`. L'import è già in
  `migrations/script.py.mako`, lascialo anche quando sembra inutilizzato.
- `migrations/env.py` ha un `include_object` che esclude `istat_comuni` e `osm_strade_raw`:
  sono dati derivati caricati da `ogr2ogr`, non modelli. Senza quel filtro il primo
  `flask db migrate` genererebbe un `drop_table()` per ciascuna, cancellando lo stradario.
- Lo stesso filtro esclude gli indici il cui nome contiene `geom` (fra cui
  `idx_strada_geom_add`, creato a mano anni fa): Alembic non li vede nei modelli e
  proporrebbe di cancellarli a ogni migrazione.

Il database aveva una `alembic_version` orfana che puntava a `b0440bf1454c`, revisione di
una storia di migrazioni perduta; è stata azzerata prima dello `stamp`.

## Version pinning — do not casually bump

`requirements.txt` pins a specific compatibility chain documented at its top:

- SQLAlchemy 1.4.x → Flask-SQLAlchemy must stay ≤2.5.1 (3.x needs SQLAlchemy 2.0) → Flask-Migrate must stay ≤3.1.0 → Flask must stay ≤2.3.x (Flask-SQLAlchemy 2.5.1 is untested on Flask 3.x).
- Upgrading Flask to 3.x requires first migrating all queries to SQLAlchemy 2.0 style. Don't bump Flask/Flask-SQLAlchemy/Flask-Migrate independently of each other.

`requirements.txt` also pins folium, plotly and numpy — **none of them are imported anywhere in `app/`** (pandas instead is used by the importer). Maps are plain Leaflet, charts are plain Highcharts (see below). Treat those three as legacy/unused rather than as the map or chart stack; `README.md` no longer lists them.

## Architecture

**Application Factory** pattern: `create_app()` in `app/__init__.py` wires up extensions (`app/extensions.py`: `db`, `migrate`, `login_manager`, `moment`, `bootstrap`), imports `app/models.py` inside an app context (required for Flask-Login's user_loader and for Alembic autogeneration to see the models), then registers three blueprints and Flask-Admin.

- **`app/main`** — all public routes (no url_prefix): home, static pages, statistics ("serie") pages, and the map views. Also hosts `/search/address`, a Nominatim geocoding proxy (geopy) consumed by the admin address-creation form.
- **`app/auth`** — `/auth/login`, `/auth/logout`, `/auth/register`, backed by Flask-Login. Note `/register` is `@login_required` and always creates users with role `rdr`.
- **`app/revisione`** — `/revisione`, sezione di manutenzione **solo `adm`**, per smaltire la
  coda degli indirizzi senza punto (TODO §1.3). Lavora per *gruppo*: una riga = una via +
  comune = tutti gli alunni che hanno scritto quell'indirizzo in qualunque annata. La coda si
  ricalcola dal DB a ogni richiesta, non si legge `data/esiti/da_rivedere_*.csv` (riscritto a
  ogni `flask geocode`). Due invarianti sono imposte qui, non solo suggerite: ogni
  collegamento passa per `_dentro_comune()` — anche una POST costruita a mano, non solo il
  bottone — e i candidati sono divisi fra **compatibili** (una regola di `toponimi.REGOLE` li
  lega alla via scritta) e il resto, che sta in un blocco chiuso. Quella separazione non è
  cosmetica: l'indice restituisce tutto ciò che condivide un token, quindi per
  `LAGO DI BOLSENA` propone anche `Via Lago di Bracciano`, e in una lista piatta l'errore
  finisce sotto il primo bottone.
  Terza via d'uscita, **il punto messo a mano sulla mappa**: OSM non è completo e per certe
  strade non c'è alcun candidato — `Via Raddusa` a Roma (45 alunni) non esiste nello
  stradario e Nominatim risponde vuoto, pur essendo una via vera in mezzo a un quartiere di
  toponimi siciliani che OSM ha (Troina, Riposto, Partanna). **Non è un problema di
  aggiornamento**: l'estratto Geofabrik è di settembre 2026, riscaricarlo non cambia nulla.
  Sono 60 gruppi / 250 alunni. Le righe create così si riconoscono da `osm_type='manuale'`
  (le altre hanno `way`, `node` o null) e passano per gli stessi due controlli delle altre:
  confine ISTAT e chiave `(via, CAP, comune)`. Una volta creata la riga, lo **stadio 2 di
  `geocode`** la riusa da sola a ogni import successivo: il lavoro manuale non si ripete.
  Lo sfondo ortofoto della mappa serve proprio a vedere il sedime dove la mappa vettoriale è
  vuota. Google è escluso: i termini di Maps Platform vietano di ricavarne coordinate da
  conservare in un dataset proprio, che è esattamente l'uso richiesto qui.
  La pagina di gruppo presenta **quattro card numerate**, che sono quattro fonti con
  affidabilità diversa e non quattro varianti della stessa cosa: 1 già in archivio (riusa un
  punto, non duplica) · 2 vie dello stradario del comune · 3 ricerca su Nominatim · 4 punto
  a mano. In fila come titoletti uguali erano indistinguibili, e non si capiva che la prima
  è sempre la scelta migliore.
  Forzatura, **«Collega comunque» / «Crea comunque» / «Salva comunque»**: il vincolo di
  comune resta imposto, ma scavalcabile con `forza=1` dopo una conferma esplicita. Serve
  perché oltre la tolleranza dei 100 m non esisteva alcuna uscita, e il caso legittimo c'è:
  il comune scritto dalla segreteria può essere **sbagliato**, e la via può essere davvero a
  cavallo del confine oltre la soglia — `Via Aci Platani`, che Nominatim descrive come
  «Municipio Roma VI, Villa Verde, Roma, Roma Capitale», ha il punto **145 m dentro
  Frascati**.
  Il bottone di forzatura sta **dove si agisce**, mai altrove: una casella globale era
  invisibile dalla card 3 e il flash di rifiuto mandava a una cosa che da lì non si vedeva.
  Perché ogni bottone possa già essere quello giusto serve sapere dove cade il punto
  *prima* del click: lo dice **`GET /revisione/dove`** (`comune` + `p=lat,lon` ripetuto, al
  più 10), che risponde `{comune, ok, metri}` per ciascun punto. `ok` passa da
  `_dentro_comune()`, tolleranza inclusa: una seconda nozione di «dentro» finirebbe per
  divergere da quella che poi rifiuta davvero il salvataggio. `metri` distingue a colpo
  d'occhio la via di confine (145 m) dall'omonimia di un'altra provincia (Aci Catena,
  658 km). Ogni risultato Nominatim porta così il suo badge e il suo bottone, e il punto
  messo a mano si verifica al click.
  Perché non riapra la porta agli 891 errori storici, la forzatura **si registra invece di
  nascondersi**: `rel_alunno_strada.forzato` la marca, il flash è `warning` e dice che
  `audit-geo` la elencherà, e `audit-geo` la elenca davvero in una sezione propria con la
  colonna `forzato` in `audit_geo.csv`. Senza quella colonna il primo `audit-geo --scollega`
  avrebbe cancellato in silenzio tutto il lavoro forzato a mano.
  Perché l'operatore possa decidere, la riga bloccata dice **dove cade davvero il punto**
  (`comune_punto`, un solo join `ST_Contains` per tutte le righe): «fuori comune» da solo non
  distingue una via di confine da un'omonimia a 47 km.
- **Flask-Admin** is *not* a blueprint — `app/admin_views.py` defines `ModelView` subclasses and registers them directly on an `Admin` instance via `configure_admin(app, db)`, called at the end of `create_app()`.

### Data model (`app/models.py`)

- `User` — app users with a role string checked ad hoc in each Flask-Admin view's `is_accessible()` (there is no centralized permission decorator). Roles: `adm` (everything incl. user management), `adv` (data + admin panel), `usr`, `rdr`. **`password_clear` stores the password in plaintext alongside `password_hash`** — deliberate in the existing admin flow (`CustomUser.on_model_change`); don't surface it in new views or templates.
- `Alunno` (`alunni` table) — one row per student enrollment-year record. `id_alunno` è la persona, `id` la riga: 11.360 persone in 47.932 righe. La chiave naturale è `(anno_ref, id_alunno)`, ed è quella che usa l'importer — ma nello storico esistono 38 doppie iscrizioni nello stesso anno (cambio classe o indirizzo in corso d'anno), quindi non è un vincolo di unicità in DB. Wide table of raw + "_norm" normalized columns (`esito_finale`/`esito_finale_norm`, `indirizzo_studi`/`indirizzo_studi_norm`, `sede`/`sede_norm`) — the `_norm` columns are the cleaned values views should generally read from, *except* the `serie_*` aggregation SQL, which deliberately pattern-matches the raw `indirizzo_studi` with `ILIKE '%LINGUIS%'` etc. Hybrid property `start_year` (Python: string split; SQL: `split_part` cast) for sorting/filtering by the school year's starting year.
- `Strada` (`strada` table) — geocoded street address with PostGIS `geom` (SRID 4326) plus raw OSM fields (`osm_*`) and denormalized `osm_lat`/`osm_lon`. Hybrid property `alunni_nr` counts linked students. Linked to `Alunno` via the many-to-many `rel_alunno_strada` association table.
- `rel_alunno_strada` — oltre alle due chiavi, la colonna **`forzato`** (`not null default false`): il collegamento è stato deciso a mano da `/revisione` contro il vincolo di comune. Va scritta dall'SQL grezzo degli insert, quindi il default è `server_default` e non un default lato Python, che quelle `text(...)` non intercetterebbe.
- `Indirizzo` (`indirizzo` table) — legacy per-student address table, kept only for backward compatibility; not actively used in new code (see the `# tabella da escludere` comment in the model).
- `Stradario` (`stradario` table) — l'elenco delle vie reali scaricato da OpenStreetMap, una riga per `(nome, comune)` con il baricentro. Non è dato del dominio: è l'anagrafe contro cui si normalizzano gli indirizzi scritti a mano. La tabella non nasce da una migrazione, la crea `stradario-sync` con `Stradario.__table__.create(..., checkfirst=True)`.

`anno_ref` is the school year as a `'1992-1993'` string and is the primary filter/group key everywhere. `'1992-1993'` is the hardcoded default year in `mapdata`; `map_graph` (la Dashboard) parte invece dall'anno più recente, `params[0]`, perché `params` è già ordinato `desc()`. Le annate coperte vanno dal 1992-1993 al 2025-2026.

`sede_norm` non è più vuota: `strade-cleanup` l'ha popolata su tutte le righe (`... SEDE SUCC.` → `SUCCURSALE`, il resto → `CENTRALE`). Nessuna vista la legge ancora.

### Map & statistics views (`app/main/views.py`)

Most data-heavy routes (`mapdata`, `mapdata_time`, `map_graph`, `serie_generale`, `serie_indirizzo`, `serie_stato`) bypass the ORM for the actual aggregation and run raw SQL via `db.engine.connect()` + `sqlalchemy.text(...)`, mixing PostgreSQL-specific constructs (`array_agg`, `PERCENTILE_CONT`, `ST_Distance`/`ST_Transform`) with GeoAlchemy2 for the PostGIS parts. When touching these, match the existing raw-SQL style rather than converting to ORM queries. Queries that filter geo data read `osm_lat`/`osm_lon` for the coordinates but still gate on `geom IS NOT NULL`.

Rendering is **server-prepared data → Jinja → inline JS**, no client-side API calls:

- Maps are hand-written **Leaflet** (plus markercluster and leaflet.heat) loaded from unpkg CDN inside each `map_*.html` template. Python builds `heat_data` (`[[lat, lon], ...]`), `cluster_data` (list of dicts), and `school_markers`, and the template interpolates them into a `<script>` block.
- Charts are **Highcharts** loaded from `code.highcharts.com` (the vendored `app/static/js/highcharts.js` is commented out in the templates; only `app/static/js/hc_theme.js` is actually used). The `serie_*` views pass dicts of parallel sequences, with the string `'null'` substituted for zero values so Highcharts renders a gap.
- `/territorio` (`map_territorio.html`) is just an embedded Google My Maps iframe, not app data.

Historical school locations (main building + three succursali/branch campuses, each active only in specific year ranges) are hardcoded in `_get_school_markers()` / `_get_all_school_markers()` at the bottom of `app/main/views.py` — the same year ranges are duplicated as Highcharts `plotbands` string literals in `serie_indirizzo` and `serie_stato`. Update all of them together if the school's site history data changes.

### Flask-Admin views (`app/admin_views.py`)

L'unico ingresso al pannello è `href="/admin"` nel menu utente di `base.html`, quindi
`HomeView` (la index di Flask-Admin) deve restare navigabile: un override di `admin_index`
che rimanda al sito rende il pannello irraggiungibile da tutti i ruoli, e sembra un problema
di permessi senza esserlo. Il controllo d'accesso vero è `is_accessible()` su ogni vista,
`adm`/`adv` a seconda dei casi; chi non passa viene mandato a `/auth/login` anche se è già
autenticato.

Five views over three models, several registered on the *same* model with different endpoints and purposes — read the `endpoint=` argument in `configure_admin`, not the class name:

- `customAlunno` (`Alunno`) — read-only browse of enrollment records.
- `AlunnoResidenza` (`Alunno`, endpoint `alunno_residenza`) — links a student to `Strada` rows via ajax refs.
- `ResidenzaAlunno` (`Strada`, endpoint `residenza_alunno`) — the inverse: links many students to one address, all `osm_*` fields readonly.
- `StradaAdmin` (`Strada`, endpoint `strada_admin`) — creates addresses through the `admin/strada_create.html` template, which calls `/search/address`, writes the picked Nominatim result into a hidden `selected_address` field, and lets `create_model()` build the PostGIS point via shapely `from_shape`.

### Import & geocodifica (`app/importer.py`, `app/toponimi.py`)

The school hands over a Spaggiari/Infoschool `.xls` export per school year. Four Flask CLI
commands, registered on the app in `create_app()` via `registra_cli`:

| comando | fa |
|---|---|
| `flask stradario-sync` | costruisce l'elenco delle vie reali: strade OSM del Centro Italia da Geofabrik + confini comunali ISTAT, caricati in PostGIS con `ogr2ogr`. Una riga per `(via, comune)` col baricentro. I file restano in `data/stradario_cache/`, `--riscarica` per rinnovarli |
| `flask import-alunni <xls>` | importa un'annata; chiave `(anno_ref, id_alunno)`, le righe già presenti sono saltate e registrate in `data/log_import_<anno>.csv` |
| `flask geocode --anno <a>` \| `--tutti` | collega gli alunni a una `strada`, scrive `esiti/correzioni_<anno>.csv` e `esiti/da_rivedere_<anno>.csv` |
| `flask audit-geo` | verifica che ogni alunno stia dentro il comune dichiarato; `--scollega` rimuove i collegamenti sbagliati, **tranne quelli forzati** |
| `flask strade-cleanup` | una tantum, già eseguito: azzera i civici, unifica i doppioni `(via, CAP, comune)`, popola `sede_norm` |

**Procedura per una nuova annata**, nell'ordine — è la stessa documentata nel README per
gli utenti non tecnici:

```bash
# 1. il file .xls va in data/input/, senza rinominarlo (l'anno si legge dal nome)
flask stradario-sync                             # 2. solo la prima volta e una volta l'anno
flask import-alunni data/input/<file>.xls        # 3. idempotente, rilanciabile
flask geocode --anno 2024-2025                   # 4. ~15-25 min, 1 richiesta/secondo
flask audit-geo                                  # 5. verifica, non modifica nulla
```

**Verifiche dopo un import** — nessuna di queste deve tornare valori:

```sql
-- civici salvati (violerebbe la regola di privacy)
select count(*) from strada where osm_house_number is not null
   and osm_house_number not in ('', 'empty');
-- doppioni sulla chiave naturale
-- il comune e' quello che contiene il punto: osm_city riporta Nominatim e a volte sbaglia
select count(*) from (select s.osm_road, coalesce(s.osm_postcode,''), coalesce(c.comune,'')
   from strada s left join istat_comuni c on ST_Contains(c.geom, s.geom)
   group by 1,2,3 having count(*)>1) t;
-- `strada` senza geometria: un collegamento a una di queste colloca l'alunno da nessuna parte
select count(*) from strada where geom is null;
```

Le forzature invece **si contano, non si azzerano**: vanno lette, non fatte sparire.

```sql
select s.osm_road, a.comune_residenza, count(*)
from rel_alunno_strada r
join strada s on s.id = r.strada_id
join alunni a on a.id = r.alunno_id
where r.forzato group by 1,2 order by 3 desc;
```

e la copertura, che va confrontata con la precedente:

```sql
select anno_ref, count(*) as alunni,
  count(*) filter (where exists (select 1 from rel_alunno_strada r where r.alunno_id = a.id)) as geo
from alunni a group by 1 order by 1;
```

Attenzione a come si legge quel conteggio: fino a settembre 2026 era **gonfiato**. In
archivio c'era una riga `strada` completamente vuota (nessuna via, nessuna geometria) usata
storicamente come segnaposto per "indirizzo non risolto", e **3.570 alunni erano collegati a
quella**: risultavano geocodificati in ogni statistica senza avere un punto. `audit-geo` la
segnala esplicitamente; la riga è stata eliminata e quegli alunni rigeocodificati.

`anno_ref` non è nel file: si deduce dal nome (`AC_2024-25` → `2024-2025`) o si passa con `--anno`.
I `.xls` di Spaggiari hanno un header OLE che manda in errore xlrd, quindi si leggono con
`engine_kwargs={'ignore_workbook_corruption': True}` — il contenuto è integro.

**Perché due file interi invece di un'API.** La prima versione del sync interrogava Overpass
un comune per volta: ~40 query pesanti in sequenza, l'istanza pubblica ha iniziato a
rispondere 429/504 e ha finito per **rifiutare l'IP**, facendo perdere Roma — da sola il 97,3%
degli indirizzi — e uscendo con codice 0 come se fosse andato tutto bene. Da lì la scelta di
scaricare per intero le due sorgenti: nessun limite di frequenza, nessun ban possibile, e lo
stesso risultato a ogni esecuzione. I confini ISTAT sono anche più precisi delle aree
amministrative OSM per attribuire il comune.

Il comune di una via si determina con `ST_Contains(comune, ST_PointOnSurface(strada))`:
`ST_PointOnSurface` cade sempre sulla linea, mentre il baricentro di una strada a U può
finire nel comune accanto. Il download è atomico (file `.parziale` rinominato solo a fine
scaricamento con verifica del `Content-Length`), altrimenti un'interruzione lascerebbe in
cache un file troncato che il lancio successivo userebbe come valido.

**Privacy**: si geocodifica solo il nome della via, mai il civico. `strada.osm_house_number`
non va più valorizzato: `strade-cleanup` l'ha azzerato su tutto lo storico e riportato i punti
sulla via. Non reintrodurlo nell'importer.

**Perché non un match per similarità di stringa** (`app/toponimi.py`): sui dati reali la
soglia mette la coppia sbagliata sopra quella giusta —
`'VIA G. LONGHI'`/`'VIA GIUSEPPE LONGHI'` sta a 0.750, `'VIA LONGI'`/`'VIA LONGO'` a 0.889.
Il confronto è quindi per token, con quattro regole in ordine di sicurezza decrescente:
esatta → abbreviazione (`G` ≡ `GIUSEPPE`) → sottoinsieme → refuso. Il refuso ammette solo
inserimenti e sostituzioni **interne**: cambiare l'ultima lettera distingue due cognomi
italiani (Longi/Longo, Rossi/Rosso), non li corregge. Ogni regola richiede un candidato
unico; altrimenti il caso finisce in coda di revisione, mai indovinato.

Due false ambiguità vengono assorbite perché OSM alterna le grafie sulla stessa via: le
maiuscole (`Via Fontana Delle Cannetacce` / `Via Fontana delle Cannetacce`) e il prefisso
agiografico, dove `S.`, `San`, `Sant'`, `Santo`, `Santa` e `Santi` collassano tutti su `SAN`
(la `S` isolata no: può essere l'iniziale di un nome, e come iniziale la tratta già la regola
di abbreviazione). Il **tipo invece conta**: `Via delle Cisternole` e `Vicolo delle Cisternole`
hanno gli stessi token e sono due strade diverse, quindi restano ambigue.

**Vincolo di località, tre livelli.** Nominatim, quando non trova la via nel comune
richiesto, **non risponde "non trovata": allenta il vincolo** e restituisce l'omonima
altrove. Servono tutti e tre i controlli:

1. `_nominatim()` rifiuta di interrogare senza almeno un comune o un CAP, e scarta un
   risultato oltre 120 km dalla scuola quando il comune non era dichiarato. Senza questo,
   «Via degli Ulivi» col solo nome finisce vicino a Milano — è successo.
2. `geocode` verifica poi che il punto cada **dentro il confine ISTAT del comune
   dichiarato** (`_dentro_comune`). La soglia dei 120 km non basta: «Via dei Giardinetti» di
   Roma tornava come quella di Nerola, 47 km, dentro soglia. Il giudice è il confine, non il
   nome di città restituito, che spesso è una frazione (`Setteville` per Guidonia) e
   boccerebbe risultati giusti.
   Il confine si prende con **`TOLLERANZA_CONFINE_M = 100`** di margine
   (`ST_Contains OR ST_DWithin(::geography, 100)`). Non è un allentamento del vincolo: quello
   che si salva è il **baricentro** della via, e su una strada a cavallo del confine il
   baricentro cade dall'altra parte. `Via Torre dello Stinco` è Roma per OSM e per la
   segreteria, e i suoi due punti stanno **0,4 m** e **30 m** dentro Frascati: senza margine
   erano irrecuperabili, 17 alunni bloccati senza alcuna via d'uscita. Le omonimie vere, che
   sono l'errore da fermare, stanno a chilometri — verificato che Nerola, Anzio e Pomezia
   restano rifiutate. Alzarla di molto le riammette: non toccarla senza rifare quella prova.
3. Lo **stadio di riuso** di `geocode` applica lo stesso confine alle `strada` già in
   archivio (`_prima_nel_comune`): senza, bastava che il CAP combaciasse per agganciare la
   via omonima del comune accanto — 132 collegamenti sbagliati, fra cui 17 studenti romani
   sulla `Via Casilina` di Monte Compatri, che è una via davvero a cavallo dei due comuni.
   Da qui la chiave naturale di `strada`: `(via, CAP, comune)`, non `(via, CAP)`, dove il
   comune è quello che **contiene il punto** e non `osm_city` (che riporta Nominatim e a
   volte sbaglia: la `Via Osini` di Monte Compatri era salvata come 'Roma').
   Anche il ripiego sul baricentro dello stradario obbedisce al vincolo: `_riga_stradario()`
   restituisce solo vie del comune dichiarato, mai l'unica omonima altrove — quel ripiego da
   solo produceva 67 dei 132 collegamenti sbagliati (`Via Capizzi` di uno studente di
   Frascati sulla Via Capizzi di Roma).

`flask audit-geo` applica lo stesso controllo a tutto l'archivio. Alla prima esecuzione ha
trovato **891 collegamenti storici nel comune sbagliato** su 67 vie — omonimie fatte a mano
negli anni: 134 alunni di `Via Santa Rita da Cascia` puntati a Pomezia, 105 di `Via Anteo`
ad Anzio, 48 di `Via dei Giardinetti` a Nerola. Applica anche la stessa tolleranza sul
confine, altrimenti segnalerebbe come errori le vie di confine che `geocode` ora accetta, e
tiene i **collegamenti forzati** (vedi `app/revisione`) in una sezione a parte: sono decisioni prese
guardando il caso, non errori, e `--scollega` non li rimuove.

`chiave()` confronta senza il tipo (la segreteria lo omette spesso), `via_pulita()` lo
mantiene ed è ciò che si salva in `alunni.via`. `toponimi.chiave_comune()` rende confrontabili
`MONTECOMPATRI`, `MONTE COMPATRI` e `Monte Compatri`, che sono lo stesso comune.

`stradario.nome_norm` esiste in tabella ma **non va letto**: `_carica_stradario()` lo
ricalcola a ogni caricamento (0,7s su ~5.000 vie). La colonna conserva la normalizzazione in
vigore al momento del sync, e ogni modifica alle regole in `toponimi.py` la renderebbe
obsoleta senza che nulla lo segnali.

Modificando `toponimi.py` si aggiorna anche `test_toponimi.py`: i casi lì dentro sono
indirizzi veri presi dai file della segreteria, non esempi inventati.

**Le sette regole di confronto** (`REGOLE` in `toponimi.py`, in ordine di sicurezza
decrescente; ci si ferma alla prima che aggancia, e ognuna pretende un candidato unico):

| regola | esempio | il freno che la tiene |
|---|---|---|
| `esatta` | — | — |
| `spaziatura` | `ROCCA MORICE` ≡ `Roccamorice` | nessuna lettera cambia, solo dove cade lo spazio |
| `preposizione` | `DEI GIARDINETTI` ≡ `di Giardinetti` | tolte le preposizioni il resto deve coincidere token per token |
| `abbreviazione` | `G. LONGHI` ≡ `Giuseppe Longhi` | stessa lunghezza, e la sigla è l'iniziale |
| `sottoinsieme` | `CHIODELLI` ⊂ `Raoul Chiodelli` | solo in un verso: token in meno sì, in più no |
| `refuso` | `MONTEMILITTO` ≡ `Montemiletto` | un carattere, interno; l'ultimo distingue i cognomi (Longi/Longo) |
| `carattere perduto` | `MATT?` ≡ `Mattè` | il `?` vale una lettera sola, lunghezze uguali |
| `troncamento` | `ARCH. DI TORRENOVA` ≡ `degli Archetti di Torrenova` | il **punto** è il permesso: senza, niente confronto per prefisso, e minimo 4 lettere scritte |

`_Indice` ha tre chiavi perché queste regole possano incontrare un candidato: per token, per
prefisso di 4 lettere dell'ultimo token (i refusi: `MONTEMILITTO` non è nell'indice, `MONT`
sì) e per nome **senza spazi** (`ROCCA MORICE` e `ROCCAMORICE` non hanno nemmeno un token
in comune).

Sopra le regole c'è un **secondo passaggio per il doppio tipo**: `VIA LARGO FERRUCCIO
MENGARONI`, dove la segreteria antepone `VIA` a un toponimo che il tipo ce l'ha già. Il
primo token si toglie solo se è un tipo e solo contro i candidati **di quel tipo**: 61 vie
vere dello stradario cominciano con due tipi (`Via Ponte Lucano`, `Via Piazza Armerina`) e
la regola scritta com'era nel TODO — «se il 2° token è un tipo, vince quello», dentro
`normalizza()` — le avrebbe storpiate tutte.

Ogni allargamento del confronto è il modo in cui si torna ad accoppiare `LONGI` con `LONGO`:
si fa con `test_toponimi.py` davanti, scrivendo **prima il caso negativo** e poi la regola.

### Templates

`app/templates/` is the live template tree (Jinja2, extends `base.html`, Bootstrap 5 via CDN + `static/css/assets/amaldi.css`). `app/templates_bk/` is a backup/scratch copy and `*_BK.html` files are stale duplicates — don't edit them expecting the running app to change.

### Data & backlog

`data/` è divisa per natura del contenuto, non per comando che la produce — vedi
[`data/README.md`](data/README.md), scritto per utenti non tecnici:

| cartella | contenuto | chi la riempie |
|---|---|---|
| `data/input/` | export `.xls` della segreteria, uno per anno scolastico | una persona |
| `data/geo/` | Geofabrik (~750 MB) e ISTAT (~12 MB) scaricati, più gli estratti | `stradario-sync`, da solo |
| `data/esiti/` | log di import, correzioni applicate, code di revisione, audit | i comandi |

`data/geo/` è **solo una cache**: si può cancellare, viene riscaricata. `data/esiti/` viene
riscritta a ogni esecuzione.

`AGGIORNAMENTI.md` is the project's running Italian to-do list (funzionalità, contenuti).
`TODO.md` è il lavoro tecnico aperto, con i numeri misurati: il bug del riuso che non
verifica il comune, le lacune del normalizzatore, la coda di revisione e il debito
preesistente. Leggilo prima di ripartire sulla pipeline di import.

### Deployment

Production runs under Apache + mod_wsgi. `WSGIApplicationGroup %{GLOBAL}` is required in the Apache vhost to avoid conflicts between mod_wsgi and C extensions (PostGIS/GeoAlchemy2) — see `README.md` for the full vhost example and the required `amaldiapp.wsgi` shape.
