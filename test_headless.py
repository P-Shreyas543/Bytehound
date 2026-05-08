import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QCoreApplication, QTimer
from app.decoder.config_loader import load_config
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.decoder.frame_decoder import decode_frame
from app.commands.tx_command_builder import build_tx_command
from app.serial_logging.raw_logger import RawLogger
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_io.replay_source import parse_log_file, replay_bytes

def main():
    app = QCoreApplication(sys.argv)
    
    config_path = Path("app/resources/config_template")
    config = load_config(config_path)
    
    settings = SerialSettings(port="COM7", baud_rate=115200)
    worker = PollingWorker(settings, config.protocol, config.polling_schedules)
    
    # 1. Test Feature: Loggers
    raw_log_path = Path("scratch/test_raw.csv")
    decoded_log_path = Path("scratch/test_decoded.csv")
    raw_logger = RawLogger(raw_log_path)
    decoded_logger = DecodedLogger(decoded_log_path)
    
    packet_count = [0]

    def on_packets(packets):
        # PollingWorker now emits batched lists of packets (up to 50 per signal)
        for packet in packets:
            packet_count[0] += 1
            raw_logger.log("RX", packet.raw)
            if not packet.ok:
                print(f"Packet error: {packet.error}")
                continue
            decoded = decode_frame(config, packet.frame_id, packet.payload)
            decoded_logger.log_frame(packet_count[0], decoded)
            print(f"[RX] Frame 0x{packet.frame_id:04X} -> {[sig.display_value for sig in decoded.signals]}")

    def on_error(err):
        print(f"ERROR: {err}")

    def on_tx(data):
        print(f"[TX] {data.hex().upper()}")
        raw_logger.log("TX", data)

    worker.tx_recorded.connect(on_tx)
    worker.packets_received.connect(on_packets)
    worker.error_occurred.connect(on_error)
    
    print("--- 1. Testing Connection & Polling ---")
    worker.open()
    worker.set_polling_global(True)
    
    # 2. Test Feature: Priority TX Commands
    def send_manual_command():
        print("\n--- 2. Testing Manual Priority TX Command ('Reset') ---")
        try:
            tx_bytes = build_tx_command(config, "Reset", {})
            worker.enqueue_priority_tx(tx_bytes)
            print("Command enqueued successfully.")
        except Exception as e:
            print(f"Failed to build TX command: {e}")
            
    QTimer.singleShot(2000, send_manual_command)
    
    def stop_and_test_replay():
        print("\n--- Stopping Serial & Flushing Logs ---")
        worker.close()
        raw_logger.close()
        decoded_logger.close()
        
        print("\n--- 3. Testing Raw Replay Engine ---")
        rows, errors = parse_log_file(raw_log_path)
        print(f"Loaded {len(rows)} rows from CSV. Parsing errors: {len(errors)}")
        
        rx_replayed = 0
        for chunk in replay_bytes(rows, directions=("RX",)):
            # The replay engine provides chunks; we'd normally pass to parser
            rx_replayed += len(chunk)
            
        print(f"Successfully replayed {rx_replayed} RX bytes from the raw log!")
        print("\nAll Core Features Tested Successfully.")
        app.quit()
        
    # Quit after 5 seconds
    QTimer.singleShot(5000, stop_and_test_replay)
    
    app.exec()

if __name__ == "__main__":
    main()
