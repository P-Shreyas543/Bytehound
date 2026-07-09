import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    xl = pd.ExcelFile(file_path)
    df = pd.read_excel(xl, sheet_name='variables')
    for i, row in df.iterrows():
        print(f"{row['id_or_address']} {row['signal_name']} start_index: {row['start_index']}")
except Exception as e:
    print(f"Error: {e}")
