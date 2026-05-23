"""SLIP-framed end-to-end smoke test against Arduino_BMS_SLIP.ino.

The point of this script is not to re-test BMS features (smoke_headless.py
already covers those in depth) — it's to prove that escape_mode = slip
survives an actual round trip with a real device. Specifically:

  Phase 0  Config sanity (escape_mode = slip, expected single frame)
  Phase 1  TX builder produces a SLIP-wrapped Reset Faults packet
  Phase 2  Live serial: SLIP-framed telemetry from the simulator is
           received and the inner CRC/length/payload all validate
  Phase 3  Pack Voltage decodes to a plausible value
  Phase 4  Reset Faults TX round-trips (host sends, simulator accepts,
           host sees the post-reset value reflected)

Run:  python smoke_slip.py [--port COM7] [--seconds 8]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QCoreApplication, QTimer

from app.commands.tx_command_builder import build_tx_command
from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.protocol.packet_parser import escape_frame
from app.serial_io.serial_worker import PollingWorker, SerialSettings


class Report:
    def __init__(self) -> None:
        self.passed: List[str] = []
        self.failed: List[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        print(f"[ OK ] {label}" + (f" - {detail}" if detail else ""))
        self.passed.append(label)

    def fail(self, label: str, detail: str = "") -> None:
        print(f"[FAIL] {label}" + (f" - {detail}" if detail else ""))
        self.failed.append(label)

    def note(self, msg: str) -> None:
        print(f"[note] {msg}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument("--boot-delay", type=float, default=3.0)
    parser.add_argument("--skip-device", action="store_true")
    args = parser.parse_args()

    rep = Report()
    config = load_config(Path("app/resources/slip_config_template"))

    # ------------------------------------------------------------------
    # Phase 0  Config sanity
    # ------------------------------------------------------------------
    print("\n=== Phase 0  SLIP config sanity ===")
    if config.protocol.escape_mode == "slip":
        rep.ok("escape_mode = slip")
    else:
        rep.fail(f"escape_mode wrong: {config.protocol.escape_mode!r}")
    if config.protocol.footer == b"\xEE":
        rep.ok("inner footer is 0xEE (matches Arduino_BMS_SLIP.ino)")
    else:
        rep.fail(f"inner footer drift: {config.protocol.footer!r}")
    if "Reset Faults" in config.tx_commands:
        rep.ok("Reset Faults TX command registered")
    else:
        rep.fail("Reset Faults TX command missing")

    # ------------------------------------------------------------------
    # Phase 1  TX builder produces SLIP-wrapped bytes
    # ------------------------------------------------------------------
    print("\n=== Phase 1  TX builder produces SLIP-wrapped bytes ===")
    try:
        built = build_tx_command(config, "Reset Faults", {})
        # The wire packet must start AND end with 0xC0 (SLIP END markers)
        # and the inner frame after un-escaping must look like the
        # standard AA55... header_to_payload CRC16 + 0xEE footer.
        if built.startswith(b"\xC0") and built.endswith(b"\xC0"):
            rep.ok(f"SLIP envelope on Reset Faults: {built.hex().upper()}")
        else:
            rep.fail("Reset Faults bytes not SLIP-wrapped", built.hex().upper())
        # Verify the wrap is correct by re-running escape_frame on the
        # equivalent unframed payload and confirming the byte sequences match.
        from app.protocol.packet_builder import build_packet
        plain_frame_bytes = build_packet(
            # Build with escape_mode=none to get the inner Bytehound frame.
            __import__("dataclasses").replace(config.protocol, escape_mode="none"),
            0x1000, b"\xFF\xFF",
        )
        expected = escape_frame(plain_frame_bytes, "slip")
        if built == expected:
            rep.ok("SLIP envelope is byte-identical to escape_frame(inner, 'slip')")
        else:
            rep.fail("SLIP envelope mismatch",
                     f"got {built.hex().upper()} expected {expected.hex().upper()}")
    except Exception as e:
        rep.fail("Reset Faults build raised", str(e))

    if args.skip_device:
        rep.note("--skip-device set: device-dependent phases skipped")
        return _summarize(rep)

    # ------------------------------------------------------------------
    # Phase 2  Live serial — SLIP-framed RX
    # ------------------------------------------------------------------
    print(f"\n=== Phase 2  Live SLIP serial on {args.port} ===")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    settings = SerialSettings(port=args.port, baud_rate=115200)
    worker = PollingWorker(settings, config.protocol, config.polling_schedules)

    pkt_total = 0
    crc_errors = 0
    pack_voltages: List[float] = []
    tx_seen: List[bytes] = []

    def on_packets(packets):
        nonlocal pkt_total, crc_errors
        for item in packets:
            # PollingWorker emits (ParsedPacket, decoded-or-None) tuples.
            pkt, pre_decoded = item if isinstance(item, tuple) else (item, None)
            pkt_total += 1
            if not pkt.ok:
                crc_errors += 1
                continue
            decoded = pre_decoded if pre_decoded is not None else decode_frame(config, pkt.frame_id, pkt.payload)
            for sig in decoded.signals:
                if sig.signal_name == "Pack Voltage" and sig.scaled_value is not None:
                    pack_voltages.append(sig.scaled_value)

    def on_tx(data: bytes):
        tx_seen.append(bytes(data))

    worker.packets_received.connect(on_packets)
    worker.tx_recorded.connect(on_tx)

    worker.open()
    worker.set_polling_global(False)
    boot_ms = int(args.boot_delay * 1000)

    def send_reset():
        try:
            worker.enqueue_priority_tx(build_tx_command(config, "Reset Faults", {}))
            rep.note(f"Reset Faults queued at t={(boot_ms + 1000) / 1000:.1f}s")
        except Exception as e:
            rep.note(f"Reset Faults build failed: {e}")

    QTimer.singleShot(boot_ms + 1000, send_reset)

    def stop():
        worker.close()
        app.quit()

    QTimer.singleShot(args.seconds * 1000, stop)
    app.exec()

    # ------------------------------------------------------------------
    # Phase 3  Frames received and decoded
    # ------------------------------------------------------------------
    print(f"\n=== Phase 3  Live results (rx packets={pkt_total}, crc_errors={crc_errors}) ===")
    if pkt_total > 0:
        rep.ok(f"SLIP-framed telemetry received ({pkt_total} packets)")
    else:
        rep.fail("No packets received — is the SLIP simulator flashed and powered?")
    if crc_errors == 0:
        rep.ok("Zero inner-CRC errors after SLIP unescaping")
    else:
        rep.fail(f"{crc_errors} inner-CRC errors after SLIP unescaping")
    if pack_voltages:
        latest = pack_voltages[-1]
        if 40.0 <= latest <= 60.0:
            rep.ok(f"Pack Voltage decoded plausibly: latest = {latest:.2f} V")
        else:
            rep.fail(f"Pack Voltage out of range: {latest:.2f} V")
    else:
        rep.fail("No Pack Voltage decoded")

    # ------------------------------------------------------------------
    # Phase 4  Reset Faults round-trip
    # ------------------------------------------------------------------
    print("\n=== Phase 4  Reset Faults round-trip ===")
    reset_packet = build_tx_command(config, "Reset Faults", {})
    if reset_packet in tx_seen:
        rep.ok(f"Reset Faults SLIP packet on wire: {reset_packet.hex().upper()}")
    else:
        rep.fail("Reset Faults SLIP packet missing from tx_recorded")
    # After Reset Faults, the simulator re-seeds pack_voltage_cv to 5000
    # (= 50.00 V). Within a couple of telemetry ticks (100 ms each) we
    # should see a reading at or below 50.5 V again.
    if any(v <= 50.5 for v in pack_voltages[-20:]):
        rep.ok("Pack Voltage observed at or below 50.5 V after Reset Faults (simulator reseeded)")
    else:
        rep.fail("Pack Voltage did not drop back near 50 V after Reset Faults")

    return _summarize(rep)


def _summarize(rep: Report) -> int:
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
