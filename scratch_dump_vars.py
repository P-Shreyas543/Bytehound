import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    xl = pd.ExcelFile(file_path)
    df = pd.read_excel(xl, sheet_name='variables')
    pd.set_option('display.max_rows', None)
    print(df[['id_or_address', 'signal_name', 'group']])
except Exception as e:
    print(f"Error: {e}")
