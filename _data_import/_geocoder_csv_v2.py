from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import re
import csv
from tqdm import tqdm

def clean_address(text):
    text = text.upper()
    text = re.sub(r'^V\.\s?', 'VIA ', text)
    text = re.sub(r'\bLGO\b', 'LARGO', text)
    text = re.sub(r'\bV\.LE\b', 'VIALE', text)
    text = re.sub(r'\bP\.ZZA\b', 'PIAZZA', text)
    text = re.sub(r'\bS\.\s?', 'SANTA ', text)
    text = re.sub(r'\s*\d+.*$', '', text).strip()  # Rimuove numeri civici
    
    regole_pulizia = [
        (r'\b(?:V\.|VIC\.|VI[CT]?)\b', 'VIA '),
        (r'\bLGO\b', 'LARGO'),
        (r'\bVLE\b', 'VIALE'),
        (r'\bP\.?ZZA\b', 'PIAZZA'),
        (r'\bS\.?\s?(?:TA|ANT[A]?)?\b', 'SANTA '),
        (r'\bN[UM]?\.?\s?', ' '),  # Gestione numeri civici
        (r'\b(?:SCALA|SC\.|INT\.|PT\.|P\.|NR?\.)\s?\w+', ' '),
        (r'\bC\.?/?(?:D|F)?\b', ' '),  # Gestione 99/C
        (r'\d+[/-]?\w*(?:\s?\w*)*', ' '),  # Qualsiasi combinazione numerica
        (r'\b(?:EDIFICIO|PALAZZA|LOCALITA)\b.*', ' '),
        (r',\s?\d+.*$', ' '),  # Tutto dopo la virgola con numeri
        (r'\s+', ' ')  # Multipli spazi
    ]
    
    for pattern, replacement in regole_pulizia:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
    return text.replace('"', '').replace(',', ' ')

geolocator = Nominatim(user_agent="amaldi2_geocoder")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

# Contatori e percorsi
input_file = 'sample_23.csv'
total_rows = sum(1 for _ in open(input_file, encoding='utf-8-sig')) - 1  # Esclude header
progress_bar = tqdm(total=total_rows, desc="Geocoding", unit="record")

data, fails = [], []

with open('sample_23.csv', mode='r', encoding='utf-8-sig') as csv_file:  # Gestisce BOM
    csv_reader = csv.reader(csv_file, delimiter=',')
    next(csv_reader)  # Salta header
    
    for row in csv_reader:
        try:
            id_alunno = row[0]
            indirizzo_originale = row[3]  # Colonna "Indirizzo Residenza"
            cap = row[5].zfill(5)  # CAP a 5 cifre
            
            # Pulizia indirizzo per la query
            indirizzo_pulito = clean_address(indirizzo_originale)
            
            # Costruisci query strutturata
            location = geocode({
                'street': indirizzo_pulito,
                'postalcode': cap,
                'city': row[1],  # Comune Residenza
                'country': 'Italia'
            }, exactly_one=True, addressdetails=True)
            
            if location:
                address_data = location.raw['address']
                pnt = {
                    'Id Alunno': id_alunno,
                    'Indirizzo Originale': indirizzo_originale,
                    'road': address_data.get('road', 'empty'),
                    'suburb': address_data.get('suburb', 'empty'),
                    'city': address_data.get('city', 'empty'),
                    'county': address_data.get('county', 'empty'),
                    'state': address_data.get('state', 'empty'),
                    'postcode': address_data.get('postcode', 'empty'),
                    'lat': location.latitude,
                    'lon': location.longitude
                }
                data.append(pnt)
            else:
                fails.append([id_alunno, indirizzo_originale, cap, "Nessun risultato OSM"])
                
        except Exception as e:
            fails.append([id_alunno, indirizzo_originale, cap, str(e)])
            
        # Aggiorna barra di avanzamento
        progress_bar.update(1)
        progress_bar.set_postfix({
            'Successi': len(data), 
            'Falliti': len(fails),
            'Compl.': f"{progress_bar.n/total_rows*100:.1f}%"
        })

progress_bar.close()

# Salva risultati con tutte le colonne OSM
headers = [
    'Id Alunno', 'Indirizzo Originale', 'road', 'suburb', 
    'city', 'county', 'state', 'postcode', 'lat', 'lon'
]

with open('results_23.csv', mode='w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(data)

# Salva errori con ID e indirizzo originale
with open('errors_23.csv', mode='w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['Id Alunno', 'Indirizzo Originale', 'CAP', 'Errore'])
    writer.writerows(fails)