import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        xl = pd.ExcelFile(file_path)
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet_name, dtype=str)
            if sheet_name == 'variables':
                # Force start_index to string
                df.loc[df['id_or_address'] == '0x2F1', 'start_index'] = '1'
                df.loc[df['id_or_address'] == '0x2F2', 'start_index'] = '5'
                df.loc[df['id_or_address'] == '0x2F3', 'start_index'] = '9'
                df.loc[df['id_or_address'] == '0x2F4', 'start_index'] = '13'
                
                df.loc[df['id_or_address'] == '0x2F6', 'start_index'] = '3'
                df.loc[df['id_or_address'] == '0x2F7', 'start_index'] = '7'
                df.loc[df['id_or_address'] == '0x2F8', 'start_index'] = '11'
                
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print("\nSuccessfully updated start_index as strings.")
except Exception as e:
    print(f"Error: {e}")
