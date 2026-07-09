import pandas as pd
import json

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    xl = pd.ExcelFile(file_path)
    data = {}
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet)
        df = df.dropna(how='all')
        data[sheet] = df.head(3).to_dict(orient='records')
    
    print(json.dumps(data, indent=2, default=str))
except Exception as e:
    print(f"Error: {e}")
