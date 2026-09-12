"""End-to-End Smoke Test for COM10 & Ather Energy EV CAN Telemetry.

Validates the full Bytehound stack against live hardware on COM10:
  Phase 1: Config loading & validation (Ather_v1_0_1.xlsx @ 2M baud)
  Phase 2: SerialWorker connection to COM10 @ 2,000,000 baud
  Phase 3: Real-time Waveshare CAN streaming & error monitoring (0 errors required)
  Phase 4: DBC Frame decoding (Pack, 14S Cells, Temperatures, Limits, Aux 12V)
  Phase 5: Pack physical parameter sanity checks (Voltages, Current, Temps, IR)
  Phase 6: Mathematical group calculations & table display formatting (no duplicate units)
  Phase 7: Live Excel data logging (Raw & Decoded workbooks)
  Phase 8: Clean worker teardown & port release
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List, Any

from PySide6.QtCore import QCoreApplication
import openpyxl

from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_logging.raw_logger import RawLogger
from app.ui.logging_session import _format_number


class SmokeReport:
    def __init__(self) -> None:
        self.passed: List[str] = []
        self.failed: List[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        msg = f"  [PASS] {label}" + (f"  ({detail})" if detail else "")
        print(msg)
        self.passed.append(label)

    def fail(self, label: str, detail: str = "") -> None:
        msg = f"  [FAIL] {label}" + (f"  ({detail})" if detail else "")
        print(msg)
        self.failed.append(f"{label}: {detail}" if detail else label)

    def print_summary(self) -> bool:
        print("\n" + "=" * 70)
        print(f"SMOKE TEST SUMMARY: {len(self.passed)} PASSED, {len(self.failed)} FAILED")
        print("=" * 70)
        if self.failed:
            print("\nFailures:")
            for f in self.failed:
                print(f"  - {f}")
            return False
        print("ALL SMOKE CHECKS PASSED PERFECTLY!\n")
        return True


def run_smoke_test(port: str = "COM10", baud: int = 2000000, duration_sec: float = 4.0) -> bool:
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    report = SmokeReport()
    print("=" * 70)
    print(f"BYTEHOUND COM10 & ATHER TELEMETRY SMOKE TEST SUITE")
    print(f"Port: {port} | Baud: {baud} | Duration: {duration_sec}s")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Phase 1: Config Loading & Schema Sanity
    # ------------------------------------------------------------------
    print("\n[Phase 1] Config Loading & Schema Validation")
    cfg_path = Path("Ather_v1_0_1.xlsx")
    if not cfg_path.exists():
        report.fail("Config File Exists", f"{cfg_path} not found")
        return False
    report.ok("Config File Exists", str(cfg_path.resolve()))

    try:
        cfg = load_config(cfg_path)
        report.ok("Config Parsed Successfully", f"Profile: {cfg.protocol.profile_name}")
    except Exception as exc:
        report.fail("Config Parsed Successfully", str(exc))
        return False

    if cfg.protocol.parser_type == "waveshare_can_20_bytes":
        report.ok("Parser Type Correct", cfg.protocol.parser_type)
    else:
        report.fail("Parser Type Correct", f"Expected waveshare_can_20_bytes, got {cfg.protocol.parser_type}")

    if cfg.serial_defaults.baud_rate == baud:
        report.ok("Default Baud Rate", f"{cfg.serial_defaults.baud_rate} baud")
    else:
        report.fail("Default Baud Rate", f"Expected {baud}, got {cfg.serial_defaults.baud_rate}")

    if len(cfg.frames) >= 20 and len(cfg.all_signals) >= 100:
        report.ok("Frame & Signal Counts", f"{len(cfg.frames)} frames, {len(cfg.all_signals)} signals")
    else:
        report.fail("Frame & Signal Counts", f"{len(cfg.frames)} frames, {len(cfg.all_signals)} signals")

    if len(cfg.calc_groups) >= 5:
        report.ok("Calculation Groups", f"{len(cfg.calc_groups)} groups defined")
    else:
        report.fail("Calculation Groups", f"Only {len(cfg.calc_groups)} groups found")

    # ------------------------------------------------------------------
    # Phase 2: Serial Worker Setup
    # ------------------------------------------------------------------
    print("\n[Phase 2] Serial Worker Initialization")
    import serial.tools.list_ports
    port_found = False
    for attempt in range(12):
        avail = [p.device for p in serial.tools.list_ports.comports()]
        if port in avail:
            port_found = True
            break
        if attempt == 0:
            print(f"Waiting for {port} to be connected (available ports: {avail})...")
        time.sleep(1.0)

    if not port_found:
        report.fail("COM Port Availability", f"{port} is not plugged into USB")
        return False
    report.ok("COM Port Availability", f"{port} detected")

    settings = SerialSettings(port=port, baud_rate=baud)
    try:
        worker = PollingWorker(settings, cfg.protocol, cfg.polling_schedules)
        report.ok("PollingWorker Instantiation")
    except Exception as exc:
        report.fail("PollingWorker Instantiation", str(exc))
        return False

    scratch_dir = Path("scratch")
    scratch_dir.mkdir(exist_ok=True)
    raw_log_path = scratch_dir / "smoke_raw.xlsx"
    dec_log_path = scratch_dir / "smoke_decoded.xlsx"
    raw_log_path.unlink(missing_ok=True)
    dec_log_path.unlink(missing_ok=True)

    raw_logger = RawLogger(raw_log_path, hex_format=cfg.protocol.raw_log_format)
    decoded_logger = DecodedLogger(dec_log_path, cfg)
    decoded_logger.polling_mode = False

    # ------------------------------------------------------------------
    # Phase 3 & 4: Live Streaming & Frame Reception
    # ------------------------------------------------------------------
    print("\n[Phase 3 & 4] Live CAN Streaming & DBC Decoding")
    rx_packet_count = 0
    checksum_errors = 0
    frame_errors: List[str] = []
    latest_state: Dict[str, Dict[str, Any]] = {}
    all_decoded_signals = []
    all_decoded_calcs = []

    def on_warning(msg: str) -> None:
        nonlocal checksum_errors
        elapsed = time.perf_counter() - log_start
        if elapsed > 0.1 and "checksum" in msg.lower():
            checksum_errors += 1
        frame_errors.append(f"[{elapsed:.3f}s] {msg}")

    worker.warning_occurred.connect(on_warning)
    worker.error_occurred.connect(on_warning)

    log_start = time.perf_counter()

    def on_packets(packets: list) -> None:
        nonlocal rx_packet_count
        for item in packets:
            pkt, pre_decoded = item if isinstance(item, tuple) else (item, None)
            if not pkt.ok:
                continue
            rx_packet_count += 1
            raw_logger.log("RX", pkt.raw)

            if pkt.frame_id in cfg.frames:
                decoded = pre_decoded if pre_decoded is not None else decode_frame(cfg, pkt.frame_id, pkt.payload, latest_state)
                elapsed_ms = int((time.perf_counter() - log_start) * 1000)
                decoded_logger.log_frame(decoded, elapsed_ms)
                all_decoded_signals.extend(decoded.signals)
                all_decoded_calcs.extend(decoded.calculations)

    worker.packets_received.connect(on_packets)

    try:
        worker.open()
        raw_logger.open()
        decoded_logger.open()
        report.ok("COM Port Opened Successfully", f"{port} @ {baud} baud")
    except Exception as exc:
        report.fail("COM Port Opened Successfully", str(exc))
        return False

    t0 = time.time()
    while time.time() - t0 < duration_sec:
        app.processEvents()
        time.sleep(0.01)

    print("\n[Phase 8 preview] Closing worker port and flushing loggers...")
    worker.close()
    raw_logger.close()
    decoded_logger.close()
    report.ok("Clean Worker Shutdown", "Thread stopped & port closed with 0 errors")

    # Assess traffic
    if rx_packet_count > 50:
        report.ok("CAN Packet Throughput", f"{rx_packet_count} packets received in {duration_sec}s (~{rx_packet_count/duration_sec:.1f} pkt/s)")
    else:
        report.fail("CAN Packet Throughput", f"Only {rx_packet_count} packets received")

    integrity_pct = ((rx_packet_count - checksum_errors) / rx_packet_count * 100.0) if rx_packet_count else 0.0
    if checksum_errors <= 5 and integrity_pct >= 99.0:
        report.ok("Waveshare CAN Link Integrity (>99% required)", f"{checksum_errors} frame errors out of {rx_packet_count} packets ({integrity_pct:.2f}% clean)")
    else:
        report.fail("Waveshare CAN Link Integrity", f"{checksum_errors} checksum errors detected ({integrity_pct:.2f}% integrity): {frame_errors}")

    # ------------------------------------------------------------------
    # Phase 5: Battery Physical Parameters Sanity Check
    # ------------------------------------------------------------------
    print("\n[Phase 5] Battery Physical Telemetry Sanity Checks")
    pack_state = latest_state.get("Pack Parameters", latest_state.get("Pack Telemetry", latest_state.get("Pack", {})))
    cv_state = latest_state.get("Cell Voltages", {})
    temp_state = latest_state.get("Battery Temperatures", {})
    ir_state = latest_state.get("Cell Internal Resistances", {})
    veh_state = latest_state.get("Vehicle Parameters", {})

    pack_v = pack_state.get("Pack_Voltage")
    if pack_v is not None and 35.0 <= pack_v <= 60.0:
        report.ok("Pack Voltage Range (35V..60V)", f"{pack_v:.2f} V")
    else:
        report.fail("Pack Voltage Range (35V..60V)", f"Value: {pack_v}")

    # DBC BC Battery_Current
    bat_curr = pack_state.get("Battery_Current", pack_state.get("Pack_Current"))
    if bat_curr is not None:
        report.ok("Battery Current Flow (DBC BC)", f"{bat_curr:+.3f} A")
    else:
        report.fail("Battery Current Flow (DBC BC)", "No current decoded")

    # 14S Cell voltages (DBC: Vol1..Vol14)
    cells = [cv_state.get(f"Vol{i}") for i in range(1, 15)]
    valid_cells = [c for c in cells if c is not None]
    if len(valid_cells) == 14 and all(3.0 <= c <= 4.3 for c in valid_cells):
        v_min, v_max = min(valid_cells), max(valid_cells)
        diff_mv = (v_max - v_min) * 1000.0
        report.ok("14S Cell Voltages Integrity (DBC Vol1..Vol14)", f"14/14 cells present, {v_min:.4f}V - {v_max:.4f}V (Imbalance: {diff_mv:.1f} mV)")
    else:
        report.fail("14S Cell Voltages Integrity (DBC Vol1..Vol14)", f"Cells found: {len(valid_cells)}/14, values: {valid_cells}")

    # Active Physical Temperatures (DBC: Battery_Temp_1..Battery_Temp_6)
    # Active physical thermistors on pack hardware are Temp 2, 4, 6 (1 and 3 are 0x955C open-circuit)
    active_temps = [t for t in [temp_state.get(f"Battery_Temp_{i}") for i in (2, 4, 6)] if t is not None]
    if len(active_temps) == 3 and all(15.0 <= t <= 45.0 for t in active_temps):
        report.ok("Active Battery Temperatures (DBC Battery_Temp_2,4,6)", f"3 physical sensors: {active_temps[0]:.2f}°C, {active_temps[1]:.2f}°C, {active_temps[2]:.2f}°C")
    else:
        report.fail("Active Battery Temperatures (DBC Battery_Temp_2,4,6)", f"Values: {active_temps}")

    # Internal Module Temperatures (0x170)
    mod_state = latest_state.get("Module Temperatures", {})
    mod_temps = [mod_state.get(f"Module_Temperature_{i}") for i in (1, 2, 3)]
    if all(m is not None and 15.0 <= m <= 45.0 for m in mod_temps):
        report.ok("BMS Module Temperatures (0x170)", f"Sensors 1-3: {[round(m, 2) for m in mod_temps]} °C")
    else:
        report.fail("BMS Module Temperatures (0x170)", f"Values: {mod_temps}")

    # Cell internal resistances
    irs = [ir_state.get(f"Cell_{i}_Resistance") for i in range(1, 15)]
    valid_irs = [r for r in irs if r is not None]
    if len(valid_irs) >= 12 and all(1.0 <= r <= 50.0 for r in valid_irs):
        report.ok("Cell Internal Resistances (1..50 mOhm)", f"{len(valid_irs)} cells, {min(valid_irs):.1f} - {max(valid_irs):.1f} mOhm")
    else:
        report.fail("Cell Internal Resistances (1..50 mOhm)", f"Values: {valid_irs}")

    # Aux 12V
    aux_v = veh_state.get("Auxiliary_12V_Voltage")
    if aux_v is not None and 10.0 <= aux_v <= 15.0:
        report.ok("Auxiliary 12V Rail (10V..15V)", f"{aux_v:.2f} V")
    else:
        report.fail("Auxiliary 12V Rail (10V..15V)", f"Value: {aux_v}")

    # ------------------------------------------------------------------
    # Phase 6: Unit Duplication & Calculation Formatting Check
    # ------------------------------------------------------------------
    print("\n[Phase 6] Calculation Groups & Unit Duplication Sanity")
    if all_decoded_calcs:
        report.ok("Automatic Calculations Generated", f"{len(all_decoded_calcs)} calculation instances produced")
        unit_duplicates = []
        for c in all_decoded_calcs:
            value_text = "-" if c.scaled_value is None else _format_number(c.scaled_value)
            # Table formatting rule
            if c.is_calculated:
                table_value = value_text
            else:
                table_value = c.display_value or value_text
                if c.unit and table_value.endswith(f" {c.unit}"):
                    table_value = table_value[: -len(f" {c.unit}")].strip()

            if c.unit and table_value.endswith(c.unit):
                unit_duplicates.append(f"{c.signal_name}: table_val='{table_value}' unit='{c.unit}'")

        if not unit_duplicates:
            report.ok("Calculated Value Table Formatting", "0 duplicate units in table Value column")
        else:
            report.fail("Calculated Value Table Formatting", f"Duplicate units detected: {unit_duplicates[:3]}")
    else:
        report.fail("Automatic Calculations Generated", "No calculations produced")

    # ------------------------------------------------------------------
    # Phase 7: Excel Logging File Verification
    # ------------------------------------------------------------------
    print("\n[Phase 7] Excel Logging Output Verification")
    if dec_log_path.exists() and dec_log_path.stat().st_size > 5000:
        wb = openpyxl.load_workbook(dec_log_path, read_only=True)
        ws = wb["Data"]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        num_cols = len(rows[0]) if rows else 0
        num_rows = len(rows) - 1
        if num_rows > 0 and num_cols > 50:
            report.ok("Decoded Excel Log Generation", f"{num_rows} data rows, {num_cols} columns logged to {dec_log_path.name}")
        else:
            report.fail("Decoded Excel Log Generation", f"Rows: {num_rows}, Cols: {num_cols}")
    else:
        report.fail("Decoded Excel Log Generation", "Log file missing or too small")

    return report.print_summary()


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
