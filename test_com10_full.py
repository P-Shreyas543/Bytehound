import sys
import time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
import openpyxl

from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_logging.raw_logger import RawLogger

def main():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    cfg_path = Path("Ather_v1_0_1.xlsx")
    cfg = load_config(cfg_path)
    print(f"Loaded config: {cfg.protocol.profile_name} (parser: {cfg.protocol.parser_type})")

    port = "COM10"
    baud = cfg.serial_defaults.baud_rate or 2000000
    settings = SerialSettings(port=port, baud_rate=baud)
    worker = PollingWorker(settings, cfg.protocol, cfg.polling_schedules)

    scratch_dir = Path("scratch")
    scratch_dir.mkdir(exist_ok=True)
    raw_path = scratch_dir / "ather_com10_raw.xlsx"
    dec_path = scratch_dir / "ather_com10_decoded.xlsx"
    raw_path.unlink(missing_ok=True)
    dec_path.unlink(missing_ok=True)

    raw_logger = RawLogger(raw_path, hex_format=cfg.protocol.raw_log_format)
    decoded_logger = DecodedLogger(dec_path, cfg)
    decoded_logger.polling_mode = False  # passive streaming

    rx_count = 0
    known_count = 0
    log_start = time.perf_counter()
    last_ui_print = 0

    def on_packets(packets):
        nonlocal rx_count, known_count
        for item in packets:
            pkt, pre_decoded = item if isinstance(item, tuple) else (item, None)
            if not pkt.ok:
                continue
            rx_count += 1
            raw_logger.log("RX", pkt.raw)
            if pkt.frame_id in cfg.frames:
                known_count += 1
                decoded = pre_decoded if pre_decoded is not None else decode_frame(cfg, pkt.frame_id, pkt.payload)
                elapsed_ms = int((time.perf_counter() - log_start) * 1000)
                decoded_logger.log_frame(decoded, elapsed_ms)

    worker.packets_received.connect(on_packets)

    print(f"Opening {port} at {baud} baud with full Bytehound pipeline...")
    worker.open()
    raw_logger.open()
    decoded_logger.open()

    test_duration = 4.0
    t0 = time.time()
    print(f"Streaming and logging for {test_duration} seconds...")

    try:
        while time.time() - t0 < test_duration:
            app.processEvents()
            now = time.time()
            if now - last_ui_print >= 1.0:
                last_ui_print = now
                print(f"  [T+{now-t0:.1f}s] Received {rx_count} total packets ({known_count} Ather DBC frames logged)")
            time.sleep(0.01)
    finally:
        print("Closing port and flushing Excel loggers...")
        worker.close()
        raw_logger.close()
        decoded_logger.close()

    print(f"\n--- SESSION SUMMARY ---")
    print(f"Total raw CAN packets received: {rx_count}")
    print(f"Ather DBC packets decoded & logged: {known_count}")

    if rx_count == 0:
        print("FAIL: No packets received on COM10.")
        sys.exit(1)

    # Inspect generated decoded Excel workbook
    wb = openpyxl.load_workbook(dec_path, read_only=True)
    ws = wb["Data"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    header = rows[0]
    data_rows = rows[1:]
    print(f"\nDecoded Excel log generated: {dec_path.resolve()}")
    print(f"Total rows logged: {len(data_rows)} (with {len(header)} columns)")

    # Print sample of the most recent logged telemetry
    if data_rows:
        latest = data_rows[-1]
        print("\n--- LATEST TELEMETRY SNAPSHOT FROM LOG ---")
        logged_items = {}
        for col_name, val in zip(header, latest):
            if val is not None and str(val).strip() != "":
                logged_items[col_name] = val

        # Print Pack & Vehicle Parameters
        print("\n  [Pack & Vehicle Parameters]")
        for k in ["Pack_Voltage", "Pack_Current", "Battery_SOC", "Auxiliary_12V_Voltage", "Vehicle_Speed", "Throttle_Position"]:
            matching = [col for col in logged_items if k in col]
            for m in matching:
                print(f"    {m}: {logged_items[m]}")

        # Print Cell Voltages
        print("\n  [Cell Voltages]")
        cv_items = {k: v for k, v in logged_items.items() if ("Cell_Voltage" in k or "Vol" in k) and "Calc" not in k and "min" not in k and "max" not in k}
        for k in sorted(cv_items.keys()):
            print(f"    {k}: {cv_items[k]}")

        # Print Temperatures
        print("\n  [Temperatures]")
        temp_items = {k: v for k, v in logged_items.items() if "Temp" in k and "Calc" not in k and "min" not in k and "max" not in k}
        for k in sorted(temp_items.keys()):
            print(f"    {k}: {temp_items[k]}")

        # Print Calculations
        print("\n  [Automatic Calculations]")
        calc_items = {k: v for k, v in logged_items.items() if any(op in k for op in ["min", "max", "diff", "avg", "sum", "Calc"])}
        for k in sorted(calc_items.keys()):
            print(f"    {k}: {calc_items[k]}")

    print("\nSUCCESS: COM10 live verification completed successfully!")

if __name__ == "__main__":
    main()
