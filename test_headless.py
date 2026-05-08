"""End-to-end headless test against the Arduino BMS simulator.

Exercises every feature the user asked about:

1. Polling             - all configured frames are received over serial
2. Bitfields           - Status_Bits decodes into a dict of named bit values
3. Enums               - Mode decodes into the enum label from enums.csv
4. TX commands         - Reset (static payload) is built and goes on the wire
5. Parameter editor    - Set_Voltage_Limit is built from a user-supplied value
                         AND the Arduino reflects the new value back via 0x2000
6. Loggers + replay    - raw / decoded CSV write and round-trip cleanly

Run:  python test_headless.py [--port COM7]

Exit status is the number of failed checks (0 = all green).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QCoreApplication, QTimer

from app.commands.tx_command_builder import build_tx_command
from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.serial_io.replay_source import parse_log_file, replay_bytes
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_logging.raw_logger import RawLogger


# ---------------------------------------------------------------- helpers
class Report:
    def __init__(self) -> None:
        self.passed: List[str] = []
        self.failed: List[str] = []
        self.notes: List[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        line = f"[ OK ] {label}" + (f" - {detail}" if detail else "")
        print(line)
        self.passed.append(label)

    def fail(self, label: str, detail: str = "") -> None:
        line = f"[FAIL] {label}" + (f" - {detail}" if detail else "")
        print(line)
        self.failed.append(label)

    def note(self, msg: str) -> None:
        print(f"[note] {msg}")
        self.notes.append(msg)


# --------------------------------------------------------------- test core
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--seconds", type=int, default=10,
                        help="how long to listen on the serial port (>=8 recommended)")
    parser.add_argument("--target-voltage", type=float, default=58.5,
                        help="voltage limit (V) to write via Set_Voltage_Limit")
    parser.add_argument("--boot-delay", type=float, default=3.0,
                        help="seconds to wait after open before enabling polling/TX. "
                             "Opening the COM port toggles DTR which resets the Arduino; "
                             "any commands sent during the ~1.5s bootloader window are lost.")
    args = parser.parse_args()

    rep = Report()
    config = load_config(Path("app/resources/config_template"))

    # ----- 0. Static config sanity ----------------------------------------
    print("\n=== 0. Config sanity ===")
    if 0x3000 in config.signals_by_frame:
        rep.ok("Status_Flags frame 0x3000 present in config")
    else:
        rep.fail("Status_Flags frame 0x3000 missing from variables.csv")

    if (0x3000, "Status_Bits") in config.bitfields:
        bits = config.bitfields[(0x3000, "Status_Bits")]
        names = [b.bit_name for b in bits]
        if "Charging" in names and "Ready" in names and len(names) == 8:
            rep.ok(f"Status_Bits bitfield has 8 named bits: {names}")
        else:
            rep.fail("Status_Bits bitfield missing expected labels", str(names))
    else:
        rep.fail("Status_Bits bitfield not registered in config")

    if (0x3000, "Mode") in config.enums:
        labels = config.enums[(0x3000, "Mode")]
        if labels.get(0) == "Idle" and labels.get(3) == "Fault":
            rep.ok(f"Mode enum has expected labels: {labels}")
        else:
            rep.fail("Mode enum missing expected labels", str(labels))
    else:
        rep.fail("Mode enum not registered in config")

    if "Set_Voltage_Limit" in config.tx_commands:
        cmd = config.tx_commands["Set_Voltage_Limit"]
        if cmd.fields and cmd.fields[0].field_name == "voltage_v":
            rep.ok(f"Set_Voltage_Limit command has parameter '{cmd.fields[0].field_name}'")
        else:
            rep.fail("Set_Voltage_Limit has no fields - parameter editor would be empty")
    else:
        rep.fail("Set_Voltage_Limit command not registered in config")

    # ----- 1. Parameter editor / TX builder (offline, byte-exact) ---------
    print("\n=== 1. Parameter editor (offline byte-exact) ===")
    try:
        bytes_585 = build_tx_command(config, "Set_Voltage_Limit", {"voltage_v": args.target_voltage})
        # Expected packet for 58.5 V: header AA55, frame 0x2001 LE, len 02,
        # payload = round((58.5-0)/0.1) = 585 = 0x0249 -> 49 02 (LE),
        # CRC16 modbus over [AA 55 01 20 02 49 02], LE, then footer EE.
        from app.protocol.crc import compute as crc_compute
        coverage = bytes([0xAA, 0x55, 0x01, 0x20, 0x02]) + (
            int(round(args.target_voltage / 0.1)).to_bytes(2, "little")
        )
        crc = crc_compute("crc16_modbus", coverage)
        expected = coverage + crc.to_bytes(2, "little") + b"\xEE"
        if bytes_585 == expected:
            rep.ok(f"Set_Voltage_Limit({args.target_voltage} V) bytes = {bytes_585.hex().upper()}")
        else:
            rep.fail("Set_Voltage_Limit byte mismatch",
                     f"got {bytes_585.hex().upper()} expected {expected.hex().upper()}")
    except Exception as e:
        rep.fail("Set_Voltage_Limit build raised", str(e))

    # Range enforcement check: 99.0 V should be rejected (max 60.0).
    try:
        build_tx_command(config, "Set_Voltage_Limit", {"voltage_v": 99.0})
        rep.fail("Set_Voltage_Limit(99 V) should have been rejected by max bound")
    except Exception:
        rep.ok("Set_Voltage_Limit enforces max bound (99.0 V rejected)")

    # ----- 2. Live serial: polling + bitfields + enums + TX ---------------
    print(f"\n=== 2. Live serial on {args.port} for {args.seconds} s ===")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    settings = SerialSettings(port=args.port, baud_rate=115200)
    worker = PollingWorker(settings, config.protocol, config.polling_schedules)

    Path("scratch").mkdir(exist_ok=True)
    raw_path = Path("scratch/test_raw.csv")
    dec_path = Path("scratch/test_decoded.csv")
    raw_logger = RawLogger(raw_path)
    decoded_logger = DecodedLogger(dec_path)

    # Per-feature observation buckets
    seen_frame_ids: set[int] = set()
    pkt_total = 0
    crc_errors = 0
    last_voltage_limit: List[float] = []   # appended each time 0x2000 arrives
    bitfield_observations: List[Dict[str, bool]] = []
    enum_observations: List[str] = []
    tx_seen: List[bytes] = []

    def on_packets(packets):
        nonlocal pkt_total, crc_errors
        for pkt in packets:
            pkt_total += 1
            raw_logger.log("RX", pkt.raw)
            if not pkt.ok:
                crc_errors += 1
                continue
            seen_frame_ids.add(pkt.frame_id)
            decoded = decode_frame(config, pkt.frame_id, pkt.payload)
            decoded_logger.log_frame(pkt_total, decoded)

            for sig in decoded.signals:
                if sig.frame_id == 0x2000 and sig.signal_name == "Voltage_Limit" and sig.scaled_value is not None:
                    last_voltage_limit.append(sig.scaled_value)
                if sig.frame_id == 0x3000 and sig.signal_name == "Status_Bits" and sig.bit_values:
                    bitfield_observations.append(dict(sig.bit_values))
                if sig.frame_id == 0x3000 and sig.signal_name == "Mode" and sig.enum_label:
                    enum_observations.append(sig.enum_label)

    def on_tx(data: bytes):
        tx_seen.append(bytes(data))
        raw_logger.log("TX", data)

    def on_error(msg: str):
        rep.note(f"worker error: {msg}")

    worker.packets_received.connect(on_packets)
    worker.tx_recorded.connect(on_tx)
    worker.error_occurred.connect(on_error)

    worker.open()
    # Polling stays OFF until the Arduino has had time to come out of its
    # DTR-triggered bootloader (~1.5 s on a Mega). Until then we just listen
    # passively and let the streaming telemetry flow.
    worker.set_polling_global(False)

    boot_ms = int(args.boot_delay * 1000)

    def enable_polling():
        worker.set_polling_global(True)
        rep.note(f"polling enabled at t={args.boot_delay:.1f}s")

    def send_reset():
        try:
            worker.enqueue_priority_tx(build_tx_command(config, "Reset", {}))
            rep.note(f"Reset queued at t={(boot_ms + 1000) / 1000:.1f}s")
        except Exception as e:
            rep.note(f"Reset build failed: {e}")

    def send_set_limit():
        try:
            worker.enqueue_priority_tx(
                build_tx_command(config, "Set_Voltage_Limit", {"voltage_v": args.target_voltage})
            )
            rep.note(f"Set_Voltage_Limit queued at t={(boot_ms + 3000) / 1000:.1f}s")
        except Exception as e:
            rep.note(f"Set_Voltage_Limit build failed: {e}")

    QTimer.singleShot(boot_ms, enable_polling)
    QTimer.singleShot(boot_ms + 1000, send_reset)
    QTimer.singleShot(boot_ms + 3000, send_set_limit)

    # Stop after `args.seconds` seconds and run post-checks.
    def stop():
        worker.close()
        raw_logger.close()
        decoded_logger.close()
        app.quit()

    QTimer.singleShot(args.seconds * 1000, stop)
    app.exec()

    # ----- 3. Post-run live-channel assertions ----------------------------
    print(f"\n=== 3. Live results (rx packets={pkt_total}, crc_errors={crc_errors}) ===")
    if 0x1000 in seen_frame_ids:
        rep.ok("Frame 0x1000 (BMS_Status) received")
    else:
        rep.fail("Frame 0x1000 NOT received - is the simulator running?")

    if 0x2000 in seen_frame_ids:
        rep.ok("Frame 0x2000 (BMS_Settings) received")
    else:
        rep.fail("Frame 0x2000 NOT received")

    if 0x3000 in seen_frame_ids:
        rep.ok("Frame 0x3000 (Status_Flags) received")
    else:
        rep.fail("Frame 0x3000 NOT received - re-flash Arduino with the updated sketch")

    if crc_errors == 0:
        rep.ok("Zero CRC errors over the run")
    else:
        rep.fail(f"{crc_errors} CRC errors observed")

    # ----- 4. Bitfields decoded with named bits ---------------------------
    print("\n=== 4. Bitfield decoding ===")
    if bitfield_observations:
        sample = bitfield_observations[-1]
        expected_keys = {"Charging", "Discharging", "Balancing", "Fault",
                         "OverVoltage", "UnderVoltage", "OverTemp", "Ready"}
        if expected_keys.issubset(sample.keys()):
            rep.ok(f"Status_Bits decoded with all 8 named bits, latest={sample}")
        else:
            rep.fail("Status_Bits bit_values missing keys",
                     f"got {set(sample.keys())}")
    else:
        rep.fail("No Status_Bits decoded - did 0x3000 arrive?")

    # ----- 5. Enum labels resolved ---------------------------------------
    print("\n=== 5. Enum decoding ===")
    if enum_observations:
        unique = sorted(set(enum_observations))
        rep.ok(f"Mode enum labels resolved: {unique}")
    else:
        rep.fail("No Mode enum labels decoded - did 0x3000 arrive?")

    # ----- 6. TX commands actually went out ------------------------------
    print("\n=== 6. TX commands ===")
    reset_packet = build_tx_command(config, "Reset", {})
    setlim_packet = build_tx_command(config, "Set_Voltage_Limit",
                                     {"voltage_v": args.target_voltage})
    if reset_packet in tx_seen:
        rep.ok(f"Reset packet seen on wire: {reset_packet.hex().upper()}")
    else:
        rep.fail("Reset packet not in tx_recorded stream")
    if setlim_packet in tx_seen:
        rep.ok(f"Set_Voltage_Limit packet seen on wire: {setlim_packet.hex().upper()}")
    else:
        rep.fail("Set_Voltage_Limit packet not in tx_recorded stream")

    # ----- 7. Round-trip: Arduino reflects the new voltage limit ----------
    print("\n=== 7. Set_Voltage_Limit round-trip ===")
    if last_voltage_limit:
        before = last_voltage_limit[: max(1, len(last_voltage_limit) // 3)]
        after = last_voltage_limit[-3:]
        rep.note(f"Voltage_Limit timeline (first/last): {before[:3]} ... {after}")
        if any(abs(v - args.target_voltage) < 0.05 for v in last_voltage_limit):
            rep.ok(f"Voltage_Limit reflected target {args.target_voltage} V at least once")
        else:
            rep.fail(
                f"Voltage_Limit never reached {args.target_voltage} V "
                f"(seen {sorted(set(last_voltage_limit))[:6]}...)"
            )
    else:
        rep.fail("No 0x2000 frames captured - cannot check round-trip")

    # ----- 8. Logger + replay round-trip ---------------------------------
    print("\n=== 8. Logger / replay round-trip ===")
    rows, errors = parse_log_file(raw_path)
    if errors:
        rep.fail(f"Raw log re-parse had {len(errors)} errors")
    else:
        rep.ok(f"Raw log parsed back: {len(rows)} rows, 0 errors")
    rx_bytes = sum(len(chunk) for chunk in replay_bytes(rows, directions=("RX",)))
    if rx_bytes > 0:
        rep.ok(f"Replay engine yielded {rx_bytes} RX bytes")
    else:
        rep.fail("Replay yielded zero RX bytes")

    # ----- Summary --------------------------------------------------------
    print("\n========================== SUMMARY ==========================")
    print(f"PASSED: {len(rep.passed)}")
    print(f"FAILED: {len(rep.failed)}")
    if rep.failed:
        print("\nFailures:")
        for f in rep.failed:
            print(f"  - {f}")
    print("=============================================================")
    return len(rep.failed)


if __name__ == "__main__":
    sys.exit(main())
