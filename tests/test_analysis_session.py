"""Analysis Suite with a logging session (Plane.md Part B), end to end:
open → plot overview → zoom to full resolution → exact stats → cursor value
→ full-resolution export."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.serial_logging.session import SessionLog, SessionSettings

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def session_folder(tmp_path_factory):
    config = load_config(TEMPLATE)
    folder = tmp_path_factory.mktemp("as") / "bench_session"
    clk = {"wall": 1_800_000_000.0, "perf": 50.0}

    class Raw:
        def start(self, path, meta):
            path.write_bytes(b"")

        def stop(self):
            return None

    s = SessionLog(folder, config, SessionSettings(segment_seconds=600), raw_capture=Raw(),
                   clock=lambda: clk["wall"], perf=lambda: clk["perf"], disk_free=lambda p: 1 << 40)
    s.start()
    # 3 hours at 10 Hz cycles = 108k rows over 18 segments: overview must use
    # summaries, a 2-minute zoom must be full resolution.
    for i in range(108_000):
        for fid, f in config.frames.items():
            payload = bytes(((i // 7 + k * 31 + fid) & 0xFF) for k in range(f.payload_length))
            s.log_frame(decode_frame(config, fid, payload, {}), clk["perf"])
        clk["wall"] += 0.1
        clk["perf"] += 0.1
        if i % 10 == 0:
            s.tick()
            seg = s._segment
            while seg is not None and seg.event is not None and seg.event.pending_rows() > 20_000:
                time.sleep(0.01)
    s.stop()
    assert s.await_finished(300)
    return folder


def _pump(app, seconds, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until and until():
            return True
        time.sleep(0.01)
    return until is None


def test_session_in_analysis_suite(qapp, session_folder, tmp_path, monkeypatch):
    from app.serial_logging import session_analysis as sa
    from app.ui import analysis_suite as asu

    monkeypatch.setattr(asu.AnalysisSuiteWindow, "_popup_warning", lambda self, *a, **k: None)
    # Scale the full-resolution threshold to this 3-hour test session (the
    # real one is 400k rows): the overview must use summaries, a 2-minute
    # zoom must be full resolution.
    monkeypatch.setattr(sa, "FULL_RES_LIMIT", 20_000)
    win = asu.AnalysisSuiteWindow()
    try:
        win._open_logging_session(str(session_folder))
        assert _pump(qapp, 60, until=lambda: len(win._logs) == 1)
        entry = next(iter(win._logs.values()))
        assert entry.is_session and entry.start_timestamp == pytest.approx(1_800_000_000.0)
        param = next(p for p in entry.available_params() if p.startswith("0x1000."))

        tree = win._param_tree
        item = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                    if tree.topLevelItem(i).text(0) == param)
        item.setCheckState(0, Qt.Checked)
        assert _pump(qapp, 30, until=lambda: entry.id in win._curves and param in win._curves[entry.id])
        assert entry.view.level != 0                       # 3 h overview: min/max summary

        # Zoom to two minutes → full resolution arrives in the background.
        pw = win._plot_widgets[0]
        pw.setXRange(3600.0, 3720.0, padding=0)
        assert _pump(qapp, 30, until=lambda: entry.view.level == 0)
        x, y = win._curves[entry.id][param].getData()
        assert np.nanmin(x) <= 3600.0 and np.nanmax(x) >= 3720.0

        # Stats of the visible range are exact (match brute force on the CSVs).
        src = entry.source
        frames = []
        for seg in src.segments:
            df = pd.read_csv(seg.csv, usecols=["time_utc", param])
            t = (pd.to_datetime(df["time_utc"], utc=True, format="ISO8601").astype("int64") / 1e9
                 - src.start_epoch).to_numpy()
            frames.append((t, pd.to_numeric(df[param], errors="coerce").to_numpy(dtype=float)))
        t = np.concatenate([a for a, _ in frames])
        v = np.concatenate([b for _, b in frames])
        rows = win._visible_curve_rows()
        row = next(r for r in rows if r["param"] == param)
        x0, x1 = row["x_range"]
        st = row["stats_fn"](x0, x1)
        sel = (t >= x0) & (t <= x1) & ~np.isnan(v)
        assert st["n"] == int(sel.sum())
        assert st["mean"] == pytest.approx(v[sel].mean())
        assert st["median"] == pytest.approx(np.median(v[sel])) and not st["approx"]

        # Whole-session stats: exact min/max/mean/n via summaries.
        monkeypatch.setattr(sa, "FULL_RES_LIMIT", 1000)
        full = entry.range_stats(param, 0.0, src.duration)
        ok = ~np.isnan(v)
        assert full["n"] == int(ok.sum()) and full["approx"]
        assert full["min"] == pytest.approx(v[ok].min()) and full["max"] == pytest.approx(v[ok].max())
        assert full["mean"] == pytest.approx(v[ok].mean(), rel=1e-12)

        # Cursor / hover values are full resolution, not envelope points.
        q = 3650.05
        expect = float(np.interp(q, t[ok], v[ok]))
        assert entry.value_at(param, q) == pytest.approx(expect)

        # Export the visible range at full resolution.
        out = tmp_path / "zoom.csv"
        n = entry.source.export_range([param], x0, x1, out)
        assert n == int(((t >= x0) & (t <= x1)).sum())
    finally:
        win.close()
        _pump(qapp, 0.2)


def test_checking_parameters_quickly_keeps_the_full_range(qapp):
    """Checking several parameters before the first plot was fitted used to
    "restore" pyqtgraph's default 0–1 range and pin every plot to it."""
    from app.ui import analysis_suite as asu
    from app.ui.log_io import LogEntry

    win = asu.AnalysisSuiteWindow()
    win.resize(1200, 800)
    win.show()
    try:
        x = np.linspace(0.0, 1000.0, 5001)
        entry = LogEntry(id="L1", path="mem.csv", name="mem", elapsed=x,
                         columns={"A (V)": np.sin(x), "B (V)": np.cos(x), "C (A)": x * 0.01})
        win._on_log_loaded("L1", "mem.csv", entry)
        tree = win._param_tree
        for i in range(tree.topLevelItemCount()):
            tree.topLevelItem(i).setCheckState(0, Qt.Checked)   # no event processing in between
        _pump(qapp, 1.0)
        lo, hi = win._plot_widgets[0].getPlotItem().vb.viewRange()[0]
        assert lo <= 1.0 and hi >= 999.0
    finally:
        win.close()
        _pump(qapp, 0.2)
