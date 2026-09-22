"""Test PollingWorker on COM10 to capture all errors/warnings seen by GUI."""

import time
import sys
from PySide6.QtCore import QCoreApplication
from app.decoder.config_loader import load_config
from app.serial_io.serial_worker import PollingWorker, SerialSettings

app = QCoreApplication(sys.argv)

cfg = load_config("Ather_v1_0_1.xlsx")
settings = SerialSettings(
    port="COM10",
    baud_rate=2000000,
    data_bits=8,
    stop_bits=1,
    parity="N",
    connection_type="serial",
)

worker = PollingWorker(
    settings=settings,
    protocol=cfg.protocol,
    schedules=cfg.polling_schedules,
    decode_config=cfg,
)

warnings = []
errors = []
packets = []
metrics_history = []

worker.warning_occurred.connect(lambda msg: warnings.append((time.time(), msg)))
worker.error_occurred.connect(lambda msg: errors.append((time.time(), msg)))
worker.metrics_updated.connect(lambda t, c, r: metrics_history.append((t, c, r)))
worker.packets_received.connect(lambda pkts: packets.extend(pkts))

print("Starting worker on COM10 @ 2000000...")
worker.open()

t0 = time.time()
while time.time() - t0 < 6.0:
    app.processEvents()
    time.sleep(0.05)

worker.stop()
worker.wait(2000)

print(f"\n--- WORKER RUN SUMMARY (6.0s) ---")
print(f"Total Batched Packets Received: {len(packets)}")
print(f"Total Warnings Emitted: {len(warnings)}")
print(f"Total Errors Emitted:   {len(errors)}")
if metrics_history:
    last_m = metrics_history[-1]
    print(f"Last Metrics: Timeouts={last_m[0]}, CRC/Frame Errors={last_m[1]}, RxBytes={last_m[2]}")

if warnings:
    print(f"\nWarnings ({len(warnings)}):")
    for t, w in warnings[:15]:
        print(f"  [{t-t0:4.2f}s] {w}")

if errors:
    print(f"\nErrors ({len(errors)}):")
    for t, e in errors[:15]:
        print(f"  [{t-t0:4.2f}s] {e}")

# Check packet health
good_pkts = sum(1 for p, d in packets if p.ok)
bad_pkts = sum(1 for p, d in packets if not p.ok)
print(f"\nPacket Breakdown: Good={good_pkts}, Bad={bad_pkts}")
