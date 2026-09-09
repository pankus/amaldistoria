# Da fare

Stato all'8 settembre 2026, a valle dell'import di 2024-2025 e 2025-2026, della
rigeocodifica dell'intero archivio, della correzione del vincolo di comune (punto 1.1),
delle regole nuove del normalizzatore (punto 1.2), della sezione `/revisione` (punto 1.4)
e degli strumenti di revisione del punto 1.5.

**Dove siamo**: 46.659 alunni su 47.932 collegati a un punto sulla mappa (97,3%).
In coda restano **316 gruppi, 1.264 alunni**. Invarianti verificate: nessun civico salvato,
nessuna `strada` senza geometria, nessun doppione sulla chiave `(via, CAP, comune)`,
**nessun collegamento fuori dal comune dichiarato** (`flask audit-geo`: 0) e nessun
collegamento forzato. Stradario: 26.712 vie in 41 comuni.

Il percorso: si partiva da 46.102 (96,2%) di cui 132 nel comune sbagliato. Il fix 1.1 li ha
staccati portando la copertura *corretta* a 46.010, poi le regole del 1.2 hanno aggiunto
543 alunni. Guadagno netto sul dato buono: +583.

---

## 1. Geocodifica — cose da sistemare

### 1.1 Il riuso non verifica il comune ✅ *fatto, 1 settembre 2026*

`geocode` verificava il confine ISTAT solo sui risultati **nuovi** di Nominatim. Due percorsi
lo aggiravano, entrambi corretti:

- **stadio 2, riuso**: se una `strada` esisteva con quella via e quel CAP la collegava e
  basta. `Via Casilina` attraversa davvero Roma e Monte Compatri, e 17 studenti romani
  stavano sul punto di Monte Compatri perché il CAP combaciava. Ora `_prima_nel_comune()`
  sceglie fra le candidate quella dentro il comune dichiarato; se nessuna lo è, si prosegue
  allo stadio 3.
- **ripiego sullo stradario**: `_riga_stradario()`, quando nel comune dichiarato non trovava
  la via ma ne esisteva una sola omonima altrove, restituiva quella — `Via Capizzi` di uno
  studente di Frascati finiva sulla Via Capizzi di Roma. Questo percorso da solo produceva
  67 dei 132 collegamenti sbagliati. Ora: comune dichiarato ⇒ o la via è lì, o è coda di
  revisione.

Conseguenza sulla chiave naturale di `strada`: è `(via, CAP, comune)`, non `(via, CAP)` —
6 coppie sono legittimamente a cavallo di due comuni (`Via Casilina` Roma/Monte Compatri,
`Via di Vermicino` Frascati/Roma, `Via degli Abeti` Ardea/Pomezia…). E il comune è quello
che **contiene il punto**, non `osm_city`: quello riporta la risposta di Nominatim e a volte
sbaglia (la `Via Osini` di Monte Compatri era salvata come 'Roma'). `strade-cleanup` e le
verifiche del punto 4 usano ora questa chiave.

Eseguito: `audit-geo --scollega` (132 + 67 collegamenti rimossi), `strade-cleanup`
(16 righe doppie unite), `geocode --tutti`, `audit-geo` → **0**.

### 1.2 Lacune del normalizzatore ✅ *fatto, 1 settembre 2026*

Sei regole nuove in `app/toponimi.py`, +543 alunni collegati. Le cinque previste dal TODO
più una, `spaziatura`, che è saltata fuori misurando il residuo ed era la più grossa di
tutte (73 indirizzi da sola): le vie di Torrenova portano nomi di comuni — `Roccamorice`,
`Poggioreale`, `Nardodipace`, `Trecastagni` — e la segreteria li scrive staccati. Non
cambia nemmeno una lettera, cambia solo dove cade lo spazio.

Una previsione del TODO era sbagliata e va ricordata: «doppio tipo → se il 2° token è un
tipo, vince quello, dentro `normalizza()`» avrebbe storpiato **61 vie vere** dello
stradario che cominciano davvero con due tipi (`Via Ponte Lucano`, `Via Corso Italia`,
`Via Piazza Armerina`). È diventata un secondo passaggio in `risolvi()`, che toglie il
primo token solo contro i candidati proprio di quel tipo.

`test_toponimi.py` è passato da 6 a 12 verifiche. I casi negativi sono la parte che conta:
`ARCH` senza punto non aggancia `ARCHETTI`, `ARC.` è troppo corto, `LONGI` non aggancia
`LONGIANO`, `PONTE LUCANO` non diventa `Lucano`.

La tabella delle sette regole con il freno di ciascuna sta in `CLAUDE.md`.

### 1.2-bis Due estensioni già misurate, non ancora fatte

Sono la stessa correzione applicata a due regole esistenti: passarle per
`_senza_preposizioni()` prima del confronto, come già fa `troncamento`. Una riga per regola.

| estensione | resa | esempio |
|---|---|---|
| `refuso` senza preposizioni | 11 indirizzi, **44 alunni** | `VIA PRATOLUNGO CASILNO` → `Via di Pratolungo Casilino` (oggi non aggancia perché il `di` del nome vero sfasa il conteggio dei token) |
| `spaziatura` senza preposizioni | 4 indirizzi, **14 alunni** | `VIA ROCCA CENC IA` → `Via di Rocca Cencia` |

Numeri verificati in sola lettura sulla coda attuale, non stimati.

### 1.3 Coda di revisione da smaltire

**316 gruppi, 1.264 alunni** all'8 settembre 2026 (erano 389/1.370, e prima 516/1.913).
Il numero si legge da `/revisione`, che lo ricalcola dal database;
`data/esiti/da_rivedere_tutti.csv` è la fotografia dell'ultimo `geocode` e invecchia.
La composizione misurata allora:

- 368 non risolti
- 16 ambigui — richiedono davvero una persona (`VIA ROSSINI` a Roma sono tre strade diverse:
  Via Luigi Rossini, Via Carlo Conti Rossini, Viale Gioacchino Rossini)
- 5 illeggibili

Cos'è rimasto fra i 368, misurato e non stimato:

- **60 non hanno alcun candidato nel comune dichiarato** (250 alunni): la via non è nello
  stradario. Non è un problema di normalizzazione, e nessuna regola nuova li recupererà.
  Il caso capofila è `VIA RADDUSA` a Roma, **45 alunni**: è una via vera, in un quartiere di
  toponimi siciliani che OSM conosce (Troina 86 m, Riposto 120 m, Partanna 128 m), ma
  OpenStreetMap non ce l'ha e Nominatim risponde vuoto. Non è cache vecchia: l'estratto
  Geofabrik è del 1 settembre 2026. Si chiudono da **/revisione**, sezione «Metti il punto a
  mano»: mappa con ortofoto, le vie note segnate intorno, click per piazzare il punto.
  Dopo la prima volta `geocode` riusa la riga da solo.
- **Da valutare, chiuderebbe questa classe senza lavoro manuale**: Roma Capitale pubblica la
  toponomastica ufficiale (SIS.TO e servizi OGC del geoportale). Roma è il 97% degli
  indirizzi, quindi una seconda anagrafe accanto a OSM eviterebbe i 60 casi a mano. Da
  verificare se esiste un download con geometrie e licenza aperta: i due endpoint provati il
  1 settembre 2026 rispondono 502 e 404.
- 15 li chiude il punto 1.2-bis.
- il resto sono nomi propri diversi (`LARGO FRANCESCO MENGARONI` per `Largo Ferruccio
  Mengaroni`: non è un refuso, è un altro nome), token in più che la via vera non ha
  (`VIA GIACOMO MATT? TRUCCO` per `Via Mattè Trucco`, 8 alunni) e contrazioni interne
  (`TORR.VA` per `Torrenova`). Ammettere token in più o prefissi interni è la porta da cui
  rientra `LONGI`/`LONGO`: da qui in avanti conviene la revisione a mano, non altre regole.

Si smaltiscono da **/revisione** (menù utente → *Revisione indirizzi*, solo `adm`), che
lavora per gruppo e rifiuta i collegamenti fuori comune. Il pannello Flask-Admin
(*Dati → Strade*) resta utilizzabile per i casi che escono dallo schema.

### 1.4 La sezione `/revisione` ✅ *fatta, 1 settembre 2026*

Blueprint indipendente (`app/revisione/`), riservata al ruolo `adm`. Esiste perché
Flask-Admin fa lavorare per riga e non impedisce l'errore più frequente.

- **Coda per via, non per studente**: 320 decisioni che coprono 1.370 alunni. Calcolata dal
  database a ogni richiesta, non dal CSV in `data/esiti/`, che invecchia a ogni `geocode`.
- **Candidati separati per compatibilità**: sopra quelli che una regola di
  `toponimi.REGOLE` riconosce come la stessa via, col nome della regola; in un blocco
  chiuso quelli che condividono solo qualche parola. Non è cosmetica: l'indice restituisce
  qualunque via condivida un token, quindi per `LAGO DI BOLSENA` propone anche
  `Via Lago di Bracciano`, e in una lista piatta l'errore sta sotto il primo bottone.
- **Il vincolo di comune è imposto nel codice**, non nascondendo il bottone: verificato
  forgiando la POST a mano.
- **Punto a mano sulla mappa** per le vie che nessuna fonte conosce, con ortofoto e le vie
  note segnate intorno. Le righe così create hanno `osm_type='manuale'`.

Sistemate contestualmente due trappole in `StradaAdmin`: `check_duplicate` confrontava
`(via, civico, CAP)` **senza il comune** e rifiutava di creare la seconda `Via Casilina`
legittima; e il form salvava il numero civico, contro la regola di privacy.

Cosa resta aperto su questa sezione (aggiornato all'8 settembre, vedi 1.5):

- Non c'è modo di **correggere** un punto già salvato: si può solo crearne uno nuovo. Serve
  quando un punto messo a mano risulta sbagliato.
- I casi impossibili (`PRIVO DI RESIDENZA`, indirizzo vuoto con 10 alunni) restano in coda
  per sempre. Se danno fastidio: una tabellina di archiviazione creata con
  `__table__.create(checkfirst=True)`, come già fa `Stradario`.
- **`Via Raddusa` (45 alunni) è ancora da piazzare**: il meccanismo è verificato end-to-end
  (copertura salita a 46.598, audit 0, invarianti 0) ma la riga di prova è stata rimossa,
  perché il punto usato era a 30 m da Via Carlentini — cioè proprio la confusione da cui il
  caso era partito. Dove passa davvero quella via lo sa una persona, non il programma.

### 1.5 Strumenti di revisione ✅ *fatto, 8 settembre 2026*

Quattro interventi nati tutti dallo stesso limite: la pagina di gruppo mostrava *cosa*
decidere ma non dava all'operatore l'informazione per decidere.

**Tolleranza sul confine, `TOLLERANZA_CONFINE_M = 100`.** `_dentro_comune()` accetta un
punto entro 100 m dal confine ISTAT (`ST_Contains OR ST_DWithin(::geography, 100)`). Non
allenta il vincolo: quello che si salva è il **baricentro** della via, e su una strada a
cavallo del confine cade dall'altra parte. `Via Torre dello Stinco` è Roma per OSM e per la
segreteria, e i suoi due punti stanno **0,4 m** e **30 m** dentro Frascati — 17 alunni
bloccati senza alcuna via d'uscita, e nessuna regola nuova li avrebbe recuperati.
`Via Aci Platani` (24,3 m) era lo stesso caso. Verificato che le omonimie storiche restano
rifiutate: Nerola 47 km, Anzio, Pomezia. Alzarla di molto le riammette: non toccarla senza
rifare quella prova. `audit-geo` applica la stessa nozione, altrimenti segnalerebbe come
errori le vie di confine che `geocode` ora accetta.

**Collegamenti forzati.** Oltre la tolleranza non esisteva alcuna uscita, e il caso
legittimo c'è: il comune scritto dalla segreteria può essere sbagliato, e una via può essere
davvero a cavallo del confine oltre la soglia. `Via Aci Platani`, che Nominatim descrive
come «Municipio Roma VI, Villa Verde, Roma, Roma Capitale, 00132», ha il punto **145 m
dentro Frascati**: la via giusta, rifiutata, senza modo di prenderla. I bottoni «Collega
comunque» / «Crea comunque» / «Salva comunque» scavalcano il vincolo dopo conferma
esplicita. Perché non riapra la porta agli 891 errori storici, la forzatura **si registra
invece di nascondersi**: colonna `rel_alunno_strada.forzato` (migrazione
`collegamenti forzati`), flash `warning`, sezione propria in `audit-geo` con la colonna nel
CSV, e `--scollega` che non li tocca. Senza quella colonna il primo audit avrebbe cancellato
in silenzio tutto il lavoro forzato a mano.

La tolleranza **non è stata alzata** per far entrare i 145 m: sarebbe una toppa che
riammette le omonimie dei comuni confinanti. Il caso si chiude forzando, e resta tracciato.

**Quattro card numerate, e la forzatura dove si agisce.** I quattro modi — 1 già in archivio
· 2 vie dello stradario · 3 ricerca Nominatim · 4 punto a mano — erano una sequenza
indistinta di titoletti, e non si capiva che il primo che risolve il caso è quello giusto.
Il bottone di forzatura, prima una casella globale, era **invisibile dalla card 3**: chi
cercava su Nominatim scopriva il rifiuto dopo il click e veniva rimandato a una casella che
da lì non si vedeva. Ora ogni card ha il suo, e per poterlo mostrare *prima* del click serve
sapere dove cade il punto: **`GET /revisione/dove`** (`comune` + `p=lat,lon` ripetuto, al
più 10) risponde `{comune, ok, metri}` per ciascun punto. `ok` passa da `_dentro_comune()`,
tolleranza inclusa — una seconda nozione di «dentro» finirebbe per divergere da quella che
poi rifiuta il salvataggio. `metri` è ciò che distingue a colpo d'occhio la via di confine
(145 m) dall'omonimia di un'altra provincia (`Via Aci Platani` di Aci Catena, 658 km): ogni
risultato Nominatim porta il badge con il comune reale e il bottone giusto, e il punto messo
a mano si verifica al click. Anche le righe d'archivio dicono ora dove cade il loro punto
(`_comune_del_punto()`), che è come si vede che la `Via Aci Platani` già salvata è **quella
di Frascati**, un'altra via.

**Il CAP come riferimento, ovunque.** In coda è una colonna, nel gruppo sono tutti i CAP
scritti dagli alunni con i rispettivi conteggi. In «Indirizzi già in archivio» ogni riga
porta il CAP in evidenza e il numero di alunni del gruppo che lo hanno, e l'ordinamento le
mette prima: 4 righe `Via Gadurso` differiscono **solo** per il CAP, e senza quel dato la
variante giusta era indistinguibile. I 5 gruppi con più CAP hanno una `select` che decide
con quale salvare una via nuova.

**Ricerca vie sulla mappa del punto a mano.** La mappa si apriva sul baricentro del CAP o
del comune, a chilometri; ci si arrivava trascinando. Ora una casella cerca su
`/search/address` e porta la vista sul risultato (zoom 17, cerchio arancione), senza creare
né collegare nulla — `vicine()` mostra da sé le vie note intorno.

---

## 2. Debito tecnico preesistente

Non introdotto in questa fase, ma emerso lavorandoci.

- **Il repo non è sotto controllo di versione.** Non c'è `.git`. Prima di iniziarlo serve un
  `.gitignore` con almeno: `.venv/`, `__pycache__/`, `*.pyc`, `.DS_Store`, **`data/geo/`**
  (750 MB di cache riscaricabile), `data/esiti/` (rigenerabile), e valutare `data/input/`
  (dati personali di minori: probabilmente **non** va versionato).
- **`data/input/` contiene dati personali di minori.** Va deciso esplicitamente dove
  possono stare e chi vi accede, e va tenuto fuori da qualsiasi repository pubblico.
- **`User.password_clear` conserva la password in chiaro** accanto all'hash, e il pannello
  admin la scrive. Da rimuovere, con una migrazione.
- **Dipendenze non usate** in `requirements.txt`: `folium`, `plotly`, `numpy` — nessuna è
  importata da nessuna parte (`pandas` invece ora serve all'importer). Il README non le
  cita più, ma i pin restano.
- **CSRF solo dove è stato messo a mano.** `/revisione` valida il token con
  `validate_csrf()` sulle proprie POST, ma l'app non ha `CSRFProtect` globale: le altre
  form protette sono solo quelle di Flask-Admin che usano `SecureForm`.
- **Connessioni mai chiuse**: `app/main/views.py` apre `db.engine.connect()` in 6 punti
  senza chiuderle né usarle come context manager.
- **Copie stantie**: `app/templates_bk/` (17 file) e `app/templates/index_BK.html` non
  hanno effetto sull'app e confondono chi cerca il template giusto.
- **Modello `Indirizzo`** — tabella legacy, marcata «da escludere» nel codice ma ancora nel
  modello e quindi nelle migrazioni.

---

## 3. Funzionalità (da `AGGIORNAMENTI.md`)

- Mappa del territorio: oggi è un iframe di Google My Maps, da convertire in Leaflet come
  le altre.
- Pagina «Materiali» nuova: podcast, video, depliant, libro.
- Homepage: elenco studenti da aggiornare, box estratti dalla pagina materiali.
- `sede_norm` ora è popolata su tutte le righe (`CENTRALE`/`SUCCURSALE`) ma **nessuna vista
  la legge**: si potrebbero incrociare succursali e residenze sulle mappe, cosa oggi
  cablata a mano nei marker di `_get_school_markers()`.
- Dati mancanti: annate precedenti al 1992-1993, se esistono.

---

## 4. Verifiche da rifare dopo ogni intervento

```bash
python test_toponimi.py          # deve passare
flask audit-geo                  # collegamenti fuori comune: idealmente 0
```

```sql
-- nessuna di queste deve tornare valori diversi da 0
select count(*) from strada where osm_house_number is not null
   and osm_house_number not in ('', 'empty');
select count(*) from strada where geom is null;
-- il comune e' quello che contiene il punto: osm_city riporta Nominatim e a volte sbaglia
select count(*) from (select s.osm_road, coalesce(s.osm_postcode,''), coalesce(c.comune,'')
   from strada s left join istat_comuni c on ST_Contains(c.geom, s.geom)
   group by 1,2,3 having count(*)>1) t;
```

```sql
-- le forzature non devono essere 0 a forza: vanno lette, non fatte sparire
select s.osm_road, a.comune_residenza, count(*)
from rel_alunno_strada r
join strada s on s.id = r.strada_id
join alunni a on a.id = r.alunno_id
where r.forzato group by 1,2 order by 3 desc;
```

```sql
-- la copertura non deve peggiorare
select anno_ref, count(*) as alunni,
  count(*) filter (where exists (
    select 1 from rel_alunno_strada r where r.alunno_id = a.id)) as geo
from alunni a group by 1 order by 1;
```
