# AmaldiStoria

**Centro di Documentazione del Liceo Edoardo Amaldi di Roma**

> Un progetto del [Liceo Amaldi di Roma](https://www.liceo-amaldi.edu.it/) e del [CNR — ISMed](https://www.ismed.cnr.it/),
> realizzato nell'ambito delle attività del [MDHLab](http://mdhlab.cnr.it/).

---

*[Italiano](#italiano) · [English](#english)*

---

## Italiano

### Descrizione del progetto

AmaldiStoria è un'applicazione web Flask sviluppata per supportare il **Centro di Documentazione del Liceo Edoardo Amaldi** di Roma (Tor Bella Monaca). Il progetto nasce nel 2021 dalla collaborazione tra il Liceo Amaldi e il **CNR — Istituto di Studi sul Mediterraneo**, nell'ambito delle attività del *Mediterranean Digital Humanities Lab* (MDHLab).

L'obiettivo è costruire uno spazio digitale ragionato per la raccolta, gestione e visualizzazione di fonti statistiche, documentarie, orali e cartografiche relative alla storia dell'istituto e al suo rapporto con il territorio circostante. Lo strumento è pensato sia per la ricerca accademica sia, e soprattutto, per la didattica attiva, favorendo un approccio laboratoriale allo studio della storia.

### Funzionalità principali

- **Serie statistiche** — grafici interattivi (Highcharts) sugli iscritti per anno scolastico, genere, nazionalità, indirizzo di studi, abbandoni e trasferimenti
- **Mappe interattive** — distribuzione geografica degli iscritti per anno, heatmap e cluster (Leaflet), con evoluzione temporale animata
- **Voci della memoria** — raccolta di interviste video a docenti e ex-studenti
- **Archivio immagini** — fondi fotografici storici dell'istituto
- **Pannello di amministrazione** — gestione dati via Flask-Admin con accesso basato su ruoli

### Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.10, Flask 2.3.x (vincolato: vedi `requirements.txt`) |
| ORM | SQLAlchemy 1.4 + Flask-SQLAlchemy |
| Database | PostgreSQL con estensione PostGIS |
| Migrazioni | Alembic / Flask-Migrate |
| Autenticazione | Flask-Login |
| Frontend | Bootstrap 5, Bootstrap Icons |
| Mappe | Leaflet.js (heatmap, cluster, timeline) |
| Grafici | Highcharts |
| Geodati | OpenStreetMap via Geofabrik, confini comunali ISTAT, geocodifica Nominatim |
| Admin | Flask-Admin |
| Deployment | Apache + mod_wsgi |

### Struttura del repository

```
amaldistoria/
├── amaldistoria.py          # Entry point Flask (FLASK_APP)
├── config.py                # Configurazione (Config class)
├── .flaskenv                # Variabili d'ambiente di sviluppo
├── requirements.txt         # Dipendenze Python
├── README.md
│
├── app/                     # Pacchetto principale dell'applicazione
│   ├── __init__.py          # create_app() — Application Factory
│   ├── extensions.py        # Istanze delle estensioni Flask
│   ├── models.py            # Modelli SQLAlchemy
│   ├── forms.py             # Form WTForms
│   ├── admin_views.py       # Viste e configurazione Flask-Admin
│   │
│   ├── main/                # Blueprint principale
│   │   ├── __init__.py
│   │   └── views.py         # Route pubbliche e dati
│   │
│   ├── auth/                # Blueprint autenticazione
│   │   ├── __init__.py
│   │   └── views.py         # Login, logout, registrazione
│   │
│   ├── revisione/           # Blueprint manutenzione indirizzi (solo ruolo adm)
│   │   ├── __init__.py
│   │   └── views.py         # Coda, candidati, punto a mano sulla mappa
│   │
│   ├── static/
│   │   ├── css/assets/      # CSS applicazione (amaldi.css)
│   │   ├── js/              # JavaScript custom
│   │   └── img/             # Immagini, loghi, carousel
│   │
│   ├── toponimi.py          # Normalizzazione degli indirizzi (logica pura, testabile)
│   ├── importer.py          # Comandi CLI: import, stradario, geocodifica, verifiche
│   │
│   └── templates/
│       ├── base.html        # Template base (Bootstrap 5)
│       ├── _macros.html     # Macro Jinja2 (carousel, ecc.)
│       ├── index.html
│       ├── voci.html
│       ├── immagini.html
│       ├── presentazione.html
│       ├── serie_generale.html
│       ├── serie_indirizzo.html
│       ├── serie_stato.html
│       ├── map.html
│       ├── map_studenti.html
│       ├── map_studenti_time.html
│       ├── map_graph.html
│       ├── map_territorio.html
│       ├── auth/
│       │   ├── login.html
│       │   └── register.html
│       ├── admin/
│       │   └── strada_create.html
│       └── revisione/
│           ├── coda.html    # Le vie da decidere, per peso
│           └── gruppo.html  # Un caso: candidati, ricerca, mappa
│
├── migrations/              # Versioni Alembic (schema del database)
├── test_toponimi.py         # L'unica verifica automatica del progetto
│
└── data/
    ├── README.md            # Guida dettagliata alla cartella
    ├── input/               # I file .xls consegnati dalla scuola  ← li metti tu
    ├── geo/                 # Mappe scaricate (Geofabrik, ISTAT)   ← si riempie da sola
    └── esiti/               # Log, correzioni, code di revisione   ← si riempie da sola
```

La cartella `data/` ha una sua guida in [`data/README.md`](data/README.md): spiega cosa
va messo a mano e cosa invece si scarica da solo.

### Architettura Blueprint

L'applicazione usa il pattern **Application Factory** (`create_app()`) con tre Blueprint:

- **`main`** — tutte le route pubbliche (`/`, `/serie-generale`, `/map`, ecc.) e l'API di geocodifica
- **`auth`** — gestione dell'autenticazione (`/auth/login`, `/auth/logout`, `/auth/register`)
- **`revisione`** — `/revisione`, la sezione di manutenzione degli indirizzi, **riservata al ruolo `adm`**

Flask-Admin è configurato separatamente in `admin_views.py` tramite la funzione `configure_admin(app, db)`, richiamata dentro `create_app()`. I ModelView Flask-Admin non sono Blueprint e vengono registrati direttamente sull'istanza `Admin`.

### Modello dei dati

I modelli principali sono:

- **`User`** — utenti dell'applicazione con sistema di ruoli (`adm`, `adv`, `usr`, `rdr`)
- **`Alunno`** — record degli iscritti (anno scolastico, genere, nazionalità, indirizzo di studi, esito finale)
- **`Strada`** — indirizzi geocodificati (coordinate PostGIS + dati OSM), collegati agli alunni via tabella di associazione `rel_alunno_strada`
- **`Indirizzo`** — indirizzi legacy (mantenuti per compatibilità)

### Installazione e sviluppo locale

**Prerequisiti:**
- Python 3.10+
- PostgreSQL con estensione PostGIS installata
- `pip`

**Setup:**

```bash
# 1. Clona il repository
git clone <url-repo>
cd amaldistoria

# 2. Crea e attiva un virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 3. Installa le dipendenze
pip install -r requirements.txt

# 4. Configura le variabili d'ambiente
# Modifica .flaskenv con i valori corretti:
#   FLASK_APP=amaldistoria
#   FLASK_DEBUG=1
#   SECRET_KEY=<chiave-segreta>
#   DATABASE_URL=postgresql://user:password@localhost/amaldistoria

# 5. Crea le tabelle del database
flask db upgrade

# 6. Avvia il server di sviluppo
flask run
```

Per caricare i dati degli studenti e geolocalizzarli, vedi
[Caricare i dati di un nuovo anno scolastico](#caricare-i-dati-di-un-nuovo-anno-scolastico).

**Nota sull'ambiente Python:** se `pip` non è disponibile dentro `.venv`, si può usare
[uv](https://github.com/astral-sh/uv):
`uv pip install --python .venv/bin/python -r requirements.txt`.

**Verifica automatica:** `python test_toponimi.py` controlla le regole di
riconoscimento degli indirizzi su casi reali presi dai file della segreteria. Va
rilanciato dopo ogni modifica a `app/toponimi.py`.

### Caricare i dati di un nuovo anno scolastico

Questa è la procedura da seguire quando la scuola consegna l'export di una nuova annata.
È pensata per essere eseguita anche da chi non ha mai usato un terminale: sono cinque
comandi, in quest'ordine, e ognuno dice cosa ha fatto.

Prima di cominciare, apri il Terminale, entra nella cartella del progetto e attiva
l'ambiente Python (questo va rifatto ogni volta che apri una finestra nuova):

```bash
cd /percorso/della/cartella/amaldistoria
source .venv/bin/activate
```

Se il prompt inizia a mostrare `(.venv)`, sei pronto.

#### Passo 1 — Metti il file al suo posto

Copia il file `.xls` che ti ha dato la scuola dentro **`data/input/`**.
Non rinominarlo: il nome contiene l'anno scolastico e il programma lo legge da lì.

```
data/input/RMII0063_AC_2024-25_data22-06-2026_ore21_19_02.xls
                     └──┬──┘
                        └── da qui il programma capisce che è l'anno 2024-2025
```

#### Passo 2 — Prepara le mappe (solo la prima volta, poi una volta l'anno)

```bash
flask stradario-sync
```

Questo comando costruisce l'elenco delle vie reali contro cui verranno riconosciuti gli
indirizzi scritti a mano dalla segreteria.

**Non devi scaricare niente a mano.** Il comando controlla se le mappe sono già in
`data/geo/` e, se mancano, se le scarica da solo da due fonti pubbliche: OpenStreetMap
via Geofabrik (~750 MB, le strade) e ISTAT (~12 MB, i confini dei comuni). Il primo
download richiede qualche minuto a seconda della connessione; i lanci successivi non
riscaricano nulla e durano un paio di minuti.

Se un giorno vuoi aggiornare le mappe con le vie nuove, aggiungi `--riscarica`.
Una volta l'anno è più che sufficiente.

#### Passo 3 — Importa gli studenti

```bash
flask import-alunni data/input/RMII0063_AC_2024-25_data22-06-2026_ore21_19_02.xls
```

Il comando risponde con quante righe ha inserito e quante ne ha saltate. Salta quelle già
presenti in archivio, riconoscendole dalla coppia anno scolastico + identificativo dello
studente: **puoi rilanciarlo senza paura, non crea doppioni.**

Se vuoi vedere cosa farebbe senza toccare l'archivio, aggiungi `--dry-run`.

#### Passo 4 — Collega gli studenti alle vie sulla mappa

```bash
flask geocode --anno 2024-2025
```

È il passo più lento: interroga un servizio pubblico di geolocalizzazione rispettandone
i limiti d'uso (una richiesta al secondo), quindi per una annata intera possono volerci
15-25 minuti. Non spegnere il computer nel frattempo.

A fine lavoro stampa un riepilogo di questo tipo:

```
Alunni collegati: 2082
  corretta (abbreviazione)     23     ← "VIA G. MARCONI" riconosciuta come "Via Guglielmo Marconi"
  corretta (refuso)            17     ← "VIA MONTEMILITTO" corretta in "Via Montemiletto"
  riuso                      1606     ← indirizzi già noti, nessuna richiesta a internet
  nuova via (nominatim)       369     ← vie nuove, cercate su internet
  ambigua                       4     ← più vie possibili: decide una persona
  non risolta                  45     ← non trovate: decide una persona
```

#### Passo 5 — Controlla il lavoro

```bash
flask audit-geo
```

Verifica che ogni studente sia collocato **dentro il comune che ha dichiarato**. È un
controllo che vale la pena fare sempre, perché il servizio di geolocalizzazione, quando
non trova una via nel comune richiesto, non risponde "non l'ho trovata": restituisce una
via con lo stesso nome da un'altra parte. `Via dei Giardinetti` di Roma tornava come
quella di Nerola, 47 km più in là.

Se trova problemi, `flask audit-geo --scollega` rimuove i collegamenti sbagliati; poi si
rilancia `flask geocode --tutti` per rifarli correttamente.

#### Passo 6 — Leggi cosa il programma non ha saputo fare

Nella cartella `data/esiti/` trovi dei file CSV apribili con Excel. Il più importante è
**`da_rivedere_<anno>.csv`**: contiene gli indirizzi che richiedono una decisione umana,
ordinati per numero di studenti coinvolti, così si parte da quelli che pesano di più.

Per ciascuno vedi l'indirizzo grezzo, il CAP, il comune e — quando ce ne sono — le vie
che il programma considerava possibili. Sono casi in cui **indovinare sarebbe peggio che
fermarsi**: `VIA ROSSINI` a Roma può essere Via Luigi Rossini, Via Carlo Conti Rossini o
Viale Gioacchino Rossini, e sono tre punti diversi della città.

Si smaltiscono dalla pagina **Revisione indirizzi** (menù utente in alto a destra,
visibile agli amministratori). Il file CSV serve a farsi un'idea; la pagina è il posto
dove si lavora, perché:

- ragiona per **via**, non per studente: `VIA RADDUSA 55` e `VIA RADDUSA, 12` sono una
  decisione sola che sistema tutti gli studenti di tutte le annate;
- propone i candidati già pronti, separando quelli che il programma riconosce come la
  stessa via da quelli che hanno solo qualche parola in comune;
- **rifiuta** un collegamento il cui punto cade fuori dal comune dichiarato dallo studente.

Ci sono tre modi per chiudere un caso: collegarlo a un indirizzo già in archivio,
crearlo da una via reale del comune, oppure — se la via non esiste in nessuna fonte —
metterne il punto a mano sulla mappa (vedi sotto).

Vale la pena scorrere anche `correzioni_<anno>.csv`, che elenca le correzioni fatte in
automatico: serve a controllare a campione che siano giuste.

---

### Come vengono riconosciuti gli indirizzi

Gli indirizzi arrivano scritti a mano e sono pieni di abbreviazioni, refusi e formati
diversi: `VIA OLLOLAI, 99/C`, `VIA G.B.BASTIANELLI, 24`, `VIA MATTE TRUCCO N.71`,
`CASTELVETRANO 72 B`. Il programma li riconduce alla via reale in cinque passaggi, dal
più economico al più costoso:

1. **Pulizia** — via il numero civico, le abbreviazioni sciolte (`L.GO` → `LARGO`), gli
   apostrofi uniformati.
2. **Stradario** — la via viene cercata nell'elenco delle vie reali del comune.
3. **Riuso** — se quella via con quel CAP è già in archivio, si riusa: nessuna richiesta
   a internet. È il caso più frequente, circa due terzi.
4. **Ricerca su internet** — solo per le vie nuove, e solo con il nome già ripulito.
5. **Coda di revisione** — quello che resta viene messo in un file, non indovinato.

Il confronto **non** si basa sulla somiglianza fra le stringhe, per un motivo preciso:
misurata sui dati reali, la somiglianza mette la coppia sbagliata sopra quella giusta.

```
0.750   'VIA G. LONGHI'  e  'VIA GIUSEPPE LONGHI'    ← è la stessa via
0.889   'VIA LONGI'      e  'VIA LONGO'              ← sono due vie diverse
```

Qualunque soglia accetti la prima accetta anche la seconda. Il confronto avviene quindi
parola per parola, con sette regole applicate in ordine, dalla più sicura alla più
rischiosa. Ci si ferma alla prima che aggancia, e **ognuna pretende che il candidato sia
uno solo**: se restano due vie possibili, il caso va in revisione invece di essere
indovinato.

| regola | esempio | perché è sicura |
|---|---|---|
| esatta | — | — |
| spaziatura | `ROCCA MORICE` = `Roccamorice` | non cambia una lettera, solo dove cade lo spazio |
| preposizione | `DEI GIARDINETTI` = `di Giardinetti` | tolte di/del/dei/degli, il resto deve coincidere |
| abbreviazione | `G. LONGHI` = `Giuseppe Longhi` | l'iniziale puntata si espande, il cognome no |
| sottoinsieme | `CHIODELLI` ⊂ `Raoul Chiodelli` | vale solo in un verso: parole in meno sì, in più no |
| refuso | `MONTEMILITTO` = `Montemiletto` | **una** lettera, e in mezzo alla parola |
| carattere perduto | `MATT?` = `Mattè` | il `?` di una codifica sbagliata vale una lettera |
| troncamento | `ARCH. DI TORRENOVA` = `degli Archetti di Torrenova` | serve il punto: senza, niente confronto per prefisso |

La regola del refuso merita una nota: cambiare l'**ultima** lettera in italiano non è un
errore di battitura, è un altro cognome — Longi/Longo, Rossi/Rosso, Bianchi/Bianco — e
infatti non viene corretta. Vale lo stesso per il troncamento: `ARCH.` può diventare
`Archetti` perché il punto dichiara che la parola è tagliata, ma `ARCH` senza punto no.

### Quando la via non esiste in nessuna fonte

Capita, ed è più comune di quanto sembri: **OpenStreetMap non è completo**. `Via Raddusa`
a Roma è una via vera, in mezzo a un quartiere di strade intitolate a comuni siciliani che
OpenStreetMap conosce — Troina, Riposto, Partanna, tutte a poche decine di metri — ma di
Raddusa non c'è traccia, e il servizio di geolocalizzazione non risponde. Sono 45 studenti
su un indirizzo solo.

Non è un problema di dati vecchi: le mappe vengono riscaricate e il risultato non cambia.
Per questi casi — una sessantina di indirizzi, circa 250 studenti — la pagina *Revisione
indirizzi* ha la sezione **«Metti il punto a mano»**: una mappa con le vie già note
segnate intorno e uno sfondo di ortofoto, dove si vede il tracciato della strada anche
dove la mappa disegnata è vuota. Si clicca il punto e si salva.

Il controllo sul comune resta identico anche qui: un punto messo fuori dal comune
dichiarato dallo studente viene rifiutato. E il lavoro **non si ripete**: una volta che
la via è in archivio, gli import degli anni successivi la riusano da soli.

### Privacy: perché non si registra il numero civico

Il progetto tratta dati di minori. La geolocalizzazione si ferma **al nome della via**:
il numero civico non viene mai salvato né usato per calcolare il punto sulla mappa. Un
punto per via, non per portone, così le mappe pubbliche mostrano la distribuzione sul
territorio senza rendere rintracciabile dove abita un singolo studente.

Questa regola vale anche all'indietro: i 170 indirizzi storici che erano stati
geolocalizzati sulla casa esatta sono stati riportati sulla via.

### Configurazione PostgreSQL/PostGIS

```sql
-- Crea il database
CREATE DATABASE amaldistoria;

-- Abilita PostGIS
\c amaldistoria
CREATE EXTENSION postgis;
```

La connessione va specificata in `.flaskenv` come:
```
DATABASE_URL=postgresql://utente:password@localhost:5432/amaldistoria
```

### Deployment Apache + mod_wsgi

Esempio di configurazione Apache (`_amaldi.conf`):

```apache
<VirtualHost *:80>
    ServerName amaldistoria.example.it

    WSGIDaemonProcess amaldistoria python-home=/path/to/venv \
        python-path=/path/to/amaldistoria
    WSGIProcessGroup amaldistoria
    WSGIApplicationGroup %{GLOBAL}
    WSGIScriptAlias / /path/to/amaldistoria/amaldiapp.wsgi

    <Directory /path/to/amaldistoria>
        Require all granted
    </Directory>

    Alias /static /path/to/amaldistoria/app/static
    <Directory /path/to/amaldistoria/app/static>
        Require all granted
    </Directory>
</VirtualHost>
```

**Nota:** `WSGIApplicationGroup %{GLOBAL}` è necessario per evitare conflitti con estensioni C come NumPy/PostGIS.

Il file `amaldiapp.wsgi` deve importare `create_app`:

```python
import sys
sys.path.insert(0, '/path/to/amaldistoria')
from app import create_app
application = create_app()
```

### Sistema di ruoli

| Ruolo | Codice | Accesso |
|---|---|---|
| Amministratore | `adm` | Tutto: gestione utenti e sezione *Revisione indirizzi* |
| Avanzato | `adv` | Dati, mappe, pannello admin (no utenti, no revisione) |
| Utente | `usr` | Aree protette del sito |
| Lettore | `rdr` | Aree protette in sola lettura |

### Coordinamento del progetto

**Liceo Amaldi (Roma):**
Danilo Corradi, Susanna Mattarocci, Domenico Zito, Maria Rocco

**CNR — ISMed:**
Michele Colucci, Francesco Di Filippo

**Università degli Studi Roma Tre:**
Giulia Zitelli Conti (AISO)

**Università Ca' Foscari, Venezia:**
Alessandro Laruffa

---

## English

### Project description

AmaldiStoria is a Flask web application developed to support the **Documentation Centre of the Liceo Edoardo Amaldi** in Rome (Tor Bella Monaca). The project was launched in 2021 as a collaboration between the Liceo Amaldi and the **CNR — Institute for the Study of the Mediterranean**, within the activities of the *Mediterranean Digital Humanities Lab* (MDHLab).

The goal is to build a structured digital environment for collecting, managing, and visualising statistical, documentary, oral, and cartographic sources related to the history of the school and its relationship with the surrounding area. The tool is designed both for academic research and, above all, for active learning, promoting a hands-on approach to the study of history.

### Key features

- **Statistical series** — interactive Highcharts graphs on enrolments by school year, gender, nationality, field of study, dropouts, and transfers
- **Interactive maps** — geographic distribution of students by year, heatmaps and clusters (Leaflet), with animated temporal evolution
- **Memory voices** — video interviews with teachers and former students
- **Image archive** — historical photographic collections of the school
- **Administration panel** — data management via Flask-Admin with role-based access control

### Technology stack

| Component | Technology |
|---|---|
| Backend | Python 3.10, Flask 2.3.x (pinned: see `requirements.txt`) |
| ORM | SQLAlchemy 1.4 + Flask-SQLAlchemy |
| Database | PostgreSQL with PostGIS extension |
| Migrations | Alembic / Flask-Migrate |
| Authentication | Flask-Login |
| Frontend | Bootstrap 5, Bootstrap Icons |
| Maps | Leaflet.js (heatmap, cluster, timeline) |
| Geodata | OpenStreetMap via Geofabrik, ISTAT municipal boundaries, Nominatim geocoding |
| Charts | Highcharts |
| Admin | Flask-Admin |
| Deployment | Apache + mod_wsgi |

### Repository structure

See the Italian section above — the directory layout is identical.

### Blueprint architecture

The application uses the **Application Factory** pattern (`create_app()`) with three Blueprints:

- **`main`** — all public routes (`/`, `/serie-generale`, `/map`, etc.) and the geocoding API
- **`auth`** — authentication handling (`/auth/login`, `/auth/logout`, `/auth/register`)
- **`revisione`** — `/revisione`, the address maintenance section, **restricted to the `adm` role**

Flask-Admin is configured separately in `admin_views.py` via `configure_admin(app, db)`, called inside `create_app()`. Flask-Admin ModelViews are not Blueprints and are registered directly on the `Admin` instance.

### Data model

Main models:

- **`User`** — application users with a role system (`adm`, `adv`, `usr`, `rdr`)
- **`Alunno`** — student enrolment records (school year, gender, nationality, field of study, final outcome)
- **`Strada`** — geocoded addresses (PostGIS coordinates + OSM data), linked to students via the `rel_alunno_strada` association table
- **`Indirizzo`** — legacy address table (kept for compatibility)

### Installation and local development

**Prerequisites:**
- Python 3.10+
- PostgreSQL with PostGIS installed
- `pip`

**Setup:**

```bash
# 1. Clone the repository
git clone <repo-url>
cd amaldistoria

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
# Edit .flaskenv with the correct values:
#   FLASK_APP=amaldistoria
#   FLASK_DEBUG=1
#   SECRET_KEY=<your-secret-key>
#   DATABASE_URL=postgresql://user:password@localhost/amaldistoria

# 5. Apply database migrations
flask db upgrade

# 6. Start the development server
flask run
```

### Loading a new school year

The school hands over one Spaggiari/Infoschool `.xls` export per school year. Five
commands, in this order:

```bash
# 1. Put the file in data/input/ (do not rename it: the school year is read from the name)

flask stradario-sync                  # 2. street gazetteer — downloads its own map data
flask import-alunni data/input/<file>.xls   # 3. import the students
flask geocode --anno 2024-2025        # 4. link them to street-level points
flask audit-geo                       # 5. verify everyone sits inside their declared town
```

Nothing has to be downloaded by hand: `stradario-sync` fetches the OpenStreetMap road
data (Geofabrik, ~750 MB) and the ISTAT municipal boundaries (~12 MB) into `data/geo/`
if they are not already there, and reuses them afterwards. Deleting `data/geo/` is
safe — it is a cache.

Re-running `import-alunni` on the same file is safe: rows already in the archive are
skipped, keyed on (school year, student id), and listed in the log.

Whatever the pipeline cannot resolve on its own is written to
`data/esiti/da_rivedere_<anno>.csv`, sorted by how many students it affects, and is
meant to be resolved by a person at **/revisione** (admins only). Guessing is deliberately
avoided: `VIA ROSSINI` in Rome matches three different streets.

That page works street by street rather than student by student, tells apart the
candidates a rule actually recognises from those that merely share a word, and **refuses**
any link whose point falls outside the town the student declared. When a street exists in
no source at all — OpenStreetMap is incomplete, and `Via Raddusa` in Rome is a real street
it simply does not have, worth 45 students — the point can be placed by hand on a map with
an orthophoto backdrop. Subsequent imports reuse it on their own.

The full step-by-step walkthrough, written for non-technical users, is in the Italian
section above and in [`data/README.md`](data/README.md).

### PostgreSQL/PostGIS setup

```sql
-- Create the database
CREATE DATABASE amaldistoria;

-- Enable PostGIS
\c amaldistoria
CREATE EXTENSION postgis;
```

Set the connection string in `.flaskenv`:
```
DATABASE_URL=postgresql://user:password@localhost:5432/amaldistoria
```

### Apache + mod_wsgi deployment

See the Italian section for a full Apache configuration example.

The `amaldiapp.wsgi` file must import `create_app`:

```python
import sys
sys.path.insert(0, '/path/to/amaldistoria')
from app import create_app
application = create_app()
```

**Note:** `WSGIApplicationGroup %{GLOBAL}` is required to avoid conflicts with C extensions such as NumPy and PostGIS.

### Role system

| Role | Code | Access |
|---|---|---|
| Administrator | `adm` | Everything: user management and the `/revisione` maintenance section |
| Advanced | `adv` | Data, maps, admin panel (no user management, no `/revisione`) |
| User | `usr` | Protected areas of the site |
| Reader | `rdr` | Protected areas, read-only |

### Project team

**Liceo Amaldi (Rome):**
Danilo Corradi, Susanna Mattarocci, Domenico Zito, Maria Rocco

**CNR — ISMed:**
Michele Colucci, Francesco Di Filippo

**Università degli Studi Roma Tre:**
Giulia Zitelli Conti (AISO)

**Università Ca' Foscari, Venezia:**
Alessandro Laruffa

---

*AmaldiStoria is developed and maintained by the [MDHLab | CNR — ISMed](http://mdhlab.cnr.it/).*
