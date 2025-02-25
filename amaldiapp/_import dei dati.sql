_import dei dati

-- creo una tabella strada con i valori unici di ogni indirizzo/strada
--  popolo la tabella strada con i dati presi da indirizzo

INSERT INTO strada (
    osm_road, osm_house_number, 
    osm_house_number_dev, osm_postcode, osm_suburb, 
    osm_city, osm_lat, osm_lon, geom
)
SELECT DISTINCT
    osm_road, osm_house_number, 
    osm_house_number_dev, osm_postcode, osm_suburb, 
    osm_city, osm_lat, osm_lon, geom
FROM indirizzo;

-- il sistema crea una tabella di giunzione (SqlAlchemy)
-- CREATE TABLE public.rel_alunno_strada (
--     alunno_id INTEGER NOT NULL REFERENCES public.alunni (id),
--     indirizzo_id INTEGER NOT NULL REFERENCES public.strada (id),
--     PRIMARY KEY (alunno_id, indirizzo_id)
-- );

-- genero le relazioni M:M associando anche la vecchia tabella indirizzo
INSERT INTO rel_alunno_strada (alunno_id, indirizzo_id)
SELECT 
    a.id,
    s.id
FROM alunni a
JOIN indirizzo i ON a.id_alunno = i.id_alunno
JOIN strada s ON 
    COALESCE(i.osm_road, '') = COALESCE(s.osm_road, '') AND
    COALESCE(i.osm_house_number, '') = COALESCE(s.osm_house_number, '') AND
    COALESCE(i.osm_postcode, '') = COALESCE(s.osm_postcode, '') AND
    COALESCE(i.osm_city, '') = COALESCE(s.osm_city, '');

-- PROBLEMA: si creano alcuni duplicati... va gestito! posso avere al massimo una relazione alunno > strada (non il contrario)
SELECT a.id, a.id_alunno, COUNT(DISTINCT r.strada_id) as num_indirizzi, array_agg(indirizzo_residenza)
FROM alunni a
JOIN rel_alunno_strada r ON a.id = r.alunno_id
GROUP BY a.id, a.id_alunno
HAVING COUNT(DISTINCT r.strada_id) > 1
ORDER BY num_indirizzi DESC

-- > va fatta pulizia

-- prima di importare il csv va settato il sistema di datetime per farlgi accettare il formato dd/mm/yyyy (al posto di yyyy/mm/dd)
SET datestyle = 'DMY';


-- per sistemare le ridondanze
BEGIN;

-- Crea tabelle di backup
CREATE TEMP TABLE rel_alunno_strada_backup AS 
SELECT * FROM rel_alunno_strada;

CREATE TEMP TABLE strada_backup AS 
SELECT * FROM strada;

-- Identifica e aggiorna i duplicati, eliminando le relazioni duplicate
WITH duplicati AS (
    SELECT 
        MIN(id) as id_da_mantenere,
        array_agg(id) as ids_da_rimuovere
    FROM strada
    GROUP BY 
        osm_road, 
        COALESCE(osm_house_number, 'empty'),
        osm_postcode, 
        osm_city
    HAVING COUNT(*) > 1
),
-- Aggiorna mantenendo solo una relazione per ogni coppia alunno_id, strada_id
update_rel AS (
    DELETE FROM rel_alunno_strada r
    WHERE EXISTS (
        SELECT 1
        FROM duplicati d
        WHERE r.strada_id = ANY(d.ids_da_rimuovere)
    )
    RETURNING *
)
INSERT INTO rel_alunno_strada (alunno_id, strada_id)
SELECT DISTINCT alunno_id, d.id_da_mantenere
FROM update_rel ur
JOIN duplicati d ON ur.strada_id = ANY(d.ids_da_rimuovere);

-- Rimuovi i duplicati dalla tabella strada
DELETE FROM strada s
WHERE EXISTS (
    SELECT 1
    FROM strada s2
    WHERE s2.osm_road = s.osm_road
    AND COALESCE(s2.osm_house_number, 'empty') = COALESCE(s.osm_house_number, 'empty')
    AND s2.osm_postcode = s.osm_postcode
    AND s2.osm_city = s.osm_city
    AND s2.id < s.id
);

-- Verifica che non ci siano più duplicati
SELECT 
    osm_road, 
    COALESCE(osm_house_number, 'empty') as osm_house_number,
    osm_postcode, 
    osm_city,
    COUNT(*) as occorrenze
FROM strada
GROUP BY 
    osm_road, 
    COALESCE(osm_house_number, 'empty'),
    osm_postcode, 
    osm_city
HAVING COUNT(*) > 1;

-- Verifica che tutte le relazioni siano ancora valide
SELECT COUNT(*) 
FROM rel_alunno_strada r
LEFT JOIN strada s ON r.strada_id = s.id
WHERE s.id IS NULL;

-- Per fare rollback:
-- ROLLBACK;

-- Per confermare le modifiche:
-- COMMIT;

-- Pulizia (solo dopo il commit):
-- DROP TABLE rel_alunno_strada_backup;
-- DROP TABLE strada_backup;

-- INFINE: eseguire se tutto va bene
COMMIT;