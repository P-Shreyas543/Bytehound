"""Live plot correctness (Documentation/live_plot_plan.md, phase L1: P1-P4).

P1  a gap in the data (unplug, silent device) breaks the line
P2  boolean / enum / bitfield signals are drawn as steps
P3  a third unit in one panel is never drawn against the second unit's axis
P4  points skipped under load break the line instead of being joined
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from app.ui import plot_panel
from app.ui.plot_panel import TimeSeriesBuffer

GAP_MIN_S = getattr(plot_panel, "GAP_MIN_S", 0.5)

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"
VOLT, AMP, SOC = (0x1000, "Pack Voltage"), (0x1000, "Pack Current"), (0x1000, "Pack SOC")
STATE, FLAGS = (0x3000, "BMS State"), (0x3000, "Fault Flags")


def _breaks(buf: TimeSeriesBuffer) -> int:
    return int(np.isnan(buf.arrays()[1]).sum())


# ---------------------------------------------------------------- P1 / P4: history buffer

def test_a_long_silence_breaks_the_line():
    buf = TimeSeriesBuffer()
    for i in range(11):                                   # 10 Hz for 1 s
        buf.append(i * 0.1, 1.0)
    buf.append(5.0, 2.0)                                  # 4 s of silence
    xs, ys = buf.arrays()
    assert _breaks(buf) == 1
    k = int(np.flatnonzero(np.isnan(ys))[0])
    assert xs[k - 1] == pytest.approx(1.0) and xs[k + 1] == 5.0
    assert xs[k - 1] < xs[k] < xs[k + 1]                  # x stays sorted (window lookups)
    assert xs[k] - xs[k - 1] < 1e-9                       # break right after the last sample:
    #                                                       a step curve must not hold into the gap
    assert buf.last_x() == 5.0 and ys[-1] == 2.0


@pytest.mark.parametrize("pause, breaks", [(0.3, 0), (GAP_MIN_S + 0.1, 1)])
def test_fast_streams_break_only_after_the_minimum_gap(pause, breaks):
    """At 100 Hz a short hiccup is not a gap; a pause over GAP_MIN_S is."""
    buf = TimeSeriesBuffer()
    for i in range(100):
        buf.append(i * 0.01, 0.0)
    buf.append(0.99 + pause, 0.0)
    assert _breaks(buf) == breaks


@pytest.mark.parametrize("gap, breaks", [(3.0, 0), (6.0, 1)])
def test_slow_signals_break_relative_to_their_own_interval(gap, breaks):
    """A 1 s polled signal: 3 s is within 5 intervals, 6 s is a gap."""
    buf = TimeSeriesBuffer()
    for i in range(10):
        buf.append(float(i), 0.0)
    buf.append(9.0 + gap, 0.0)
    assert _breaks(buf) == breaks


def test_regular_and_jittery_sampling_never_breaks():
    rng = np.random.default_rng(1)
    buf = TimeSeriesBuffer()
    t = 0.0
    for _ in range(2000):
        t += 0.05 * rng.uniform(0.5, 1.5)
        buf.append(t, 1.0)
    assert _breaks(buf) == 0


def test_mark_break_splits_at_the_next_sample():
    buf = TimeSeriesBuffer()
    buf.mark_break()                                      # nothing to break yet
    buf.append(0.0, 1.0)
    buf.append(0.1, 1.0)
    buf.mark_break()
    buf.append(0.2, 1.0)                                  # no time gap, but points were skipped
    buf.append(0.3, 1.0)
    assert _breaks(buf) == 1 and len(buf) == 5


def test_window_lookup_and_clear_with_breaks():
    buf = TimeSeriesBuffer()
    for i in range(11):
        buf.append(i * 0.1, 1.0)
    buf.append(5.0, 2.0)
    xs, ys = buf.arrays_since(4.0)
    assert ys[-1] == 2.0 and len(xs) == 2                 # the break point + the new sample
    buf.clear()
    buf.append(0.0, 1.0)
    buf.append(10.0, 1.0)                                 # no interval known after clear: no break
    assert _breaks(buf) == 0


def test_pyqtgraph_draws_separate_pieces_across_a_break(qapp):
    import pyqtgraph as pg

    xs = np.array([0.0, 1.0, 2.0, 2.5, 3.0, 4.0])
    ys = np.array([0.0, 1.0, 0.0, math.nan, 1.0, 0.0])
    for step in (None, "right"):
        item = pg.PlotDataItem(stepMode=step)
        item.setData(xs, ys, connect="finite", autoDownsample=True, clipToView=True)
        path = item.curve.getPath()
        assert len(path.toSubpathPolygons()) == 2, step   # two pieces, nothing across the gap


# ---------------------------------------------------------------- GUI: P1-P4 in the live plot

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp, monkeypatch):
    import app.ui.main_window as mw

    monkeypatch.setattr(mw.MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_popup_warning", lambda self, *a, **k: None)
    w = mw.MainWindow()
    w._load_config_from_path(TEMPLATE, suppress_popups=True)
    w.show()
    w._plot_dock.setVisible(True)
    QApplication.processEvents()
    yield w
    w.close()


def _feed(w, key, xs, ys):
    buf = w._plot_history.get(key)
    if buf is None:
        buf = w._plot_history[key] = w._make_history_buffer()
    for x, y in zip(xs, ys, strict=True):
        buf.append(x, y)


def test_curves_break_at_gaps_in_the_live_plot(win):
    win._add_signal_to_panel(0, VOLT)
    _feed(win, VOLT, [0.0, 0.1, 0.2, 5.0, 5.1], [1, 2, 3, 4, 5])
    win._redraw_plot()
    curve = win._plot_panels[0].curves[VOLT]
    assert curve.opts["connect"] == "finite"
    assert len(curve.curve.getPath().toSubpathPolygons()) == 2


def test_state_signals_are_drawn_as_steps(win):
    for key in (VOLT, STATE, FLAGS):
        win._add_signal_to_panel(0, key)
        _feed(win, key, [0.0, 0.1, 0.2], [0, 1, 0])
    win._redraw_plot()
    curves = win._plot_panels[0].curves
    assert curves[STATE].opts["stepMode"] == "right"      # enum
    assert curves[FLAGS].opts["stepMode"] == "right"      # bitfield
    assert not curves[VOLT].opts["stepMode"]              # measured value: a line


def test_a_third_unit_is_refused_when_adding(win, monkeypatch):
    warned = []
    monkeypatch.setattr(win, "_popup_warning", lambda title, text: warned.append(text))
    win._add_signal_to_panel(0, VOLT)
    win._add_signal_to_panel(0, AMP)
    win._add_signal_to_panel(0, SOC)                      # V and A already: % is a third unit
    assert win._plot_panels[0].assigned_keys == [VOLT, AMP]
    assert warned and "third unit" in warned[0]


def test_a_saved_third_unit_is_not_drawn_on_the_wrong_axis(win):
    """Layouts saved before the check can still hold three units."""
    panel = win._plot_panels[0]
    panel.assigned_keys[:] = [VOLT, AMP, SOC]
    for key in panel.assigned_keys:
        _feed(win, key, [0.0, 0.1], [1, 2])
    win._redraw_plot()
    assert panel.curves[AMP].getViewBox() is panel.right_vb
    assert SOC not in panel.curves                        # never plotted against the A axis


def test_points_dropped_under_load_break_the_line(win):
    win._add_signal_to_panel(0, VOLT)
    _feed(win, VOLT, [0.0, 0.1], [1, 2])
    win._pending_packets = type(win._pending_packets)(maxlen=2)
    win._on_packets_received([object()] * 5)              # 3 more than fit: display skips them
    _feed(win, VOLT, [0.2], [3])                          # next sample after the skipped ones
    assert _breaks(win._plot_history[VOLT]) == 1


def test_hover_readout_shows_no_value_inside_a_gap(win):
    win._add_signal_to_panel(0, VOLT)
    _feed(win, VOLT, [0.0, 0.1, 0.2, 5.0], [1, 2, 3, 4])
    win._redraw_plot()
    xs, ys = win._plot_history[VOLT].arrays()
    gap_x = float(xs[np.flatnonzero(np.isnan(ys))[0]])
    for t in (gap_x, 1.0, 2.6, 4.9):                     # anywhere inside the 0.2 .. 5.0 gap
        text = win._plot_readout_text(win._plot_panels[0], t)
        assert "Pack Voltage=–" in text and "nan" not in text.lower(), t
    assert "Pack Voltage=4.00" in win._plot_readout_text(win._plot_panels[0], 5.0)
