from pathlib import Path
import sys
sys.path.insert(0, 'c:/Users/Shreyas/Documents/Python/Bytehound')
from app.decoder.config_loader import load_config

try:
    cfg = load_config(Path('c:/Users/Shreyas/Documents/Python/Bytehound/the_energy_company_4850.xlsx'))
    print("Config loaded successfully!")
    print(f"Total signals: {len(cfg.all_signals)}")
    for sig in sorted(cfg.all_signals, key=lambda s: s.signal_name)[:5]:
        print(f"{sig.signal_name} (frame {sig.frame_id:0X})")
except Exception as e:
    print(f"Error: {e}")
