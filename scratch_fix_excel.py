import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        xl = pd.ExcelFile(file_path)
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet_name)
            if sheet_name == 'bitfields':
                df.loc[df['signal_name'] == 'Contactor_Status', 'id_or_address'] = '0x2F9'
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print("Successfully updated bitfields sheet.")
except Exception as e:
    print(f"Error: {e}")
