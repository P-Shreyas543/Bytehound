import sys
import time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_logging.raw_logger import RawLogger
import openpyxl

def main():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    cfg_path = Path("the_energy_company_48100.xlsx")
    cfg = load_config(cfg_path)
    
    # Waveshare CAN adapter at 2 Mbps default config
    settings = SerialSettings(port="COM7", baud_rate=2000000)
    worker = PollingWorker(settings, cfg.protocol, cfg.polling_schedules)
    
    raw_path = Path("scratch/com7_raw.xlsx")
    dec_path = Path("scratch/com7_decoded.xlsx")
    raw_path.unlink(missing_ok=True)
    dec_path.unlink(missing_ok=True)
    
    raw_logger = RawLogger(raw_path, hex_format=cfg.protocol.raw_log_format)
    decoded_logger = DecodedLogger(dec_path, cfg)
    decoded_logger.polling_mode = False # passive streaming
    
    rx_count = 0
    log_start = time.perf_counter()
    
    def on_packets(packets):
        nonlocal rx_count
        for item in packets:
            pkt, pre_decoded = item if isinstance(item, tuple) else (item, None)
            if not pkt.ok:
                continue
            rx_count += 1
            raw_logger.log("RX", pkt.raw)
            decoded = pre_decoded if pre_decoded is not None else decode_frame(cfg, pkt.frame_id, pkt.payload)
            elapsed_ms = int((time.perf_counter() - log_start) * 1000)
            decoded_logger.log_frame(decoded, elapsed_ms)
            
    worker.packets_received.connect(on_packets)
    
    print("Opening COM7 at 2000000 baud...")
    worker.open()
    raw_logger.open()
    decoded_logger.open()
    
    t0 = time.time()
    try:
        while time.time() - t0 < 8:
            app.processEvents()
            time.sleep(0.01)
    finally:
        print("Stopping logging and closing COM7 port...")
        worker.close()
        raw_logger.close()
        decoded_logger.close()
        
    print(f"Received {rx_count} packets")
    if rx_count == 0:
        print("FAIL: No packets received! Is the device streaming?")
        sys.exit(1)
        
    # Verify Decoded Excel Workbook
    wb = openpyxl.load_workbook(dec_path, read_only=True)
    ws = wb["Data"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    
    print(f"Generated decoded rows: {len(rows)}")
    if len(rows) < 2:
        print("FAIL: No data rows written to decoded log!")
        sys.exit(1)
        
    # Check if calculation columns exist and have non-None values
    calc_cols = []
    for col_idx, col_name in enumerate(rows[0]):
        if "Cell Voltages" in str(col_name) or "avg" in str(col_name):
            calc_cols.append((col_idx, col_name))
            
    if not calc_cols:
        print("FAIL: No calculation columns found in header!")
        sys.exit(1)
        
    print(f"Found calculation columns in Excel header: {[name for _, name in calc_cols]}")
    
    # Assert that calculation headers do NOT contain frame ID prefixes
    for _, col_name in calc_cols:
        if "0x" in col_name:
            print(f"FAIL: Calculation column header contains frame ID prefix: {col_name}")
            sys.exit(1)
            
    has_values = False
    for row in rows[1:]:
        for col_idx, col_name in calc_cols:
            val = row[col_idx]
            if val is not None:
                print(f"Successfully logged calculation value: {col_name} = {val}")
                has_values = True
                
    if not has_values:
        print("FAIL: All calculation column values are empty/None!")
        sys.exit(1)
        
    print("SUCCESS: Headless smoke test on COM7 with the_energy_company_48100.xlsx configuration passed!")
    sys.exit(0)

if __name__ == "__main__":
    main()
