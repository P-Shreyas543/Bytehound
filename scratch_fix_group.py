import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        xl = pd.ExcelFile(file_path)
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet_name)
            if sheet_name == 'variables':
                # Fix the group name for Pack_Temperature variables that were folded
                mask = df['signal_name'] == 'Pack_Temperature'
                df.loc[mask, 'group'] = 'Pack Temperatures'
                
                print("Updated variables sheet:")
                print(df[mask][['id_or_address', 'signal_name', 'group']])
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print("\nSuccessfully updated group name for Pack Temperatures.")
except Exception as e:
    print(f"Error: {e}")
