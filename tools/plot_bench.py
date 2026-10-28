"""Live plot cost benchmark (Documentation/live_plot_plan.md, phase L0: M2-M4).

Builds the real ``MainWindow`` offscreen, fills a plot grid with synthetic
signals whose histories already hold ``--hours`` of data at ``--hz``, then
times, on the GUI thread:

* ``redraw_idle``    — a redraw with no new data (the cost floor);
* ``redraw_tick``    — one new sample on every signal, then a redraw (the
  normal live case), for the sliding window and for "All session";
* ``readout``        — the hover readout for a panel, cache cold;
* ``trim_append``    — an append that hits the history budget and drops the
  oldest samples (the copy runs on the GUI thread).

Histories are filled by writing the buffers' arrays directly (filling
18 million samples one append at a time would take minutes); everything
measured afterwards goes through the normal code paths.

  python tools/plot_bench.py --hours 0.1 1 8 --grid 2x4 --signals-per-panel 8

Writes JSON to ``artifacts/plot_bench/`` and prints a summary table.
QSettings and the configuration history go to a temp folder.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

TEMPLATE = ROOT / "app" / "resources" / "config_template"


def _timed(fn, repeat: int) -> dict:
    vals = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        vals.append((time.perf_counter() - t0) * 1000.0)
    return {"median_ms": round(statistics.median(vals), 3), "max_ms": round(max(vals), 3), "n": repeat}


def _fill(buf, hz: float, seconds: float, phase: float) -> None:
    n = max(2, int(hz * seconds))
    x = np.linspace(0.0, seconds, n)
    y = 50.0 + 2.0 * np.sin(x / 7.0 + phase)
    cap = n + 1024
    buf._x = np.empty(cap)
    buf._y = np.empty(cap)
    buf._x[:n], buf._y[:n] = x, y
    buf._start, buf._end = 0, n
    buf._dt = 1.0 / hz


def bench(hours: float, args) -> dict:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import app.ui.main_window as mw

    tmp = Path(tempfile.mkdtemp(prefix="bh_plotbench_"))
    os.environ["BYTEHOUND_CONFIG_HISTORY_DIR"] = str(tmp / "history")
    ini = str(tmp / "settings.ini")

    class Iso(QSettings):
        def __init__(self, *a, **k):
            super().__init__(ini, QSettings.Format.IniFormat)

    mw.QSettings = Iso
    mw.MainWindow._check_and_recover_temp_logs = lambda self, *a, **k: None
    app = QApplication.instance() or QApplication(sys.argv)
    w = mw.MainWindow()
    w.resize(1600, 1000)
    w.show()
    w._load_config_from_path(TEMPLATE, suppress_popups=True)
    w._plot_history_budget_mb = args.budget_mb
    dock = w._plot_dock
    dock.setVisible(True)
    dock.setFloating(True)
    dock.resize(1500, 900)
    rows, cols = (int(v) for v in args.grid.lower().split("x"))
    w._rebuild_plot_grid(rows, cols, restore=False)
    app.processEvents()

    seconds = hours * 3600.0
    keys = []
    for p_idx, panel in enumerate(w._plot_panels):
        for s_idx in range(args.signals_per_panel):
            key = (0x7000 + p_idx, f"Synth_{p_idx}_{s_idx}")
            w._signal_unit_map[key] = "V"
            panel.assigned_keys.append(key)
            keys.append(key)
    w._sync_plot_keys()
    for i, key in enumerate(keys):
        buf = w._plot_history.setdefault(key, w._make_history_buffer())
        _fill(buf, args.hz, seconds, i * 0.3)
    samples = sum(len(w._plot_history[k]) for k in keys)
    w._session_started_perf = time.perf_counter() - seconds
    w._plot_live = True

    t_next = [seconds]

    def tick():
        t_next[0] += 1.0 / args.hz
        for k in keys:
            w._plot_history[k].append(t_next[0], 50.0)

    def redraw():
        w._redraw_plot()

    out = {"hours": hours, "hz": args.hz, "signals": len(keys), "grid": args.grid,
           "samples_total": samples, "history_mb": round(samples * 16 / 1e6, 1)}
    for label, window in (("window_5min", 300), ("all_session", None)):
        w._plot_window_seconds = window
        redraw()                                             # create curves, first full send
        app.processEvents()
        out[f"redraw_idle_{label}"] = _timed(redraw, args.repeat)
        out[f"redraw_tick_{label}"] = _timed(lambda: (tick(), redraw()), args.repeat)
    w._plot_window_seconds = None
    panel = w._plot_panels[0]

    def readout():
        w._hover_cache = {}
        w._plot_readout_text(panel, seconds * 0.5)
    out["readout_cold_all_session"] = _timed(readout, args.repeat)

    # Budget full: cap the first signal at its current length, then append.
    buf = w._plot_history[keys[0]]
    buf.set_max_samples(len(buf))
    worst = []
    spare = buf._x.shape[0] - buf._end                       # appends before the first trim
    for _ in range(spare + 2 * buf._slack(len(buf)) + 2):    # at least two trims
        t_next[0] += 1.0 / args.hz
        t0 = time.perf_counter()
        buf.append(t_next[0], 1.0)
        worst.append((time.perf_counter() - t0) * 1000.0)
    out["trim_append_one_signal"] = {"max_ms": round(max(worst), 3), "trims": sum(1 for v in worst if v > 0.05),
                                     "median_ms": round(statistics.median(worst), 4),
                                     "samples_kept": len(buf)}
    w.close()
    app.processEvents()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, nargs="+", default=[0.1, 1.0, 8.0])
    ap.add_argument("--hz", type=float, default=10.0, help="samples per second per signal")
    ap.add_argument("--grid", default="2x4")
    ap.add_argument("--signals-per-panel", type=int, default=8)
    ap.add_argument("--budget-mb", type=int, default=4096, help="large enough not to trim while filling")
    ap.add_argument("--repeat", type=int, default=20)
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts" / "plot_bench")
    args = ap.parse_args()

    results = [bench(h, args) for h in args.hours]
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"plot_bench_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"{'hours':>6} {'signals':>7} {'MB':>7} | {'idle 5m':>8} {'tick 5m':>8} | "
          f"{'idle all':>8} {'tick all':>9} | {'readout':>8} | {'trim max':>8}   (ms, median / max)")
    for r in results:
        def m(k, r=r):
            return f"{r[k]['median_ms']:.1f}/{r[k]['max_ms']:.0f}"
        print(f"{r['hours']:>6} {r['signals']:>7} {r['history_mb']:>7} | {m('redraw_idle_window_5min'):>8} "
              f"{m('redraw_tick_window_5min'):>8} | {m('redraw_idle_all_session'):>8} "
              f"{m('redraw_tick_all_session'):>9} | {m('readout_cold_all_session'):>8} | "
              f"{r['trim_append_one_signal']['max_ms']:>8.1f}")
    print(f"written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
