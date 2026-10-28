"""Live plot L2 (Documentation/live_plot_plan.md): curves are drawn at screen
resolution — min/max per bucket, gaps kept — re-reduced for the visible range
when exploring, and the redraw rate adapts to its own cost."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from app.ui.plot_panel import peak_decimate

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"
VOLT = (0x1000, "Pack Voltage")


def _series(n=200_000, seconds=300.0, gaps=()):
    x = np.linspace(0.0, seconds, n)
    y = np.sin(x * 3.0) + 0.01 * np.cos(x * 400.0)
    y[n // 3] = 9.0                       # a one-sample spike
    y[2 * n // 3] = -7.0
    for g in gaps:
        y[g] = np.nan
    return x, y


def test_short_series_are_returned_unchanged():
    x, y = np.arange(100.0), np.arange(100.0)
    dx, dy = peak_decimate(x, y, 1000)
    assert dx is x and dy is y


def test_reduction_keeps_extremes_order_and_size():
    x, y = _series()
    dx, dy = peak_decimate(x, y, 2000)
    assert len(dx) <= 2000 + 4
    assert np.nanmax(dy) == 9.0 and np.nanmin(dy) == -7.0       # spikes survive
    assert np.all(np.diff(dx) >= 0)                               # x stays sorted
    assert dx[0] == x[0] and dx[-1] <= x[-1]


def test_gaps_are_carried_through_never_bridged():
    gaps = (50_000, 50_001, 120_000)
    x, y = _series(gaps=gaps)
    dx, dy = peak_decimate(x, y, 2000)
    nan_x = dx[np.isnan(dy)]
    assert sorted(nan_x.tolist()) == sorted(x[list(gaps)].tolist())
    # every piece between breaks keeps its own extremes
    for a, b in ((0, 50_000), (50_002, 120_000), (120_001, len(x))):
        piece = (dx >= x[a]) & (dx <= x[b - 1]) & ~np.isnan(dy)
        assert np.max(dy[piece]) == np.max(y[a:b]) and np.min(dy[piece]) == np.min(y[a:b])


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp, monkeypatch):
    import app.ui.main_window as mw

    monkeypatch.setattr(mw.MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = mw.MainWindow()
    w.resize(1400, 900)
    w.show()
    w._load_config_from_path(TEMPLATE, suppress_popups=True)
    w._plot_dock.setVisible(True)
    QApplication.processEvents()
    w._add_signal_to_panel(0, VOLT)
    buf = w._plot_history.setdefault(VOLT, w._make_history_buffer())
    buf.set_max_samples(None)
    x, y = _series()
    for xv, yv in zip(x, y, strict=True):
        buf.append(float(xv), float(yv))
    w._session_started_perf = time.perf_counter() - 300.0
    w._plot_window_seconds = None
    yield w
    w.close()


def _pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def test_live_redraw_sends_screen_resolution_not_every_sample(win):
    win._plot_live = True
    win._redraw_plot()
    curve = win._plot_panels[0].curves[VOLT]
    xs, ys = curve.getData()
    width = win._plot_panels[0].plot_item.getViewBox().width()
    assert len(xs) <= max(500, int(2 * width)) + 4 < 200_000
    assert np.nanmax(ys) == 9.0 and np.nanmin(ys) == -7.0


def test_zooming_in_shows_every_sample_in_the_visible_range(win):
    win._plot_live = True
    win._redraw_plot()
    vb = win._plot_panels[0].plot_item.getViewBox()
    vb.setXRange(100.0, 101.0, padding=0)          # user zoom: Explore + re-reduce shortly after
    _pump(0.4)
    assert not win._plot_live
    xs, _ys = win._plot_panels[0].curves[VOLT].getData()
    x, _y = _series()
    raw_in_view = int(((x >= 100.0) & (x <= 101.0)).sum())
    in_view = int(((xs >= 100.0) & (xs <= 101.0)).sum())
    assert in_view == raw_in_view                    # full resolution, nothing reduced away


def test_redraw_rate_adapts_to_its_cost(win):
    now = 1000.0
    win._plot_last_redraw = now
    win._plot_redraw_cost_s = 0.0
    win._plot_pixel_time_s = 0.0
    assert win._plot_redraw_due(now + 1 / 30 + 0.001)                 # light plot, short window: 30 Hz
    win._plot_pixel_time_s = 0.34                                      # 5 min window on ~880 px
    assert not win._plot_redraw_due(now + 0.05)
    assert win._plot_redraw_due(now + 0.101)                           # capped at 10 Hz
    win._plot_pixel_time_s = 0.0
    win._plot_redraw_cost_s = 0.1
    assert not win._plot_redraw_due(now + 0.2)                        # heavy: wait 4 x cost
    assert win._plot_redraw_due(now + 0.41)


def test_live_axis_moves_only_when_it_shifts_a_pixel(win, monkeypatch):
    win._set_plot_live(True)
    pi = win._plot_panels[0].plot_item
    calls = []
    orig = pi.setXRange
    monkeypatch.setattr(pi, "setXRange", lambda *a, **k: (calls.append(a), orig(*a, **k)))
    win._redraw_plot()                                # first live redraw applies the range
    assert len(calls) == 1
    for _ in range(5):                                # well under a pixel later: no cascade
        win._redraw_plot()
    assert len(calls) == 1
    win._session_started_perf -= 30.0                 # 30 s later: many pixels
    win._redraw_plot()
    assert len(calls) == 2


def test_returning_to_live_after_panning_snaps_back(win):
    win._plot_window_seconds = 60
    win._set_plot_live(True)
    win._redraw_plot()
    vb = win._plot_panels[0].plot_item.getViewBox()
    vb.setXRange(10.0, 20.0, padding=0)              # user pans away: Explore
    _pump(0.3)
    assert not win._plot_live
    win._set_plot_live(True)
    win._redraw_plot()
    x0, x1 = vb.viewRange()[0]
    now = win._session_elapsed_s()
    assert x1 >= now - 1.0 and x0 >= now - 62.0      # back on the live 60 s window


def test_activating_a_configuration_refreezes_the_collector(win):
    import gc

    gc.unfreeze()
    win._load_config_from_path(TEMPLATE, suppress_popups=True)
    assert gc.get_freeze_count() > 0


def test_refreeze_frees_objects_that_are_no_longer_referenced():
    """Frozen objects are not lost for good: the next refreeze (the next
    configuration activation) unfreezes, collects, and frees them."""
    import gc
    import weakref

    from app.gc_tuning import refreeze

    class Node:
        pass

    node = Node()
    node.me = node                      # a cycle: only the collector can free it
    ref = weakref.ref(node)
    refreeze()                          # frozen while still referenced
    del node
    gc.collect()
    assert ref() is not None            # frozen objects are skipped by collections...
    refreeze()
    assert ref() is None                # ...until the next refreeze frees them
