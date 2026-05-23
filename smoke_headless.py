"""End-to-end headless test against the Arduino BMS simulator.

Exercises every Bytehound feature that has a wire-level or device-level
component, against the bundled `app/resources/config_template` config and
the matching `Arduino_BMS_Simulator.ino` sketch.

  Phase  0  Static config sanity
  Phase  1  TX builder byte-exactness (offline)
  Phase  2  Live serial: polling + bitfields + enums + TX
  Phase  3  Frames received (0x1000 / 0x2000 / 0x3000)
  Phase  4  Bitfield decoding (Fault Flags / Status_Bits)
  Phase  5  Enum decoding (BMS State / Mode)
  Phase  6  TX commands on the wire (Reset Faults + Set Voltage Limit)
  Phase  7  Voltage Limit round-trip (param-editor short form)
  Phase  8  Cell Voltage decoding (8 expanded signals from `count=8`)
  Phase  9  CalcGroups (Cell Voltages min/max/avg/diff)
  Phase 10  Polling cadence (interval honoured by PollingWorker)
  Phase 11  `direction` gating (UI software check, no device)
  Phase 12  `raw_log_format` hex vs compact (no device)
  Phase 13  TxCommand description tooltip data (no device)
  Phase 14  SerialDefaults pre-pop priority (no device)

Run:  python smoke_headless.py [--port COM7] [--seconds 12]

Exit status is the number of failed checks (0 = all green). Anything
non-zero means at least one feature did not behave the way the docs claim.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QCoreApplication, QSettings, QTimer

from app.commands.tx_command_builder import build_tx_command
from app.decoder.calculations import calculate_group_value
from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.protocol.crc import compute as crc_compute
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
    parser.add_argument("--seconds", type=int, default=12,
                        help="how long to listen on the serial port (>=10 recommended)")
    parser.add_argument("--target-voltage", type=float, default=58.5,
                        help="voltage limit (V) to write via Set Voltage Limit")
    parser.add_argument("--boot-delay", type=float, default=3.0,
                        help="seconds to wait after open before enabling polling/TX. "
                             "Opening the COM port toggles DTR which resets the Arduino; "
                             "any commands sent during the ~1.5s bootloader window are lost.")
    parser.add_argument("--skip-device", action="store_true",
                        help="skip phases 2-10 (live serial). Only the software-only "
                             "phases (0, 1, 11-14) will run. Use this on a build server.")
    args = parser.parse_args()

    rep = Report()
    config = load_config(Path("app/resources/config_template"))

    # ------------------------------------------------------------------
    # Phase 0  Static config sanity — every signal/bitfield/enum/command
    # the rest of the test relies on must be present in the loaded config.
    # ------------------------------------------------------------------
    print("\n=== Phase 0  Config sanity ===")
    if 0x1000 in config.signals_by_frame:
        rep.ok("Frame 0x1000 (BMS Status) present in config")
    else:
        rep.fail("Frame 0x1000 missing from variables.csv")

    if 0x2000 in config.signals_by_frame:
        sigs_2000 = [s.signal_name for s in config.signals_by_frame[0x2000]]
        cells = [n for n in sigs_2000 if n.startswith("Cell Voltage")]
        if len(cells) == 8:
            rep.ok(f"Frame 0x2000 expands count=8 to {cells[:3]}…{cells[-1]} ({len(cells)} signals)")
        else:
            rep.fail(f"Frame 0x2000: expected 8 Cell Voltage expansions, got {len(cells)}")
        if "Voltage Limit" in sigs_2000:
            rep.ok("Voltage Limit signal present on frame 0x2000")
        else:
            rep.fail("Voltage Limit signal missing on frame 0x2000")
    else:
        rep.fail("Frame 0x2000 missing from variables.csv")

    if 0x3000 in config.signals_by_frame:
        rep.ok("Frame 0x3000 (Status Flags) present in config")
    else:
        rep.fail("Frame 0x3000 missing from variables.csv")

    if (0x3000, "Fault Flags") in config.bitfields:
        bits = config.bitfields[(0x3000, "Fault Flags")]
        names = [b.bit_name for b in bits]
        if "Charging" in names and "Ready" in names and len(names) == 8:
            rep.ok(f"Fault Flags bitfield has 8 named bits: {names}")
        else:
            rep.fail("Fault Flags bitfield missing expected labels", str(names))
    else:
        rep.fail("Fault Flags bitfield not registered in config")

    if (0x3000, "BMS State") in config.enums:
        labels = config.enums[(0x3000, "BMS State")]
        if labels.get(0) == "Idle" and labels.get(3) == "Fault":
            rep.ok(f"BMS State enum has expected labels: {labels}")
        else:
            rep.fail("BMS State enum missing expected labels", str(labels))
    else:
        rep.fail("BMS State enum not registered in config")

    if "Set Voltage Limit" in config.tx_commands:
        cmd = config.tx_commands["Set Voltage Limit"]
        if cmd.fields and cmd.fields[0].field_name == "Voltage Limit (V)":
            rep.ok(f"Set Voltage Limit has field '{cmd.fields[0].field_name}'")
        else:
            rep.fail("Set Voltage Limit has no fields - parameter editor would be empty")
    else:
        rep.fail("Set Voltage Limit command not registered in config")

    if "Reset Faults" in config.tx_commands:
        rep.ok("Reset Faults TX command registered")
    else:
        rep.fail("Reset Faults TX command missing")

    # CalcGroups: Cell Voltages with min|max|diff|avg.
    cg_stats = sorted({g.stat for g in config.calc_groups if g.group == "Cell Voltages"})
    expected_stats = ["avg", "diff", "max", "min"]
    if cg_stats == expected_stats:
        rep.ok(f"CalcGroups for 'Cell Voltages' has all 4 stats: {cg_stats}")
    else:
        rep.fail(f"CalcGroups for 'Cell Voltages' got {cg_stats}, expected {expected_stats}")

    # ------------------------------------------------------------------
    # Phase 1  Parameter editor / TX builder byte-exactness — proves the
    # builder produces the exact byte sequence the Arduino will accept.
    # ------------------------------------------------------------------
    print("\n=== Phase 1  TX builder (offline byte-exact) ===")
    try:
        built = build_tx_command(
            config, "Set Voltage Limit", {"Voltage Limit (V)": args.target_voltage}
        )
        # Expected packet for 58.5 V on frame 0x2000 with scale 0.01:
        #   header AA 55, frame 0x2000 LE (00 20), len 02,
        #   payload = round(58.5 / 0.01) = 5850 = 0x16DA → DA 16 (LE),
        #   CRC16 modbus over [AA 55 00 20 02 DA 16], LE, then footer EE.
        raw = int(round(args.target_voltage / 0.01))
        coverage = bytes([0xAA, 0x55, 0x00, 0x20, 0x02]) + raw.to_bytes(2, "little")
        crc = crc_compute("crc16_modbus", coverage)
        expected = coverage + crc.to_bytes(2, "little") + b"\xEE"
        if built == expected:
            rep.ok(f"Set Voltage Limit({args.target_voltage} V) bytes = {built.hex().upper()}")
        else:
            rep.fail("Set Voltage Limit byte mismatch",
                     f"got {built.hex().upper()} expected {expected.hex().upper()}")
    except Exception as e:
        rep.fail("Set Voltage Limit build raised", str(e))

    # Range enforcement: 99.0 V is above the field's max=60.
    try:
        build_tx_command(config, "Set Voltage Limit", {"Voltage Limit (V)": 99.0})
        rep.fail("Set Voltage Limit(99 V) should have been rejected by max bound")
    except Exception:
        rep.ok("Set Voltage Limit enforces max bound (99.0 V rejected)")

    # Reset Faults builds as a static-payload command (FF FF).
    try:
        reset_bytes = build_tx_command(config, "Reset Faults", {})
        if reset_bytes.startswith(b"\xAA\x55") and b"\xFF\xFF" in reset_bytes:
            rep.ok(f"Reset Faults bytes = {reset_bytes.hex().upper()}")
        else:
            rep.fail("Reset Faults bytes look wrong", reset_bytes.hex().upper())
    except Exception as e:
        rep.fail("Reset Faults build raised", str(e))

    # ------------------------------------------------------------------
    # Software-only phases for new features that have no device-side
    # dependency. Running them BEFORE the live phase means we still get
    # signal on what works even if the Arduino isn't plugged in.
    # ------------------------------------------------------------------
    _phase_11_direction_gating(config, rep)
    _phase_12_raw_log_format(rep)
    _phase_13_tx_command_descriptions(config, rep)
    _phase_14_serial_defaults_priority(config, rep)

    if args.skip_device:
        rep.note("--skip-device set: phases 2-10 skipped")
        return _summarize(rep)

    # ------------------------------------------------------------------
    # Phase 2  Live serial — polling + bitfields + enums + TX
    # ------------------------------------------------------------------
    print(f"\n=== Phase 2  Live serial on {args.port} for {args.seconds} s ===")
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    settings = SerialSettings(port=args.port, baud_rate=115200)
    worker = PollingWorker(settings, config.protocol, config.polling_schedules)

    Path("scratch").mkdir(exist_ok=True)
    raw_path = Path("scratch/test_raw.csv")
    if raw_path.exists():
        raw_path.unlink()
    dec_path = Path("scratch/test_decoded.xlsx")
    raw_logger = RawLogger(raw_path, hex_format=config.protocol.raw_log_format)
    decoded_logger = DecodedLogger(dec_path, config)
    log_start = time.perf_counter()

    # Per-feature observation buckets
    seen_frame_ids: set[int] = set()
    pkt_total = 0
    crc_errors = 0
    voltage_limit_timeline: List[float] = []
    cell_voltage_obs: List[Dict[str, float]] = []   # one dict per 0x2000 frame
    bitfield_observations: List[Dict[str, bool]] = []
    enum_observations: List[str] = []
    tx_seen: List[bytes] = []
    # (frame_id → list of arrival times) for cadence checks.
    arrival_times: Dict[int, List[float]] = {0x1000: [], 0x2000: [], 0x3000: []}

    def on_packets(packets):
        nonlocal pkt_total, crc_errors
        for item in packets:
            # PollingWorker emits (ParsedPacket, decoded-or-None) tuples.
            pkt, pre_decoded = item if isinstance(item, tuple) else (item, None)
            pkt_total += 1
            raw_logger.log("RX", pkt.raw)
            if not pkt.ok:
                crc_errors += 1
                continue
            seen_frame_ids.add(pkt.frame_id)
            if pkt.frame_id in arrival_times:
                arrival_times[pkt.frame_id].append(time.perf_counter())
            decoded = pre_decoded if pre_decoded is not None else decode_frame(config, pkt.frame_id, pkt.payload)
            elapsed_ms = int((time.perf_counter() - log_start) * 1000)
            decoded_logger.log_frame(decoded, elapsed_ms)

            cells_this_frame: Dict[str, float] = {}
            for sig in decoded.signals:
                if sig.frame_id == 0x2000 and sig.signal_name == "Voltage Limit" and sig.scaled_value is not None:
                    voltage_limit_timeline.append(sig.scaled_value)
                if sig.frame_id == 0x2000 and sig.signal_name.startswith("Cell Voltage") and sig.scaled_value is not None:
                    cells_this_frame[sig.signal_name] = sig.scaled_value
                if sig.frame_id == 0x3000 and sig.signal_name == "Fault Flags" and sig.bit_values:
                    bitfield_observations.append(dict(sig.bit_values))
                if sig.frame_id == 0x3000 and sig.signal_name == "BMS State" and sig.enum_label:
                    enum_observations.append(sig.enum_label)
            if cells_this_frame:
                cell_voltage_obs.append(cells_this_frame)

    def on_tx(data: bytes):
        tx_seen.append(bytes(data))
        raw_logger.log("TX", data)

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

    def send_reset():
        try:
            worker.enqueue_priority_tx(build_tx_command(config, "Reset Faults", {}))
            rep.note(f"Reset Faults queued at t={(boot_ms + 1000) / 1000:.1f}s")
        except Exception as e:
            rep.note(f"Reset Faults build failed: {e}")

    def send_set_limit():
        try:
            worker.enqueue_priority_tx(build_tx_command(
                config, "Set Voltage Limit", {"Voltage Limit (V)": args.target_voltage}
            ))
            rep.note(f"Set Voltage Limit queued at t={(boot_ms + 3000) / 1000:.1f}s")
        except Exception as e:
            rep.note(f"Set Voltage Limit build failed: {e}")

    def disable_streaming_and_arm_cadence():
        # 0x1005 [01] = autonomous streaming off. From this point on the only
        # 0x1000/0x2000/0x3000 frames on the wire are responses to polls.
        # We also CLEAR arrival_times here so Phase 10's cadence measurement
        # only sees the polling-only window — the early ~2 seconds of mixed
        # autonomous+polling traffic would otherwise pull the average gap
        # low and flake the test.
        from app.protocol.packet_builder import build_packet
        try:
            worker.enqueue_priority_tx(build_packet(config.protocol, 0x1005, b"\x01"))
            for fid in arrival_times:
                arrival_times[fid].clear()
            rep.note(f"streaming OFF + cadence buckets cleared at t={(boot_ms + 2000) / 1000:.1f}s")
        except Exception as e:
            rep.note(f"0x1005 build failed: {e}")

    QTimer.singleShot(boot_ms, enable_polling)
    QTimer.singleShot(boot_ms + 500, send_reset)
    # Reset (above) also re-enables streaming inside the firmware, so we
    # turn streaming off AFTER reset rather than before.
    QTimer.singleShot(boot_ms + 2000, disable_streaming_and_arm_cadence)
    QTimer.singleShot(boot_ms + 3500, send_set_limit)

    def stop():
        worker.close()
        raw_logger.close()
        decoded_logger.close()
        app.quit()

    QTimer.singleShot(args.seconds * 1000, stop)
    app.exec()

    # ------------------------------------------------------------------
    # Phase 3  Frames received
    # ------------------------------------------------------------------
    print(f"\n=== Phase 3  Live results (rx packets={pkt_total}, crc_errors={crc_errors}) ===")
    for fid, name in [(0x1000, "BMS Status"), (0x2000, "BMS Settings"), (0x3000, "Status Flags")]:
        if fid in seen_frame_ids:
            rep.ok(f"Frame 0x{fid:04X} ({name}) received")
        else:
            rep.fail(f"Frame 0x{fid:04X} ({name}) NOT received - is the simulator running?")
    if crc_errors == 0:
        rep.ok("Zero CRC errors over the run")
    else:
        rep.fail(f"{crc_errors} CRC errors observed")

    # ------------------------------------------------------------------
    # Phase 4  Bitfield decoding
    # ------------------------------------------------------------------
    print("\n=== Phase 4  Bitfield decoding ===")
    if bitfield_observations:
        sample = bitfield_observations[-1]
        expected_keys = {"Charging", "Discharging", "Balancing", "Fault",
                         "Overvoltage", "Undervoltage", "Overtemp", "Ready"}
        if expected_keys.issubset(sample.keys()):
            rep.ok(f"Fault Flags decoded with all 8 named bits, latest={sample}")
        else:
            rep.fail("Fault Flags bit_values missing keys",
                     f"got {set(sample.keys())}")
    else:
        rep.fail("No Fault Flags decoded - did 0x3000 arrive?")

    # ------------------------------------------------------------------
    # Phase 5  Enum decoding
    # ------------------------------------------------------------------
    print("\n=== Phase 5  Enum decoding ===")
    if enum_observations:
        unique = sorted(set(enum_observations))
        rep.ok(f"BMS State enum labels resolved: {unique}")
        if len(unique) >= 2:
            rep.ok(f"BMS State actually cycled (saw {len(unique)} distinct labels)")
        else:
            rep.fail("BMS State did not cycle — only one label observed")
    else:
        rep.fail("No BMS State labels decoded - did 0x3000 arrive?")

    # ------------------------------------------------------------------
    # Phase 6  TX commands actually went out
    # ------------------------------------------------------------------
    print("\n=== Phase 6  TX commands ===")
    reset_packet = build_tx_command(config, "Reset Faults", {})
    setlim_packet = build_tx_command(
        config, "Set Voltage Limit", {"Voltage Limit (V)": args.target_voltage}
    )
    if reset_packet in tx_seen:
        rep.ok(f"Reset Faults packet seen on wire: {reset_packet.hex().upper()}")
    else:
        rep.fail("Reset Faults packet not in tx_recorded stream")
    if setlim_packet in tx_seen:
        rep.ok(f"Set Voltage Limit packet seen on wire: {setlim_packet.hex().upper()}")
    else:
        rep.fail("Set Voltage Limit packet not in tx_recorded stream")

    # ------------------------------------------------------------------
    # Phase 7  Voltage Limit round-trip
    # ------------------------------------------------------------------
    print("\n=== Phase 7  Set Voltage Limit round-trip ===")
    if voltage_limit_timeline:
        before = voltage_limit_timeline[: max(1, len(voltage_limit_timeline) // 3)]
        after = voltage_limit_timeline[-3:]
        rep.note(f"Voltage Limit timeline (first/last): {before[:3]} ... {after}")
        if any(abs(v - args.target_voltage) < 0.05 for v in voltage_limit_timeline):
            rep.ok(f"Voltage Limit reflected target {args.target_voltage} V at least once")
        else:
            rep.fail(
                f"Voltage Limit never reached {args.target_voltage} V "
                f"(seen {sorted(set(voltage_limit_timeline))[:6]}...)"
            )
    else:
        rep.fail("No 0x2000 frames captured - cannot check round-trip")

    # ------------------------------------------------------------------
    # Phase 8  Cell Voltage decoding (8 expanded signals)
    # ------------------------------------------------------------------
    print("\n=== Phase 8  Cell Voltage decoding (count=8 expansion) ===")
    if cell_voltage_obs:
        latest = cell_voltage_obs[-1]
        expected_names = {f"Cell Voltage {i}" for i in range(1, 9)}
        if expected_names.issubset(latest.keys()):
            rep.ok(f"All 8 Cell Voltage signals decoded, latest = "
                   + ", ".join(f"{k}={v:.3f}V" for k, v in sorted(latest.items())))
            # Sanity: cells should land near 3.7 V given the Arduino seed values.
            in_range = all(3.0 <= v <= 4.5 for v in latest.values())
            if in_range:
                rep.ok("Cell Voltage values are within plausible 3.0–4.5 V range")
            else:
                rep.fail("Cell Voltage values out of plausible range",
                         str(sorted(latest.values())))
        else:
            missing = expected_names - latest.keys()
            rep.fail(f"Cell Voltage missing {missing}", f"got {sorted(latest.keys())}")
    else:
        rep.fail("No Cell Voltage signals decoded - did the Arduino emit 18-byte 0x2000?")

    # ------------------------------------------------------------------
    # Phase 9  CalcGroups (min/max/avg/diff over Cell Voltages)
    #
    # The bundled config has one CalcGroupSpec per stat (min, max, diff,
    # avg) all bound to group="Cell Voltages" and frame_id=0x2000. We
    # run each spec against the 8 latest cell voltage values via
    # calculate_group_value() and verify the math matches what we'd get
    # from a hand-rolled min/max/(max-min)/mean.
    # ------------------------------------------------------------------
    print("\n=== Phase 9  CalcGroups (Cell Voltages min/max/avg/diff) ===")
    if cell_voltage_obs:
        latest_cells = cell_voltage_obs[-1]
        vals = list(latest_cells.values())
        expected = {
            "min":  min(vals),
            "max":  max(vals),
            "diff": max(vals) - min(vals),
            "avg":  sum(vals) / len(vals),
        }
        calcs = [g for g in config.calc_groups if g.group == "Cell Voltages"]
        if not calcs:
            rep.fail("No CalcGroupSpec rows for 'Cell Voltages' in loaded config")
        else:
            for spec in calcs:
                try:
                    got = calculate_group_value(spec, vals)
                except Exception as e:
                    rep.fail(f"calculate_group_value(stat={spec.stat!r}) raised", str(e))
                    continue
                want = expected.get(spec.stat)
                if want is None:
                    rep.fail(f"Unexpected stat in config: {spec.stat!r}")
                elif abs(got - want) < 1e-9:
                    rep.ok(f"Cell Voltages {spec.stat} = {got:.3f}V (matches hand-computed)")
                else:
                    rep.fail(f"Cell Voltages {spec.stat} mismatch: got {got}, expected {want}")
    else:
        rep.fail("Skipping CalcGroups check — no cell voltage frames captured")

    # ------------------------------------------------------------------
    # Phase 10  Polling cadence — frames should arrive at their declared
    # interval (polling_schedule.csv: 0x1000@100, 0x2000@500, 0x3000@200).
    # We measure the average gap between consecutive arrivals and require
    # it to be within ±50% of the configured interval — generous on USB
    # serial but tight enough to catch a 10x mis-schedule.
    # ------------------------------------------------------------------
    print("\n=== Phase 10  Polling cadence ===")
    expected_intervals_ms = {0x1000: 100, 0x2000: 500, 0x3000: 200}
    for fid, want in expected_intervals_ms.items():
        ts = arrival_times.get(fid, [])
        if len(ts) < 3:
            rep.fail(f"0x{fid:04X}: only {len(ts)} arrivals — cannot measure cadence")
            continue
        gaps_ms = [(ts[i] - ts[i - 1]) * 1000.0 for i in range(1, len(ts))]
        avg_gap = sum(gaps_ms) / len(gaps_ms)
        lo, hi = want * 0.5, want * 1.5
        if lo <= avg_gap <= hi:
            rep.ok(f"0x{fid:04X} arrival cadence avg={avg_gap:.1f} ms (want {want} ms ±50%)")
        else:
            rep.fail(f"0x{fid:04X} cadence drift: avg={avg_gap:.1f} ms, want {want} ms ±50%")

    return _summarize(rep)


# ------------------------------------------------------------------
# Software-only phases (no Arduino required)
# ------------------------------------------------------------------
def _phase_11_direction_gating(config, rep: Report) -> None:
    print("\n=== Phase 11  `direction` gating (software) ===")
    # The bundled frames.csv now declares 0x3000 as 'rx' (telemetry only).
    # Per the gating rules, TX commands targeting 0x3000 must be hidden
    # from the TX panel, and writable signals on 0x3000 must be hidden
    # from the Parameter Editor's rw_signals list.
    if 0x3000 in config.frames and config.frames[0x3000].direction == "rx":
        rep.ok("Frame 0x3000 is declared direction=rx in bundled frames.csv")
    else:
        rep.fail("Frame 0x3000 direction is not 'rx' — direction column not applied?")

    # is_tx_capable / is_rx_capable property check.
    rxtx_frame = config.frames.get(0x2000)
    if rxtx_frame and rxtx_frame.is_tx_capable and rxtx_frame.is_rx_capable:
        rep.ok("Frame 0x2000 is_tx_capable AND is_rx_capable (direction='rxtx')")
    else:
        rep.fail("Frame 0x2000 direction helpers wrong",
                 f"direction={rxtx_frame.direction if rxtx_frame else 'MISSING'}")

    rx_frame = config.frames.get(0x3000)
    if rx_frame and not rx_frame.is_tx_capable and rx_frame.is_rx_capable:
        rep.ok("Frame 0x3000 is_rx_capable but NOT is_tx_capable (direction='rx')")
    else:
        rep.fail("Frame 0x3000 direction helpers wrong",
                 f"direction={rx_frame.direction if rx_frame else 'MISSING'}")


def _phase_12_raw_log_format(rep: Report) -> None:
    print("\n=== Phase 12  raw_log_format (software) ===")
    # Sanity-check both hex_format values produce the expected on-disk text.
    Path("scratch").mkdir(exist_ok=True)
    payload = bytes.fromhex("AA550010040FA00BB8BE70")
    for mode, expected_hex in [
        ("hex",     "AA 55 00 10 04 0F A0 0B B8 BE 70"),
        ("compact", "AA550010040FA00BB8BE70"),
    ]:
        path = Path(f"scratch/_fmt_{mode}.csv")
        if path.exists():
            path.unlink()
        with RawLogger(path, hex_format=mode) as lg:
            lg.log("RX", payload)
        lines = path.read_text(encoding="utf-8").splitlines()
        # Header line is COLUMNS; data line is line 1.
        if len(lines) >= 2 and expected_hex in lines[1]:
            rep.ok(f"raw_log_format={mode!r} wrote {expected_hex!r}")
        else:
            rep.fail(f"raw_log_format={mode!r} content wrong", str(lines))

    # Invalid value should be rejected with a clear error.
    try:
        RawLogger(Path("scratch/_fmt_bad.csv"), hex_format="binary")
        rep.fail("RawLogger should have rejected hex_format='binary'")
    except ValueError:
        rep.ok("RawLogger rejects invalid hex_format values")


def _phase_13_tx_command_descriptions(config, rep: Report) -> None:
    print("\n=== Phase 13  TxCommand descriptions (tooltip source) ===")
    # Every bundled TX command should have a non-empty description so the
    # tooltip surface in the TX panel is meaningful out of the box.
    missing = [n for n, c in config.tx_commands.items() if not c.description.strip()]
    if not missing:
        rep.ok("All TX commands have a non-empty description for the tooltip")
        for n, c in sorted(config.tx_commands.items()):
            print(f"        {n}: {c.description!r}")
    else:
        rep.fail(f"TX commands missing tooltip descriptions: {missing}")


def _phase_14_serial_defaults_priority(config, rep: Report) -> None:
    print("\n=== Phase 14  SerialDefaults pre-pop priority (software) ===")
    # ConnectionDialog must use config_defaults when QSettings has no stored
    # value. We can't open a Qt dialog headlessly here without
    # QApplication overhead, but we have unit tests
    # (tests/test_connection_dialog.py); this phase just confirms the loaded
    # config exposes the expected serial_defaults.
    sd = config.serial_defaults
    if sd.baud_rate > 0 and sd.parity in ("N", "E", "O"):
        rep.ok(
            f"SerialDefaults loaded: baud={sd.baud_rate}, data={sd.data_bits}, "
            f"stop={sd.stop_bits}, parity={sd.parity}, timeout={sd.timeout_ms} ms"
        )
    else:
        rep.fail(f"SerialDefaults sanity check failed: {sd}")
    # And: the QSettings → config_defaults priority is locked by 3 unit tests
    # in tests/test_connection_dialog.py — surface that this phase is a smoke
    # check, not the source of truth.
    rep.note("Field priority (QSettings > SerialDefaults > class default) is "
             "locked by tests/test_connection_dialog.py")


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
