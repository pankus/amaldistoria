import pandas as pd
import ast

def expand_student_ids(input_file, output_file):
    """
    Elabora un CSV contenente ID studenti in liste e crea un nuovo CSV
    dove ogni ID studente ha la sua riga dedicata.
    
    Args:
        input_file (str): Percorso del file CSV di input
        output_file (str): Percorso dove salvare il file CSV elaborato
    """
    # Leggo il CSV
    df = pd.read_csv(input_file)
    
    # Funzione per convertire la stringa della lista in lista Python
    def parse_list(x):
        try:
            # Gestisce sia le stringhe con virgole che senza
            return ast.literal_eval(x if isinstance(x, str) else f"[{x}]")
        except:
            return [x]
    
    # Converto la colonna Id_Alunni in liste
    df['Id_Alunni'] = df['Id_Alunni'].apply(parse_list)
    
    # Espando le liste di ID
    df_expanded = df.explode('Id_Alunni')
    
    # Converto gli ID in interi
    df_expanded['Id_Alunni'] = df_expanded['Id_Alunni'].astype(int)
    
    # Salvo il risultato
    df_expanded.to_csv(output_file, index=False)
    
    # Stampo alcune statistiche
    print(f"Righe nel file originale: {len(df)}")
    print(f"Righe nel file elaborato: {len(df_expanded)}")
    print("\nPrime 5 righe del risultato:")
    print(df_expanded.head())

if __name__ == "__main__":
    # Esempio di utilizzo
    input_file = "__indirizzi_geocoded.csv"
    output_file = "__indirizzi_expanded_END.csv"
    
    expand_student_ids(input_file, output_file)