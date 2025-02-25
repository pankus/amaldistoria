import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from tqdm import tqdm
import ast  # Per convertire la stringa della lista in lista Python

def get_address_details(address, city, province, cap):
    """
    Funzione per ottenere i dettagli dell'indirizzo usando geopy
    """
    # Costruisci la query completa
    # query = f"{address}, {city}, {province}, {cap}, Italy"
    query = f"{address}, {city}, Italy"
    
    try:
        # Ottieni la location
        # location = geocode(query)
        location = geocode(query=query, addressdetails=True, exactly_one=True)
        
        if location:
            # Estrai i dettagli dall'oggetto raw
            raw = location.raw
            address_details = raw.get('address', {})
            # print(address_details)
            details = {
                'latitude': location.latitude,
                'longitude': location.longitude,
                'road': address_details.get('road', ''),
                'suburb': address_details.get('suburb', ''),
                'city': address_details.get('city', address_details.get('town', address_details.get('village', ''))),
                'county': address_details.get('county', ''),
                'state': address_details.get('state', ''),
                'postcode': address_details.get('postcode', ''),
                'osm_type': raw.get('osm_type', ''),
                'osm_id': raw.get('osm_id', ''),
            }
            return details, None
        
        return None, query
    
    except Exception as e:
        return None, f"{query} - Errore: {str(e)}"

def enrich_addresses(input_file, output_file, failed_output_file):
    # Leggi il CSV
    df = pd.read_csv(input_file)
    
    # Converti la stringa della lista in lista Python
    df['Lista_Id_Alunni'] = df['Lista_Id_Alunni'].apply(ast.literal_eval)
    
    # Liste per i dati
    geocoded_data = []
    failed_addresses = []
    
    # Processa ogni riga con tqdm per mostrare la progress bar
    for index, row in tqdm(df.iterrows(), total=len(df), desc="Geocoding indirizzi"):
        # Ottieni i dettagli dell'indirizzo
        details, error = get_address_details(
            row['Indirizzo Residenza'],
            row['Comune Residenza'],
            row['Provincia Residenza'],
            row['Cap Residenza']
        )
        
        if details:
            # Prepara i dati base
            row_data = {
                'Indirizzo Residenza': row['Indirizzo Residenza'],
                'Comune Residenza': row['Comune Residenza'],
                'Provincia Residenza': row['Provincia Residenza'],
                'Cap Residenza': row['Cap Residenza'],
                'Id_Alunni': row['Lista_Id_Alunni']  # Mantieni la lista di ID
            }
            # Aggiungi i dettagli del geocoding
            row_data.update(details)
            geocoded_data.append(row_data)
        else:
            # Aggiungi alla lista dei falliti
            failed_addresses.append({
                'indirizzo_completo': error,
                'indirizzo': row['Indirizzo Residenza'],
                'comune': row['Comune Residenza'],
                'provincia': row['Provincia Residenza'],
                'cap': row['Cap Residenza'],
                'id_alunni': str(row['Lista_Id_Alunni'])  # Converti la lista in stringa per il CSV
            })
    
    # Crea DataFrame con i risultati
    result_df = pd.DataFrame(geocoded_data)
    failed_df = pd.DataFrame(failed_addresses)
    
    # Converti la lista di ID in stringa per il salvataggio
    result_df['Id_Alunni'] = result_df['Id_Alunni'].apply(str)
    
    # Salva i risultati
    result_df.to_csv(output_file, index=False)
    if failed_addresses:
        failed_df.to_csv(failed_output_file, index=False)
        print(f"\nTrovati {len(failed_addresses)} indirizzi non localizzati.")
        print(f"Lista salvata in: {failed_output_file}")
    
    return result_df, failed_df

if __name__ == "__main__":
    input_file = "__indirizzi_raggruppati.csv"
    output_file = "__indirizzi_geocoded.csv"
    failed_output_file = "__indirizzi_non_localizzati.csv"
    
    # Inizializza il geocoder
    geolocator = Nominatim(user_agent="amaldistoria_devel3")
    
    # Crea una versione con rate limiting del geocoder
    geocode = RateLimiter(geolocator.geocode, 
                         min_delay_seconds=1.5,
                         return_value_on_exception=None)
    
    print("Inizio processo di geocoding...")
    result, failed = enrich_addresses(input_file, output_file, failed_output_file)
    print(f"\nProcesso completato. I dati sono stati salvati in: {output_file}")
    
    # Mostra alcune statistiche
    total = len(result)
    failed_count = len(failed) if not failed.empty else 0
    success_rate = ((total - failed_count) / total) * 100
    
    print(f"\nStatistiche:")
    print(f"- Totale indirizzi processati: {total}")
    print(f"- Indirizzi localizzati con successo: {total - failed_count}")
    print(f"- Indirizzi non localizzati: {failed_count}")
    print(f"- Tasso di successo: {success_rate:.2f}%")