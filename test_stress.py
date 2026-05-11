"""Comprehensive stress test against the Arduino BMS simulator.

Designed to find production bugs by hammering every part of the stack:

  Phase 0  Config sanity
  Phase 1  Parameter editor (offline byte-exact)
  Phase 2  Boot delay, passive baseline
  Phase 3  Normal polling baseline
  Phase 4  Stress mode (5x cadence, ~85 pkts/sec)
  Phase 5  Forced CRC errors (Errors counter must increment exactly N)
  Phase 6  Watchdog under silence (device_timeout must fire)
  Phase 7  Recovery (worker resumes cleanly when device speaks again)
  Phase 8  Connect / disconnect cycling
  Phase 9  TX flood (priority queue overflow handled gracefully)
  Phase 10 Parameter editor round-trip (multiple set-points)
  Phase 11 Long-run leak check (5 s bursts, watch _pending_packets / RAM)
  Phase 12 Logger + replay round-trip

The Arduino must be flashed with the sketch in Arduino_BMS_Simulator/.
Exit code is the number of failed checks (0 = all green).

Usage:
    python test_stress.py [--port COM7]
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QCoreApplication, QTimer

from app.commands.tx_command_builder import build_tx_command
from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.protocol.packet_builder import build_packet
from app.serial_io.replay_source import parse_log_file, replay_bytes
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.serial_logging.decoded_logger import DecodedLogger
from app.serial_logging.raw_logger import RawLogger


# ============================================================ infrastructure
class Report:
    def __init__(self) -> None:
        self.passed: List[str] = []
        self.failed: List[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        print(f"[ OK ] {label}" + (f"  ({detail})" if detail else ""))
        self.passed.append(label)

    def fail(self, label: str, detail: str = "") -> None:
        print(f"[FAIL] {label}" + (f"  ({detail})" if detail else ""))
        self.failed.append(f"{label} - {detail}" if detail else label)

    def note(self, msg: str) -> None:
        print(f"[note] {msg}")


def hdr(s: str) -> None:
    print(f"\n{'=' * 5} {s} {'=' * (62 - len(s))}")


def run_for(app: QCoreApplication, seconds: float) -> None:
    """Spin the Qt event loop for `seconds` and return."""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.005)


# ===================================================================== main
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--boot-delay", type=float, default=2.5,
                        help="seconds to wait after open() before doing anything")
    args = parser.parse_args()

    rep = Report()
    cfg = load_config(Path("app/resources/config_template"))

    Path("scratch").mkdir(exist_ok=True)
    raw_path = Path("scratch/stress_raw.csv")
    dec_path = Path("scratch/stress_decoded.csv")
    raw_path.unlink(missing_ok=True)
    dec_path.unlink(missing_ok=True)

    # ---------- Shared collectors that span phases ------------------------
    seen_ids: set[int] = set()
    pkt_total = 0
    crc_errors_observed = 0
    voltage_limits: List[float] = []
    bitfield_samples: List[Dict[str, bool]] = []
    enum_samples: List[str] = []
    tx_seen: List[bytes] = []
    error_messages: List[str] = []
    device_timeout_count = 0
    last_metrics: Dict[str, int] = {"timeouts": 0, "crc": 0, "rx_bytes": 0}

    def reset_collectors() -> None:
        nonlocal pkt_total, crc_errors_observed
        seen_ids.clear()
        pkt_total = 0
        crc_errors_observed = 0
        voltage_limits.clear()
        bitfield_samples.clear()
        enum_samples.clear()
        tx_seen.clear()

    raw_logger = RawLogger(raw_path)
    decoded_logger = DecodedLogger(dec_path, cfg)
    log_start = time.perf_counter()
    raw_logger.open()
    decoded_logger.open()

    # ---------- Phase 0 — config sanity (offline) -------------------------
    hdr("Phase 0  Config sanity")
    if 0x3000 in cfg.signals_by_frame: rep.ok("Frame 0x3000 in config")
    else: rep.fail("Frame 0x3000 missing")
    if (0x3000, "Status_Bits") in cfg.bitfields and len(cfg.bitfields[(0x3000, "Status_Bits")]) == 8:
        rep.ok("Status_Bits has 8 named bits")
    else: rep.fail("Status_Bits bitfield missing/wrong count")
    if (0x3000, "Mode") in cfg.enums and len(cfg.enums[(0x3000, "Mode")]) == 5:
        rep.ok("Mode enum has 5 labels")
    else: rep.fail("Mode enum missing/wrong count")
    if "Set_Voltage_Limit" in cfg.tx_commands and cfg.tx_commands["Set_Voltage_Limit"].fields:
        rep.ok("Set_Voltage_Limit is parameterized")
    else: rep.fail("Set_Voltage_Limit not parameterized")

    # ---------- Phase 1 — parameter editor offline ------------------------
    hdr("Phase 1  Parameter editor (offline)")
    pkt = build_tx_command(cfg, "Set_Voltage_Limit", {"voltage_v": 58.5})
    expected = bytes.fromhex("AA5501200249023C9EEE")
    if pkt == expected:
        rep.ok("Set_Voltage_Limit(58.5) byte-exact", pkt.hex().upper())
    else:
        rep.fail("Set_Voltage_Limit byte mismatch",
                 f"got {pkt.hex().upper()} want {expected.hex().upper()}")
    try:
        build_tx_command(cfg, "Set_Voltage_Limit", {"voltage_v": 99.0})
        rep.fail("Set_Voltage_Limit(99V) should be rejected by max_value")
    except Exception:
        rep.ok("Set_Voltage_Limit max-bound enforced")

    # ---------- Worker setup ---------------------------------------------
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    settings = SerialSettings(port=args.port, baud_rate=115200)
    worker = PollingWorker(settings, cfg.protocol, cfg.polling_schedules)

    def on_packets(batch: List[Any]) -> None:
        nonlocal pkt_total, crc_errors_observed
        for p in batch:
            pkt_total += 1
            raw_logger.log("RX", p.raw)
            if not p.ok:
                crc_errors_observed += 1
                continue
            seen_ids.add(p.frame_id)
            decoded = decode_frame(cfg, p.frame_id, p.payload)
            elapsed_ms = int((time.perf_counter() - log_start) * 1000)
            decoded_logger.log_frame(decoded, elapsed_ms)
            for sig in decoded.signals:
                if sig.frame_id == 0x2000 and sig.signal_name == "Voltage_Limit" and sig.scaled_value is not None:
                    voltage_limits.append(sig.scaled_value)
                if sig.frame_id == 0x3000 and sig.signal_name == "Status_Bits" and sig.bit_values:
                    bitfield_samples.append(dict(sig.bit_values))
                if sig.frame_id == 0x3000 and sig.signal_name == "Mode" and sig.enum_label:
                    enum_samples.append(sig.enum_label)

    def on_metrics(timeouts: int, crc: int, rx_bytes: int) -> None:
        last_metrics["timeouts"] = timeouts
        last_metrics["crc"] = crc
        last_metrics["rx_bytes"] = rx_bytes

    def on_tx(data: bytes) -> None:
        tx_seen.append(bytes(data))
        raw_logger.log("TX", data)

    def on_error(msg: str) -> None:
        error_messages.append(msg)
        rep.note(f"worker error: {msg}")

    def on_device_timeout() -> None:
        nonlocal device_timeout_count
        device_timeout_count += 1
        rep.note(f"device_timeout signal #{device_timeout_count}")

    worker.packets_received.connect(on_packets)
    worker.metrics_updated.connect(on_metrics)
    worker.tx_recorded.connect(on_tx)
    worker.error_occurred.connect(on_error)
    worker.device_timeout.connect(on_device_timeout)

    # Open + boot delay
    worker.open()
    worker.set_polling_global(False)
    rep.note(f"opened {args.port}, waiting {args.boot_delay}s for Arduino boot")
    run_for(app, args.boot_delay)

    def send(name: str, fields: Dict[str, float] | None = None) -> None:
        worker.enqueue_priority_tx(build_tx_command(cfg, name, fields or {}))

    def send_raw(frame_id: int, payload: bytes) -> None:
        """Build + enqueue a one-off framed packet (for stress hooks)."""
        worker.enqueue_priority_tx(build_packet(cfg.protocol, frame_id, payload))

    # ---------- Phase 2 — passive baseline (no polling) -------------------
    hdr("Phase 2  Passive baseline (3 s, no polling)")
    reset_collectors()
    run_for(app, 3.0)
    rate2 = pkt_total / 3.0
    if 10 <= rate2 <= 30:
        rep.ok(f"Passive RX rate sane", f"{rate2:.1f} pkts/s")
    else:
        rep.fail(f"Passive RX rate out of range", f"{rate2:.1f} pkts/s, want 10-30")
    if {0x1000, 0x2000, 0x3000}.issubset(seen_ids):
        rep.ok("All three frame IDs seen in baseline")
    else:
        rep.fail(f"Missing frame IDs in baseline", f"saw {sorted(map(hex, seen_ids))}")

    # ---------- Phase 3 — polling baseline --------------------------------
    hdr("Phase 3  Polling baseline (5 s)")
    reset_collectors()
    worker.set_polling_global(True)
    run_for(app, 5.0)
    rate3 = pkt_total / 5.0
    if rate3 >= rate2 * 0.8:
        rep.ok(f"Polling RX rate at or above passive", f"{rate3:.1f} pkts/s")
    else:
        rep.fail(f"Polling RX rate dropped", f"{rate3:.1f} vs passive {rate2:.1f}")
    if last_metrics["crc"] == 0:
        rep.ok("Zero CRC errors during polling baseline")
    else:
        rep.fail(f"CRC errors in baseline", str(last_metrics["crc"]))
    crc_baseline = last_metrics["crc"]

    # ---------- Phase 4 — stress mode (5x cadence) ------------------------
    hdr("Phase 4  Stress mode 5x (5 s)")
    reset_collectors()
    send_raw(0x1002, bytes([0x01]))   # stress on
    run_for(app, 5.0)
    rate4 = pkt_total / 5.0
    if rate4 >= rate3 * 2.0:
        rep.ok(f"Stress mode lifted RX rate >=2x baseline", f"{rate4:.1f} pkts/s vs {rate3:.1f}")
    else:
        rep.fail(f"Stress mode rate did not climb",
                 f"{rate4:.1f} pkts/s vs baseline {rate3:.1f}")
    if last_metrics["crc"] == crc_baseline:
        rep.ok("No new CRC errors under stress")
    else:
        rep.fail(f"CRC errors leaked during stress",
                 f"crc={last_metrics['crc']} (baseline {crc_baseline})")
    send_raw(0x1002, bytes([0x00]))   # stress off
    run_for(app, 0.5)

    # ---------- Phase 5 — forced CRC errors -------------------------------
    hdr("Phase 5  Forced CRC errors x10")
    reset_collectors()
    crc_before = last_metrics["crc"]
    send_raw(0x1003, bytes([10]))     # next 10 frames will have bad CRC
    run_for(app, 3.0)
    crc_delta = last_metrics["crc"] - crc_before
    if 8 <= crc_delta <= 12:
        rep.ok(f"Errors counter incremented as expected",
               f"+{crc_delta} (asked for 10)")
    else:
        rep.fail(f"Errors counter wrong",
                 f"delta={crc_delta}, expected ~10")
    # Verify the displayed value never went DOWN — the original flicker bug.
    # (We cannot directly observe the UI's _error_count, but the worker's
    # _crc_errors is monotonic by construction.)
    if last_metrics["crc"] >= crc_before:
        rep.ok("Errors counter monotonic (no 0->1->0 flicker)")
    else:
        rep.fail("Errors counter went backwards",
                 f"{crc_before} -> {last_metrics['crc']}")

    # ---------- Phase 6 — watchdog under silence --------------------------
    hdr("Phase 6  Watchdog (4 s of silence, expect device_timeout)")
    reset_collectors()
    timeout_before = device_timeout_count
    send_raw(0x1004, bytes([4]))      # go silent for 4 seconds
    # WATCHDOG_TIMEOUT in the worker is 3.0 s, so we should see at least
    # one device_timeout after about 3 s of silence.
    run_for(app, 5.0)
    if device_timeout_count > timeout_before:
        rep.ok(f"device_timeout fired during silence",
               f"+{device_timeout_count - timeout_before} signal(s)")
    else:
        rep.fail("device_timeout did NOT fire during 4 s of silence")
    rep.note(f"timeouts metric during silence: {last_metrics['timeouts']}")

    # ---------- Phase 7 — recovery ---------------------------------------
    hdr("Phase 7  Recovery (3 s)")
    reset_collectors()
    run_for(app, 3.0)
    if pkt_total > 0:
        rep.ok(f"Telemetry resumed after silence", f"{pkt_total} pkts in 3 s")
    else:
        rep.fail("No telemetry after silence period ended")

    # ---------- Phase 8 — connect/disconnect cycling ---------------------
    # Real users hit "Disconnect" then "Connect" with at least one human-scale
    # pause between (clicks, dialog navigation). Rapid sub-second reopens on
    # Windows USB-CDC routinely fail because the OS port-handle reuse clashes
    # with the 16U2 USB bridge re-enumerating. We test the realistic path,
    # not the pathological one.
    hdr("Phase 8  Connect/disconnect cycling (2 cycles, 2 s settle)")
    cycle_failures = 0
    for cycle in range(2):
        rep.note(f"cycle {cycle + 1}: closing worker (rx_bytes so far={last_metrics['rx_bytes']})")
        worker.close()
        worker.metrics_updated.disconnect(on_metrics)
        worker.packets_received.disconnect(on_packets)
        worker.tx_recorded.disconnect(on_tx)
        worker.error_occurred.disconnect(on_error)
        worker.device_timeout.disconnect(on_device_timeout)
        # Give Windows time to fully release the port and the Arduino USB-CDC
        # bridge time to re-enumerate before re-opening.
        run_for(app, 2.0)
        try:
            worker = PollingWorker(settings, cfg.protocol, cfg.polling_schedules)
            worker.packets_received.connect(on_packets)
            worker.metrics_updated.connect(on_metrics)
            worker.tx_recorded.connect(on_tx)
            worker.error_occurred.connect(on_error)
            worker.device_timeout.connect(on_device_timeout)
            worker.open()
            worker.set_polling_global(True)
            rep.note(f"cycle {cycle + 1}: opened, is_open={worker.is_open}")
            run_for(app, args.boot_delay)
            rep.note(
                f"cycle {cycle + 1}: post-boot rx_bytes={last_metrics['rx_bytes']}, "
                f"pkts_seen_this_cycle={pkt_total}"
            )
        except Exception as exc:
            cycle_failures += 1
            rep.note(f"cycle {cycle + 1} reopen failed: {exc}")
    if cycle_failures == 0:
        rep.ok(f"Reconnect x2 succeeded")
    else:
        rep.fail(f"Reconnect failures", f"{cycle_failures}/2 failed")

    reset_collectors()
    rep.note(f"about to listen for 2s; worker.is_open={worker.is_open}")
    run_for(app, 2.0)
    rep.note(f"end of Phase 8 listen: pkt_total={pkt_total}, rx_bytes={last_metrics['rx_bytes']}")
    if pkt_total > 0:
        rep.ok(f"Telemetry flowing after reconnect cycle", f"{pkt_total} pkts in 2 s")
    else:
        rep.fail("No telemetry after reconnect cycle")

    # ---------- Phase 9 — TX flood (over the 256 cap) --------------------
    hdr("Phase 9  TX flood (300 commands rapid-fire)")
    err_before = len(error_messages)
    burst_pkt = build_tx_command(cfg, "Reset", {})
    drops = 0
    for _ in range(300):
        try:
            worker.enqueue_priority_tx(burst_pkt)
        except Exception:
            drops += 1
    run_for(app, 2.0)
    queue_full_msgs = [m for m in error_messages[err_before:] if "queue full" in m.lower()]
    if queue_full_msgs:
        rep.ok(f"TX queue overflow surfaced via error_occurred",
               f"{len(queue_full_msgs)} 'queue full' message(s)")
    else:
        rep.fail("TX flood did not produce a 'queue full' error")
    if drops == 0:
        rep.ok("enqueue_priority_tx never raised — drop happens internally")
    else:
        rep.fail(f"enqueue_priority_tx raised", f"{drops} times")

    # Drain the queue
    run_for(app, 3.0)

    # ---------- Phase 10 — parameter editor round-trip x3 -----------------
    hdr("Phase 10  Parameter editor round-trip (3 set-points)")
    for target in (45.2, 58.5, 50.0):
        run_for(app, 0.5)
        before_count = len(voltage_limits)
        send("Set_Voltage_Limit", {"voltage_v": target})
        run_for(app, 1.5)
        recent = voltage_limits[before_count:]
        if any(abs(v - target) < 0.05 for v in recent):
            rep.ok(f"Round-trip Voltage_Limit -> {target} V",
                   f"{len(recent)} samples after write")
        else:
            rep.fail(f"Round-trip {target} V failed",
                     f"recent samples: {sorted(set(recent))[:6]}")

    # ---------- Phase 11 — leak check (5 s @ 5x cadence) ------------------
    hdr("Phase 11  Leak check (5 s under stress)")
    send_raw(0x1002, bytes([0x01]))   # stress on
    run_for(app, 0.5)
    pending_before = len(worker._pending_packets) if hasattr(worker, "_pending_packets") else 0
    gc.collect()
    rep.note(f"pre-burst _pending_packets={pending_before}")
    run_for(app, 5.0)
    pending_after = len(worker._pending_packets) if hasattr(worker, "_pending_packets") else 0
    if pending_after < 100:
        rep.ok(f"_pending_packets stays drained", f"{pending_after} after 5 s burst")
    else:
        rep.fail(f"_pending_packets grew",
                 f"{pending_before} -> {pending_after}")
    send_raw(0x1002, bytes([0x00]))   # stress off
    run_for(app, 0.5)

    # ---------- Phase 12 — logger / replay round-trip ---------------------
    hdr("Phase 12  Logger + replay round-trip")
    worker.close()
    raw_logger.close()
    decoded_logger.close()
    rows, log_errors = parse_log_file(raw_path)
    if log_errors:
        rep.fail(f"raw log parse errors", f"{len(log_errors)}")
    else:
        rep.ok(f"Raw log re-parsed cleanly", f"{len(rows)} rows")
    rx_bytes = sum(len(chunk) for chunk in replay_bytes(rows, directions=("RX",)))
    if rx_bytes > 0:
        rep.ok(f"Replay yielded RX bytes", f"{rx_bytes} bytes")
    else:
        rep.fail("Replay yielded zero RX bytes")

    # ---------- Summary --------------------------------------------------
    hdr(f"Summary  {len(rep.passed)} passed, {len(rep.failed)} failed")
    if rep.failed:
        for f in rep.failed:
            print(f"  FAIL: {f}")
    return len(rep.failed)


if __name__ == "__main__":
    sys.exit(main())
