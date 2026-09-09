# PAGINE

## Homepage

[] aggiornare elenco studenti
[] banner/box automaticamente estratti dalla sezione/pagina materiali (da progettare)

## Voci

### video (da youtube)

### file audio (da caricare sul sito)

## Mappe

[] mappa territorio > cercare di convertire in leaflet

## Materiali (nuova pagina)

- podcast 1
- podcast 2 (finanziato: "voci della città")
- video
- deplian
- libro

## DATI

- 2024-2025 (mail di Mimmo) — importata
- 2025-2026 (mancanti) — importata
- problema della geo-localizzazione >> provare ad automatizzare il processo
  - automatizzato: `flask import-alunni` + `flask geocode` + `flask audit-geo`.
    97,3% degli alunni ha un punto sulla mappa (46.659 su 47.932)
  - quello che resta lo si chiude a mano da **/revisione** (menù utente →
    *Revisione indirizzi*, solo `adm`): **316 vie, 1.264 alunni**. Una riga è una via,
    non uno studente: decidendola si sistemano tutti gli alunni che l'hanno scritta,
    in qualunque annata
  - [] smaltire la coda — le prime voci valgono decine di alunni a testa
  - [] `Via Raddusa` (45 alunni): OSM non ce l'ha, va piazzata a mano sulla mappa.
    Dove passa lo sa una persona, non il programma
- succursali (non si può fare ora)
  - `sede_norm` ora è compilata su tutte le righe (CENTRALE / SUCCURSALE), ma nessuna
    pagina la usa ancora: si potrebbero incrociare succursali e residenze sulle mappe
