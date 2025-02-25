from amaldiapp import app, db
from amaldiapp.models import Strada, Alunno
import pandas as pd
from sqlalchemy import exists

def import_addresses():
    # Leggi il CSV
    df = pd.read_csv('__indirizzi_expanded_END.csv')
    
    # Conta quanti record verranno processati
    total_records = len(df)
    new_records = 0
    new_relations = 0
    
    print(f"Processando {total_records} indirizzi...")
    
    # Itera sulle righe del CSV
    for index, row in df.iterrows():
        # Verifica se esiste già una strada con lo stesso osm_road
        # existing_strada = db.session.query(Strada).filter(Strada.osm_road == row['road']).first()
        existing_strada = Strada.query.filter(Strada.osm_road == row['road']).first()
        
        # Trova l'alunno corrispondente
        # alunno = db.session.query(Alunno).filter(Alunno.id_alunno == row['Id_Alunni']).first()
        alunno = Alunno.query.filter(Alunno.id_alunno == row['Id_Alunni']).first()
        
        if alunno:
            # Se la strada non esiste, creala
            if not existing_strada and pd.notna(row['road']):
                new_strada = Strada(
                    osm_road=row['road'],
                    osm_postcode=str(int(row['postcode'])) if pd.notna(row['postcode']) else None,
                    osm_suburb=row['suburb'],
                    osm_city=row['city'],
                    osm_type=row['osm_type'],
                    osm_lat=row['latitude'],
                    osm_lon=row['longitude'],
                    geom=f'POINT({row["longitude"]} {row["latitude"]})'
                )
                db.session.add(new_strada)
                db.session.flush()  # Per ottenere l'ID della nuova strada
                current_strada = new_strada
                new_records += 1
            else:
                current_strada = existing_strada
            
            # Se abbiamo una strada (nuova o esistente) e un alunno, crea la relazione
            if current_strada and current_strada not in alunno.strade:
                alunno.strade.append(current_strada)
                new_relations += 1
            
            # Commit ogni 100 record
            if (new_records + new_relations) % 100 == 0:
                db.session.commit()
                print(f"Processati {index + 1}/{total_records} record. "
                      f"Aggiunti {new_records} nuovi indirizzi e {new_relations} nuove relazioni.")
    
    # Commit finale
    db.session.commit()
    
    print(f"\nImportazione completata!")
    print(f"Totale record processati: {total_records}")
    print(f"Nuovi indirizzi aggiunti: {new_records}")
    print(f"Nuove relazioni create: {new_relations}")

if __name__ == '__main__':
    with app.app_context():
        import_addresses()