"""End-to-end Modbus RTU headless test against MCU_BMS_Modbus.ino.

Exercises every Modbus-specific code path on both sides of the wire:

  Phase 0  Static config sanity (Modbus protocol, 15 signals, 1 TX command)
  Phase 1  TX builder byte-exactness for FC06 single-register write
  Phase 2  Live serial: FC03 polling against the Modbus simulator
  Phase 3  All declared registers received
  Phase 4  Bitfield decoding from register 0x0030
  Phase 5  Enum decoding from register 0x0031
  Phase 6  Set Voltage Limit (FC06) round-trip
  Phase 7  Cell Voltages CalcGroups (min/max/avg/diff)
  Phase 8  modbus_node_address mismatch — slave 99 should yield zero replies

Run:  python smoke_modbus.py [--port COM7] [--seconds 12]

Exit status is the number of failed checks (0 = all green).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QCoreApplication, QTimer

from app.commands.tx_command_builder import build_tx_command
from app.decoder.calculations import calculate_group_value
from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.protocol.packet_builder import build_modbus_packet
from app.serial_io.serial_worker import PollingWorker, SerialSettings


class Report:
    def __init__(self) -> None:
        self.passed: List[str] = []
        self.failed: List[str] = []

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--seconds", type=int, default=12)
    parser.add_argument("--target-voltage", type=float, default=57.5)
    parser.add_argument("--boot-delay", type=float, default=3.0)
    parser.add_argument("--skip-device", action="store_true")
    parser.add_argument("--skip-node-mismatch", action="store_true",
                        help="skip Phase 8 (saves ~10 s of test runtime)")
    args = parser.parse_args()

    rep = Report()
    config = load_config(Path("app/resources/modbus_config_template"))

    # ------------------------------------------------------------------
    # Phase 0  Config sanity
    # ------------------------------------------------------------------
    print("\n=== Phase 0  Modbus config sanity ===")
    if config.protocol.parser_type == "modbus_rtu":
        rep.ok("parser_type = modbus_rtu")
    else:
        rep.fail(f"parser_type wrong: {config.protocol.parser_type!r}")
    if config.protocol.modbus_node_address == 1:
        rep.ok("modbus_node_address = 1 (matches MCU_BMS_Modbus.ino)")
    else:
        rep.fail(f"modbus_node_address wrong: {config.protocol.modbus_node_address}")

    sig_count = sum(len(v) for v in config.signals_by_frame.values())
    if sig_count == 15:
        rep.ok(f"15 signals registered ({sig_count})")
    else:
        rep.fail(f"signal count drift: got {sig_count}, expected 15")

    if len(config.polling_schedules) == 15:
        rep.ok(f"15 polling targets registered ({len(config.polling_schedules)})")
    else:
        rep.fail(f"polling target count drift: got {len(config.polling_schedules)}")

    if (0x0030, "Status Bits") in config.bitfields:
        rep.ok("Status Bits bitfield (register 0x0030) registered")
    else:
        rep.fail("Status Bits bitfield not registered")
    if (0x0031, "BMS State") in config.enums:
        rep.ok("BMS State enum (register 0x0031) registered")
    else:
        rep.fail("BMS State enum not registered")
    if "Set Voltage Limit" in config.tx_commands:
        rep.ok("Set Voltage Limit TX command registered")
    else:
        rep.fail("Set Voltage Limit TX command missing")

    # ------------------------------------------------------------------
    # Phase 1  TX builder byte-exactness for FC06
    # ------------------------------------------------------------------
    print("\n=== Phase 1  FC06 byte-exactness (Set Voltage Limit) ===")
    try:
        built = build_tx_command(
            config, "Set Voltage Limit", {"Voltage Limit (V)": args.target_voltage}
        )
        # Expected Modbus RTU FC06 request:
        #   [node][06][reg_hi][reg_lo][val_hi][val_lo][crc_lo][crc_hi]
        raw = int(round(args.target_voltage / 0.01))
        body = bytes([0x01, 0x06]) + (0x0028).to_bytes(2, "big") + raw.to_bytes(2, "big")
        from app.protocol.crc import compute as crc_compute
        crc = crc_compute("crc16_modbus", body)
        expected = body + crc.to_bytes(2, "little")
        if built == expected:
            rep.ok(f"FC06 bytes = {built.hex().upper()}")
        else:
            rep.fail("FC06 byte mismatch",
                     f"got {built.hex().upper()} expected {expected.hex().upper()}")
    except Exception as e:
        rep.fail("Set Voltage Limit build raised", str(e))

    # build_modbus_packet with empty payload should be FC03 (read holding).
    fc03 = build_modbus_packet(config.protocol, 0x0010, b"")
    if len(fc03) == 8 and fc03[1] == 0x03:
        rep.ok(f"FC03 read of 0x0010 = {fc03.hex().upper()}")
    else:
        rep.fail("FC03 build wrong", fc03.hex().upper())

    if args.skip_device:
        rep.note("--skip-device set: device-dependent phases skipped")
        return _summarize(rep)

    # ------------------------------------------------------------------
    # Phase 2  Live serial — Modbus polling
    # ------------------------------------------------------------------
    print(f"\n=== Phase 2  Live Modbus on {args.port} @ 19200 ===")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    settings = SerialSettings(
        port=args.port,
        baud_rate=config.serial_defaults.baud_rate,
        data_bits=config.serial_defaults.data_bits,
        stop_bits=config.serial_defaults.stop_bits,
        parity=config.serial_defaults.parity,
        timeout_ms=config.serial_defaults.timeout_ms,
    )
    worker = PollingWorker(settings, config.protocol, config.polling_schedules)

    seen_addresses: set[int] = set()
    pkt_total = 0
    crc_errors = 0
    voltage_limit_timeline: List[float] = []
    cell_voltage_obs: Dict[str, float] = {}
    bitfield_observations: List[Dict[str, bool]] = []
    enum_observations: List[str] = []
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
            seen_addresses.add(pkt.frame_id)
            decoded = pre_decoded if pre_decoded is not None else decode_frame(config, pkt.frame_id, pkt.payload)
            for sig in decoded.signals:
                if sig.signal_name == "Voltage Limit" and sig.scaled_value is not None:
                    voltage_limit_timeline.append(sig.scaled_value)
                if sig.signal_name.startswith("Cell Voltage") and sig.scaled_value is not None:
                    cell_voltage_obs[sig.signal_name] = sig.scaled_value
                if sig.signal_name == "Status Bits" and sig.bit_values:
                    bitfield_observations.append(dict(sig.bit_values))
                if sig.signal_name == "BMS State" and sig.enum_label:
                    enum_observations.append(sig.enum_label)

    def on_tx(data: bytes):
        tx_seen.append(bytes(data))

    def on_error(msg: str):
        rep.note(f"worker error: {msg}")

    worker.packets_received.connect(on_packets)
    worker.tx_recorded.connect(on_tx)
    worker.error_occurred.connect(on_error)

    worker.open()
    worker.set_polling_global(False)
    boot_ms = int(args.boot_delay * 1000)

    def enable_polling():
        worker.set_polling_global(True)
        rep.note(f"polling enabled at t={args.boot_delay:.1f}s")

    def send_set_limit():
        try:
            worker.enqueue_priority_tx(build_tx_command(
                config, "Set Voltage Limit", {"Voltage Limit (V)": args.target_voltage}
            ))
            rep.note(f"Set Voltage Limit queued at t={(boot_ms + 4000) / 1000:.1f}s")
        except Exception as e:
            rep.note(f"Set Voltage Limit build failed: {e}")

    QTimer.singleShot(boot_ms, enable_polling)
    QTimer.singleShot(boot_ms + 4000, send_set_limit)

    def stop():
        worker.close()
        app.quit()

    QTimer.singleShot(args.seconds * 1000, stop)
    app.exec()

    # ------------------------------------------------------------------
    # Phase 3  Registers received
    # ------------------------------------------------------------------
    print(f"\n=== Phase 3  Live results (rx packets={pkt_total}, crc_errors={crc_errors}) ===")
    expected_addrs = {0x0010, 0x0011, 0x0012, 0x0013, 0x0028, 0x0030, 0x0031} | set(range(0x0020, 0x0028))
    missing = expected_addrs - seen_addresses
    if not missing:
        rep.ok(f"All {len(expected_addrs)} declared registers responded to FC03")
    else:
        rep.fail(f"Missing register responses: {sorted(f'0x{a:04X}' for a in missing)}")
    if crc_errors == 0:
        rep.ok("Zero Modbus CRC errors over the run")
    else:
        rep.fail(f"{crc_errors} CRC errors observed")

    # ------------------------------------------------------------------
    # Phase 4  Bitfield decoding
    # ------------------------------------------------------------------
    print("\n=== Phase 4  Bitfield decoding (Status Bits @ 0x0030) ===")
    if bitfield_observations:
        sample = bitfield_observations[-1]
        expected_keys = {"Charging", "Discharging", "Balancing", "Fault",
                         "Overvoltage", "Undervoltage", "Overtemp", "Ready"}
        if expected_keys.issubset(sample.keys()):
            rep.ok(f"Status Bits decoded with all 8 named bits, latest={sample}")
        else:
            rep.fail("Status Bits missing keys", str(sample.keys()))
    else:
        rep.fail("No Status Bits observations — did 0x0030 ever respond?")

    # ------------------------------------------------------------------
    # Phase 5  Enum decoding
    # ------------------------------------------------------------------
    print("\n=== Phase 5  Enum decoding (BMS State @ 0x0031) ===")
    if enum_observations:
        unique = sorted(set(enum_observations))
        rep.ok(f"BMS State labels resolved: {unique}")
        if len(unique) >= 2:
            rep.ok(f"BMS State cycled across {len(unique)} distinct labels")
        else:
            rep.fail("BMS State did not cycle — only one label observed")
    else:
        rep.fail("No BMS State labels observed — did 0x0031 ever respond?")

    # ------------------------------------------------------------------
    # Phase 6  Set Voltage Limit round-trip
    # ------------------------------------------------------------------
    print("\n=== Phase 6  Set Voltage Limit round-trip ===")
    if voltage_limit_timeline:
        if any(abs(v - args.target_voltage) < 0.05 for v in voltage_limit_timeline):
            rep.ok(f"Voltage Limit reflected target {args.target_voltage} V after FC06 write")
        else:
            rep.fail(
                f"Voltage Limit never reached {args.target_voltage} V "
                f"(saw {sorted(set(voltage_limit_timeline))[:6]})"
            )
    else:
        rep.fail("No 0x0028 responses captured — cannot check round-trip")

    setlim_packet = build_tx_command(
        config, "Set Voltage Limit", {"Voltage Limit (V)": args.target_voltage}
    )
    if setlim_packet in tx_seen:
        rep.ok(f"FC06 packet went out on the wire: {setlim_packet.hex().upper()}")
    else:
        rep.fail("FC06 packet not in tx_recorded stream")

    # ------------------------------------------------------------------
    # Phase 7  CalcGroups over the 8 cell voltages
    # ------------------------------------------------------------------
    print("\n=== Phase 7  CalcGroups (Cell Voltages min/max/avg/diff) ===")
    if len(cell_voltage_obs) == 8:
        vals = list(cell_voltage_obs.values())
        expected = {
            "min":  min(vals),
            "max":  max(vals),
            "diff": max(vals) - min(vals),
            "avg":  sum(vals) / len(vals),
        }
        calcs = [g for g in config.calc_groups if g.group == "Cell Voltages"]
        for spec in calcs:
            try:
                got = calculate_group_value(spec, vals)
            except Exception as e:
                rep.fail(f"calc {spec.stat!r} raised", str(e))
                continue
            want = expected[spec.stat]
            if abs(got - want) < 1e-9:
                rep.ok(f"Cell Voltages {spec.stat} = {got:.3f}V (matches hand-computed)")
            else:
                rep.fail(f"Cell Voltages {spec.stat} mismatch: got {got}, expected {want}")
    else:
        rep.fail(f"Expected 8 cell voltages, observed {len(cell_voltage_obs)}: "
                 f"{sorted(cell_voltage_obs.keys())}")

    # ------------------------------------------------------------------
    # Phase 8  modbus_node_address mismatch
    # Open a fresh worker with the protocol's node_address overridden to 99
    # (the Arduino sketch only answers address 1). We should see zero
    # successful packets after the boot delay — proving the field actually
    # gates which device responds.
    # ------------------------------------------------------------------
    if not args.skip_node_mismatch:
        print("\n=== Phase 8  modbus_node_address mismatch (slave=99) ===")
        from dataclasses import replace
        mismatched_protocol = replace(config.protocol, modbus_node_address=99)
        mismatched_worker = PollingWorker(
            settings, mismatched_protocol, config.polling_schedules
        )
        mismatched_count = [0]

        def on_mismatched(packets):
            for pkt in packets:
                if pkt.ok:
                    mismatched_count[0] += 1

        mismatched_worker.packets_received.connect(on_mismatched)
        mismatched_worker.open()
        mismatched_worker.set_polling_global(True)

        def stop_mismatched():
            mismatched_worker.close()
            app.quit()

        # 5 s is enough for the Arduino to ignore many polls from "slave 99".
        QTimer.singleShot(5000, stop_mismatched)
        app.exec()

        if mismatched_count[0] == 0:
            rep.ok("Slave 99 yielded zero replies — node_address field is enforced")
        else:
            rep.fail(f"Slave 99 unexpectedly got {mismatched_count[0]} replies")
    else:
        rep.note("--skip-node-mismatch set: Phase 8 skipped")

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
