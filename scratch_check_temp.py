import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    xl = pd.ExcelFile(file_path)
    df = pd.read_excel(xl, sheet_name='variables')
    print("Variables with 'Pack_Temperature' in name:")
    print(df[df['signal_name'].astype(str).str.contains('Pack_Temperature')][['id_or_address', 'signal_name', 'group']])
except Exception as e:
    print(f"Error: {e}")
