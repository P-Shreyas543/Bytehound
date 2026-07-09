import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    xl = pd.ExcelFile(file_path)
    df_vars = pd.read_excel(xl, sheet_name='variables')
    
    print("Variables with 'Cell' in name or count > 1:")
    mask = df_vars['signal_name'].astype(str).str.contains('Cell', na=False, case=False) | (df_vars['count'] > 1)
    
    columns_to_show = ['id_or_address', 'signal_name', 'data_type', 'count', 'start_byte']
    # start_byte might not exist, check columns
    cols = [c for c in columns_to_show if c in df_vars.columns]
    
    print(df_vars[mask][cols].to_string())
    
    print("\nAll variables:")
    print(df_vars[cols].to_string())
    
except Exception as e:
    print(f"Error: {e}")
