import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    xl = pd.ExcelFile(file_path)
    df_vars = pd.read_excel(xl, sheet_name='variables')
    df_bits = pd.read_excel(xl, sheet_name='bitfields')
    
    # Check if every signal_name + id_or_address combination in bitfields exists in variables
    bitfield_keys = df_bits[['id_or_address', 'signal_name']].drop_duplicates()
    var_keys = df_vars[['id_or_address', 'signal_name']].drop_duplicates()
    
    # Ensure they are strings
    bitfield_keys['id_or_address'] = bitfield_keys['id_or_address'].astype(str).str.strip()
    bitfield_keys['signal_name'] = bitfield_keys['signal_name'].astype(str).str.strip()
    var_keys['id_or_address'] = var_keys['id_or_address'].astype(str).str.strip()
    var_keys['signal_name'] = var_keys['signal_name'].astype(str).str.strip()
    
    merged = pd.merge(bitfield_keys, var_keys, on=['id_or_address', 'signal_name'], how='left', indicator=True)
    mismatches = merged[merged['_merge'] == 'left_only']
    
    if not mismatches.empty:
        print("Mismatches found in bitfields:")
        print(mismatches)
    else:
        print("All bitfields match variables successfully.")
except Exception as e:
    print(f"Error: {e}")
