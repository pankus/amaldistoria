import pandas as pd

def process_addresses(input_file, output_file):
    # Leggi il CSV
    df = pd.read_csv(input_file)
    
    # Formatta il CAP aggiungendo gli zeri iniziali dove necessario
    df['Cap Residenza'] = df['Cap Residenza'].astype(str).str.zfill(5)
    
    # Raggruppa i dati secondo i criteri richiesti e rimuovi i duplicati
    grouped_df = df.groupby(['Comune Residenza', 'Provincia Residenza', 
                            'Indirizzo Residenza', 'Cap Residenza'])
    
    # Crea un array con gli Id Alunno per ogni gruppo, rimuovendo i duplicati
    result_df = grouped_df['Id Alunno'].agg(lambda x: list(set(x))).reset_index()
    
    # Rinomina la colonna degli ID per maggiore chiarezza
    result_df = result_df.rename(columns={'Id Alunno': 'Lista_Id_Alunni'})
    
    # Ordina gli ID all'interno di ogni lista per una migliore leggibilità
    result_df['Lista_Id_Alunni'] = result_df['Lista_Id_Alunni'].apply(sorted)
    
    # Salva il risultato in un nuovo CSV
    result_df.to_csv(output_file, index=False)
    
    return result_df

# Esempio di utilizzo
if __name__ == "__main__":
    input_file = "sample_indirizzi.csv"
    output_file = "__indirizzi_raggruppati.csv"
    
    result = process_addresses(input_file, output_file)
    print("Elaborazione completata. I dati sono stati salvati in:", output_file)
    # Mostra le prime righe del risultato
    print("\nPrime righe del risultato:")
    print(result.head())