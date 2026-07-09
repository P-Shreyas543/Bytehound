import pandas as pd

file_path = 'c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'
try:
    xl = pd.ExcelFile(file_path)
    df_vars = pd.read_excel(xl, sheet_name='variables')
    df_bits = pd.read_excel(xl, sheet_name='bitfields')
    
    print("Variables containing 'Contactor':")
    print(df_vars[df_vars['signal_name'].str.contains('Contactor', na=False, case=False)][['id_or_address', 'signal_name']])
    
    print("\nFrames containing 0x3F0:")
    df_frames = pd.read_excel(xl, sheet_name='frames')
    print(df_frames[df_frames['frame_id'].astype(str).str.contains('3F0', na=False)])
    
except Exception as e:
    print(f"Error: {e}")
