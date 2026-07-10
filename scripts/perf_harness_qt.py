"""Qt-integrated performance harness for Bytehound.

Spins up a real ``MainWindow`` under the offscreen Qt platform, loads
the canonical test config, and drives synthetic ``ParsedPacket`` batches
through the live UI pipeline at a configurable rate. Times the 60 Hz
``_flush_ui`` callback per call and reports percentiles + pipeline
queue behaviour.

This is the missing half of the headless harness in ``perf_harness.py``:
that one measures parser → decoder → logger; this one measures everything
from packets-arriving-on-the-worker-signal onward (queue drain, table
model updates, console batching, plot redraw, rate label, hover cache).

Usage::

    python scripts\\perf_harness_qt.py                       # default 30 s, 500 Hz
    python scripts\\perf_harness_qt.py --rate 1000           # 1 kHz
    python scripts\\perf_harness_qt.py --duration 10 --json out.json
    python scripts\\perf_harness_qt.py --panels 4 --signals-per-panel 3

What gets measured
------------------
* ``flush_*``     – wall time spent inside ``MainWindow._flush_ui``.
* ``queue_depth`` – packets sitting in ``_pending_packets`` at the start
  of each flush. A growing queue means the UI thread is falling behind.
* ``dropped``     – packets the bounded deque silently evicted when the
  feed outran the drain.

Notes
-----
* The harness drives packets by calling ``window._on_packets_received``
  directly with a synthetic batch — same entry point the real worker
  signal uses, so the measurement path is identical to a live session.
* Logging (decoded.xlsx, raw.csv) is left OFF in this harness. Use
  ``perf_harness.py`` for the logger pipeline.
* ``QT_QPA_PLATFORM=offscreen`` is set automatically so this runs on
  headless CI / WSL.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.protocol.packet_parser import ParsedPacket
from app.protocol.packet_builder import build_packet
from app.ui.main_window import MainWindow

CANONICAL_CONFIG = ROOT / "tests" / "fixtures" / "canonical_config"


# ---------------------------------------------------------------------------
# Synthetic packet feeder
# ---------------------------------------------------------------------------

def _prebuild_packets(config, n: int) -> List[ParsedPacket]:
    """Build N ParsedPackets cycling through every configured frame.

    Pre-building once keeps the timed loop free of packet-construction work
    so the harness numbers reflect only the live-UI pipeline cost.
    """
    frame_ids = list(config.signals_by_frame.keys())
    if not frame_ids:
        raise RuntimeError("canonical config has no frames")

    packets: List[ParsedPacket] = []
    for i in range(n):
        fid = frame_ids[i % len(frame_ids)]
        specs = config.signals_by_frame[fid]
        payload_len = max((s.end_byte for s in specs), default=0)
        payload = bytes((i + j) & 0xFF for j in range(payload_len))
        raw = build_packet(config.protocol, fid, payload)
        packets.append(ParsedPacket(raw=raw, frame_id=fid, payload=payload, ok=True))
    return packets


# ---------------------------------------------------------------------------
# Instrumentation: wrap _flush_ui with a timer + queue-depth sampler
# ---------------------------------------------------------------------------

@dataclass
class FlushStats:
    flush_times_us: List[float] = field(default_factory=list)
    queue_depth_at_flush: List[int] = field(default_factory=list)
    dropped_total: int = 0


def _instrument(window: MainWindow, stats: FlushStats) -> None:
    """Wrap ``window._flush_ui`` so every invocation records its wall time."""
    original = window._flush_ui

    def wrapped() -> None:
        depth = len(getattr(window, "_pending_packets", ()))
        t0 = time.perf_counter()
        original()
        t1 = time.perf_counter()
        stats.flush_times_us.append((t1 - t0) * 1e6)
        stats.queue_depth_at_flush.append(depth)

    window._flush_ui = wrapped  # type: ignore[assignment]
    # The 60 Hz QTimer was bound to the unwrapped method during __init__;
    # rebind it so our wrapper actually fires on each timer tick.
    try:
        window._ui_timer.timeout.disconnect()
    except (RuntimeError, TypeError):
        # No connections to disconnect — fine on a freshly constructed window
        # before connectivity is wired up.
        pass
    window._ui_timer.timeout.connect(wrapped)
    # The real connect path also starts the timer when the worker opens;
    # in the harness we have no worker, so start it here.
    if not window._ui_timer.isActive():
        window._ui_timer.start()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class QtRunReport:
    rate_hz: int
    duration_s: float
    packets_planned: int
    packets_fed: int
    flush_count: int
    flush_mean_us: Optional[float]
    flush_p50_us: Optional[float]
    flush_p95_us: Optional[float]
    flush_p99_us: Optional[float]
    flush_max_us: Optional[float]
    queue_max: int
    queue_p95: float
    dropped_total: int
    panels: int
    signals_per_panel: int

    def to_dict(self) -> dict:
        return asdict(self)


def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(int(len(sorted_vals) * p), len(sorted_vals) - 1)
    return sorted_vals[idx]


def _build_report(rate_hz: int, duration_s: float, n_packets: int,
                  packets_fed: int, stats: FlushStats,
                  panels: int, signals_per_panel: int) -> QtRunReport:
    ft = sorted(stats.flush_times_us)
    qd = sorted(stats.queue_depth_at_flush)
    return QtRunReport(
        rate_hz=rate_hz,
        duration_s=round(duration_s, 3),
        packets_planned=n_packets,
        packets_fed=packets_fed,
        flush_count=len(ft),
        flush_mean_us=round(statistics.fmean(ft), 2) if ft else None,
        flush_p50_us=round(_percentile(ft, 0.50), 2) if ft else None,
        flush_p95_us=round(_percentile(ft, 0.95), 2) if ft else None,
        flush_p99_us=round(_percentile(ft, 0.99), 2) if ft else None,
        flush_max_us=round(ft[-1], 2) if ft else None,
        queue_max=max(stats.queue_depth_at_flush) if stats.queue_depth_at_flush else 0,
        queue_p95=round(_percentile(qd, 0.95), 1) if qd else 0.0,
        dropped_total=stats.dropped_total,
        panels=panels,
        signals_per_panel=signals_per_panel,
    )


def _print_report(r: QtRunReport) -> None:
    print("=" * 72)
    print(f"  Rate: {r.rate_hz} Hz   Duration: {r.duration_s} s")
    print(f"  Packets fed: {r.packets_fed}/{r.packets_planned}"
          f"   Flush calls: {r.flush_count}")
    print(f"  Panels: {r.panels}   Signals/panel: {r.signals_per_panel}")
    print(f"  Queue depth at flush — max: {r.queue_max}  p95: {r.queue_p95}"
          f"   Dropped: {r.dropped_total}")
    print("-" * 72)
    if r.flush_mean_us is not None:
        print(f"  flush_ui  mean: {r.flush_mean_us:>7.2f} us"
              f"   p50: {r.flush_p50_us:>7.2f} us"
              f"   p95: {r.flush_p95_us:>7.2f} us"
              f"   p99: {r.flush_p99_us:>7.2f} us"
              f"   max: {r.flush_max_us:>7.2f} us")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(rate_hz: int, duration_s: float,
        panels: int, signals_per_panel: int,
        hide_detail_docks: bool = False,
        hide_plot_dock: bool = False,
        hide_console: bool = False) -> QtRunReport:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window._load_config_from_path(CANONICAL_CONFIG)
    # Optional dock hides — exercise the hide-aware skips in _apply_decoded.
    if hide_detail_docks:
        if hasattr(window, "_bitfields_dock"):
            window._bitfields_dock.setVisible(False)
        if hasattr(window, "_enums_dock"):
            window._enums_dock.setVisible(False)
    if hide_plot_dock and hasattr(window, "_plot_dock"):
        window._plot_dock.setVisible(False)
    if hide_console and hasattr(window, "_console_dock"):
        window._console_dock.setVisible(False)

    # Wire up enough panels to stress the redraw path. Each panel gets the
    # first N signals from the config so they all have data to draw.
    config = window._config
    all_keys = [
        (fid, spec.signal_name)
        for fid, specs in config.signals_by_frame.items()
        for spec in specs
    ]
    if not all_keys:
        raise RuntimeError("no signals in canonical config — harness can't draw anything")

    # Re-build the grid to the requested panel count if needed.
    layout_name = {1: "1×1", 2: "2×1", 3: "1×3", 4: "2×2", 6: "3×1", 8: "2×4"}.get(panels)
    if layout_name is None:
        layout_name = "2×2"
        panels = 4
    window._layout_combo.setCurrentText(layout_name)
    window._rebuild_plot_grid(*({"1×1": (1, 1), "2×1": (2, 1), "1×3": (1, 3),
                                  "2×2": (2, 2), "3×1": (3, 1), "2×4": (2, 4)}[layout_name]))

    for idx, panel in enumerate(window._plot_panels):
        panel.assigned_keys.clear()
        # Round-robin assign keys so every panel has signals_per_panel curves.
        for j in range(signals_per_panel):
            key = all_keys[(idx * signals_per_panel + j) % len(all_keys)]
            if key not in panel.assigned_keys:
                panel.assigned_keys.append(key)

    n_packets = int(rate_hz * duration_s)
    packets = _prebuild_packets(config, n_packets)

    stats = FlushStats()
    _instrument(window, stats)

    # Feed packets at ~60 Hz cadence to mimic the real worker's batch emit
    # interval. Use a float accumulator so fractional packets-per-tick at
    # low rates (e.g. 100 Hz → 1.67 packets/tick) still hit the target
    # rate over time — int(rate/60) would round down and under-feed.
    feed_interval_ms = max(int(1000 / 60), 5)
    packets_per_tick = rate_hz / 60.0

    state = {"i": 0, "fed": 0, "acc": 0.0}
    start_perf = [None]  # boxed so the closure can set it

    def feed_one_batch() -> None:
        if start_perf[0] is None:
            start_perf[0] = time.perf_counter()
        i = state["i"]
        if i >= len(packets):
            return
        state["acc"] += packets_per_tick
        n = int(state["acc"])
        state["acc"] -= n
        if n <= 0:
            return
        end = min(i + n, len(packets))
        batch = packets[i:end]
        prev_depth = len(window._pending_packets)
        window._on_packets_received(batch)
        after = len(window._pending_packets)
        added = after - prev_depth
        if added < len(batch):
            stats.dropped_total += (len(batch) - added)
        state["i"] = end
        state["fed"] += len(batch)

    feeder = QTimer()
    feeder.setInterval(feed_interval_ms)
    feeder.timeout.connect(feed_one_batch)
    feeder.start()

    # Stop after the requested duration. Use a separate timer so the run
    # ends cleanly even if the feeder is still going.
    def stop_run() -> None:
        feeder.stop()
        # Give one final flush a chance to drain.
        QTimer.singleShot(50, app.quit)

    QTimer.singleShot(int(duration_s * 1000), stop_run)

    app.exec()

    actual_duration = (
        time.perf_counter() - start_perf[0] if start_perf[0] is not None else duration_s
    )
    return _build_report(
        rate_hz=rate_hz,
        duration_s=actual_duration,
        n_packets=n_packets,
        packets_fed=state["fed"],
        stats=stats,
        panels=panels,
        signals_per_panel=signals_per_panel,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Bytehound Qt-integrated perf harness")
    ap.add_argument("--rate", type=int, default=500, help="packets per second (default 500)")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds (default 10)")
    ap.add_argument(
        "--scenarios", type=str, default=None,
        help="comma-separated rates to sweep (overrides --rate)",
    )
    ap.add_argument("--panels", type=int, default=4, help="plot panels (1, 2, 3, 4, 6, 8)")
    ap.add_argument("--signals-per-panel", type=int, default=2)
    ap.add_argument("--hide-detail-docks", action="store_true",
                    help="exercise the bitfields/enums dock-hidden skip path")
    ap.add_argument("--hide-plot-dock", action="store_true",
                    help="exercise the plot-dock-hidden skip path")
    ap.add_argument("--hide-console", action="store_true",
                    help="exercise the console-dock-hidden skip path")
    ap.add_argument("--hide-all", action="store_true",
                    help="shortcut: hide detail + plot + console docks")
    ap.add_argument("--json", type=Path, help="write machine-readable report to this path")
    args = ap.parse_args()

    rates = (
        [int(x) for x in args.scenarios.split(",")]
        if args.scenarios
        else [args.rate]
    )

    reports: List[QtRunReport] = []
    for rate in rates:
        report = run(
            rate_hz=rate,
            duration_s=args.duration,
            panels=args.panels,
            signals_per_panel=args.signals_per_panel,
            hide_detail_docks=args.hide_detail_docks or args.hide_all,
            hide_plot_dock=args.hide_plot_dock or args.hide_all,
            hide_console=args.hide_console or args.hide_all,
        )
        _print_report(report)
        reports.append(report)

    if args.json:
        args.json.write_text(json.dumps([r.to_dict() for r in reports], indent=2))
        print(f"\nWrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
