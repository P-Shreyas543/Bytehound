"""Live plot L3 (Documentation/live_plot_plan.md): U1 a signal that stopped
arriving is shown as stale; U2 recorded gaps (connection lost → reconnect)
are shaded on the time axis."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"
VOLT = (0x1000, "Pack Voltage")


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
    w._plot_history.setdefault(VOLT, w._make_history_buffer())
    w._set_plot_live(True)
    yield w
    w.close()


def _at(w, seconds: float) -> None:
    """Put the session clock at ``seconds``."""
    w._session_started_perf = time.perf_counter() - seconds


def _legend_text(w, curve) -> str:
    legend = w._plot_panels[0].plot_item.legend
    return next(lbl.text for sample, lbl in legend.items if sample.item is curve)


def test_a_signal_that_stops_is_shown_stale_until_data_returns(win):
    buf = win._plot_history[VOLT]
    for i in range(101):                                   # 10 Hz for 10 s
        buf.append(i * 0.1, 50.0)
    _at(win, 10.2)
    win._redraw_plot()
    curve = win._plot_panels[0].curves[VOLT]
    assert curve.opts["pen"].style() == Qt.PenStyle.SolidLine
    assert "no data" not in _legend_text(win, curve)

    _at(win, 22.0)                                         # 12 s without a sample
    win._redraw_plot()
    assert curve.opts["pen"].style() == Qt.PenStyle.DashLine
    assert curve.opts["pen"].color().alpha() < 255
    assert "no data for 12 s" in _legend_text(win, curve)

    buf.append(22.0, 51.0)                                 # data again
    win._redraw_plot()
    assert curve.opts["pen"].style() == Qt.PenStyle.SolidLine
    assert _legend_text(win, curve).endswith("Pack Voltage")


def test_age_is_readable_for_long_outages(win):
    fmt = win._format_age
    assert (fmt(12), fmt(150), fmt(7300)) == ("12 s", "2 min", "2 h 1 min")


def _regions(win, i=0):
    return [tuple(round(v, 1) for v in r.getRegion()) for r in win._plot_panels[i].__dict__.get("_bh_gap_regions", [])]


def test_recorded_gaps_are_shaded_in_every_panel_and_an_open_gap_grows(win):
    _at(win, 5.0)
    win._plot_gap_begin()
    _at(win, 8.0)
    win._plot_gap_end()
    _at(win, 12.0)
    win._plot_gap_begin()                                  # still open
    _at(win, 15.0)
    win._redraw_plot()
    for i in range(len(win._plot_panels)):
        assert _regions(win, i) == [(5.0, 8.0), (12.0, 15.0)]
    _at(win, 18.0)
    win._redraw_plot()
    assert _regions(win)[1] == (12.0, 18.0)               # open gap follows the clock
    win._reset_session_clock()                             # a new session clock: old gaps go
    assert _regions(win) == [] and win._plot_gaps == []


def test_connection_lost_with_auto_reconnect_opens_a_gap_reconnect_closes_it(win, monkeypatch):
    win._saved_settings = SimpleNamespace(auto_reconnect=True, port="COM9")
    monkeypatch.setattr(win, "_disconnect", lambda **k: None)
    monkeypatch.setattr(win._reconnect_timer, "start", lambda *a: None)
    _at(win, 30.0)
    win._on_connection_lost()
    assert win._plot_gaps and win._plot_gaps[-1][1] is None
    _at(win, 34.0)
    win._plot_gap_end()                                    # what a successful reconnect calls
    assert win._plot_gaps[-1] == [pytest.approx(30.0, abs=0.1), pytest.approx(34.0, abs=0.1)]


def test_no_gap_without_auto_reconnect_and_user_disconnect_closes_an_open_gap(win, monkeypatch):
    win._saved_settings = SimpleNamespace(auto_reconnect=False, port="COM9")
    monkeypatch.setattr(win, "_disconnect", lambda **k: None)
    win._on_connection_lost()
    assert not getattr(win, "_plot_gaps", [])
    monkeypatch.undo()
    _at(win, 40.0)
    win._plot_gap_begin()
    _at(win, 41.0)
    win._disconnect(reason="Disconnected")                 # the user gives up waiting
    assert win._plot_gaps[-1][1] == pytest.approx(41.0, abs=0.1)
