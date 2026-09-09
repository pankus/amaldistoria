# La cartella `data/`

Tre sottocartelle, divise per **natura del contenuto**, non per comando che le usa.

```
data/
├── input/   i file che consegna la scuola          ← ci metti tu i file
├── geo/     le mappe scaricate da internet          ← si riempie da sola
└── esiti/   i rapporti prodotti dai comandi         ← si riempie da sola
```

---

## `input/` — i dati della segreteria

Qui vanno i file **`.xls` esportati da Spaggiari/Infoschool**, uno per anno scolastico.
Sono i file che la scuola consegna periodicamente.

Non vanno rinominati: il nome contiene l'anno scolastico
(`RMII0063_AC_2024-25_data22-06-2026_ore21_19_02.xls` → anno `2024-2025`) e il comando
lo legge da lì. Se il nome fosse diverso si può sempre indicare l'anno a mano con
`--anno 2024-2025`.

Un file per anno. Reimportare lo stesso file due volte non crea doppioni: le righe già
presenti vengono saltate e registrate in `esiti/log_import_<anno>.csv`.

## `geo/` — le mappe per la geolocalizzazione

**Non devi scaricare niente a mano.** Il comando `flask stradario-sync` controlla se i
file ci sono e, se mancano, li scarica da solo. Se ci sono già, li riusa senza
riscaricarli.

Due sorgenti, entrambe pubbliche e gratuite:

| file | cos'è | quanto pesa |
|---|---|---|
| `centro-free.shp.zip` | tutte le strade del Centro Italia da OpenStreetMap (Geofabrik) | ~750 MB |
| `istat_comuni.zip` | i confini ufficiali dei comuni italiani (ISTAT) | ~12 MB |

Insieme agli archivi trovi anche i file estratti (`gis_osm_roads_free_1.*`,
`Limiti01012024_g/`): sono la stessa roba scompattata, servono al caricamento.

**Puoi cancellare tutta la cartella `geo/` senza perdere nulla**: al prossimo
`flask stradario-sync` viene riscaricata. Serve solo a evitare di riscaricare 750 MB
ogni volta. Per forzare l'aggiornamento delle mappe (una volta l'anno è più che
sufficiente) si usa `flask stradario-sync --riscarica`.

Il download è "tutto o niente": se si interrompe non lascia un file monco che il
lancio successivo scambierebbe per buono.

## `esiti/` — cosa è successo

Rapporti in formato CSV, apribili con Excel o LibreOffice. Sono **la parte da leggere
dopo ogni import**: dicono cosa il programma non è riuscito a fare da solo.

| file | contiene |
|---|---|
| `log_import_<anno>.csv` | righe saltate perché già in archivio, CAP scritti male, valori troncati |
| `correzioni_<anno>.csv` | le correzioni applicate automaticamente agli indirizzi, con la regola usata |
| `da_rivedere_<anno>.csv` | gli indirizzi che **richiedono una persona**, ordinati per numero di studenti coinvolti |
| `audit_geo.csv` | studenti collegati a una via che sta fuori dal loro comune |

`correzioni_*.csv` va scorso ogni tanto a campione: serve a controllare che le
correzioni automatiche siano giuste (`VIA G. MARCONI` → `Via Guglielmo Marconi` sì,
un cognome cambiato no).

Questi file si possono cancellare: vengono riscritti a ogni esecuzione del comando.
