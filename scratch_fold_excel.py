import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    xl = pd.ExcelFile(file_path)
    df_vars = pd.read_excel(xl, sheet_name='variables')
    
    # We want to remove all Cell_Voltage_X and Pack_Temperature_X (X >= 3)
    # and replace them with folded rows.
    
    mask_cells = df_vars['signal_name'].astype(str).str.match(r'Cell_Voltage_\d+')
    mask_temps = df_vars['signal_name'].astype(str).str.match(r'Pack_Temperature_([3-9]|1[0-9])')
    
    df_vars_clean = df_vars[~(mask_cells | mask_temps)].copy()
    
    # Prepare folded rows
    new_rows = []
    
    # Cells
    for frame, start_idx in [('0x2F1', 1), ('0x2F2', 5), ('0x2F3', 9), ('0x2F4', 13)]:
        new_rows.append({
            'id_or_address': frame,
            'signal_name': 'Cell_Voltage',
            'data_type': 'uint16',
            'count': 4,
            'start_index': start_idx,
            'byte_order': 'little',
            'scale': 0.001,
            'offset': 0,
            'unit': 'V',
            'group': 'Cell Voltages',
            'read_write': 'R',
            'min_value': 2000,
            'max_value': 4500,
            'enabled': True
        })
        
    # Temps
    for frame, start_idx in [('0x2F6', 3), ('0x2F7', 7), ('0x2F8', 11)]:
        new_rows.append({
            'id_or_address': frame,
            'signal_name': 'Pack_Temperature',
            'data_type': 'uint16',
            'count': 4,
            'start_index': start_idx,
            'byte_order': 'little',
            'scale': 1,
            'offset': -50,
            'unit': 'C',
            'group': 'Temperatures',
            'read_write': 'R',
            'min_value': -50,
            'max_value': 150,
            'enabled': True
        })
        
    df_new = pd.DataFrame(new_rows)
    df_vars_final = pd.concat([df_vars_clean, df_new], ignore_index=True)
    
    # Ensure start_index column exists in the final df
    if 'start_index' not in df_vars_final.columns:
        df_vars_final['start_index'] = pd.NA
        
    # Write back
    with pd.ExcelWriter(file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        for sheet_name in xl.sheet_names:
            if sheet_name == 'variables':
                df_vars_final.to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                df = pd.read_excel(xl, sheet_name=sheet_name)
                df.to_excel(writer, sheet_name=sheet_name, index=False)

    print("Successfully folded Cell Voltages and Pack Temperatures.")
except Exception as e:
    print(f"Error: {e}")
