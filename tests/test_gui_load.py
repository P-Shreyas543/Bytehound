"""GUI-thread costs found on the NUCLEO HIL rig at 3,250 frames/s."""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from app.decoder.config_loader import load_config
from app.protocol.packet_parser import ParsedPacket
from app.ui.telemetry_pipeline import CONSOLE_LINES_PER_SECOND, TelemetryPipelineMixin

TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "resources" / "config_template"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_card_repolishes_only_when_its_state_changes(qapp):
    from app.ui.telemetry_cards import SignalCardWidget

    spec = next(s for s in load_config(TEMPLATE).all_signals if not s.is_boolean)
    card = SignalCardWidget(spec)
    calls = []

    # Count style passes only. Never hold the QStyle itself: a test that kept
    # a wrapper of the application style broke later tests once that style
    # was replaced (stale shiboken wrapper, "QCommonStyle already deleted").
    class Style:
        def polish(self, _w):
            calls.append("polish")

        def unpolish(self, _w):
            calls.append("unpolish")

    card.val_label.style = Style
    card.status_pill.style = Style
    try:
        card.update_value(0.0, "ok")
        after_first = calls.count("polish")
        assert after_first <= 2                    # label (+ pill unless already "ok")
        for i in range(1, 100):
            card.update_value(float(i), "ok")
        assert calls.count("polish") == after_first   # unchanged state: no style pass
        card.update_value(5.0, "warning")
        assert calls.count("polish") == after_first + 2
        assert card.status_pill.text() == "WARN" and card.val_label.text() == "5.000"
    finally:
        del card.val_label.style
        del card.status_pill.style
        card.deleteLater()
        qapp.processEvents()


def test_console_shows_at_most_its_budget_and_counts_the_rest():
    class Window(TelemetryPipelineMixin):
        def __init__(self):
            self._pending_packets = deque(maxlen=10_000)
            self._serial = None
            self._session_started = None
            self._console = MagicMock()
            self._console.verticalScrollBar.return_value.value.return_value = 0
            self._console.verticalScrollBar.return_value.maximum.return_value = 0
            self._console_dock = MagicMock()
            self._console_dock.isVisible.return_value = True
            self.handled = 0
            self._table_model = MagicMock()
            self._plot_last_redraw = 0.0
            self._plot_redraw_interval_s = 0.05

        def _stage_table_cells(self):
            pass

        def _handle_packet(self, packet, pre_decoded=None, rx_perf=None):
            self.handled += 1

        def _refresh_counts_label(self):
            pass

        def _redraw_plot(self):
            pass

    win = Window()
    pkt = ParsedPacket(raw=b"\xAA\x55\x00\x10", frame_id=0x1000, payload=b"", ok=True)
    win._pending_packets.extend((pkt, None, time.perf_counter()) for _ in range(5000))
    win._console_last_flush = time.monotonic() - 0.1
    win._flush_ui_inner()

    assert win.handled == 5000                  # every frame still processed
    text = win._console.appendPlainText.call_args_list[0].args[0]
    lines = text.split("\n")
    shown = len(lines) - 1
    assert 1 <= shown <= CONSOLE_LINES_PER_SECOND * 0.2
    assert lines[0].startswith(f"… {5000 - shown} frames not shown")
    assert all(", RX, AA 55 00 10" in ln for ln in lines[1:])


def test_flush_stops_at_its_time_budget_and_keeps_the_rest_in_order(monkeypatch):
    """A large UI backlog used to be drained in one call (0.1-1.5 s stalls
    at 5,000 frames/s). Each flush now stops at FLUSH_BUDGET_S; the rest is
    handled by later flushes, in order, each packet exactly once."""
    from types import SimpleNamespace

    import app.ui.telemetry_pipeline as tp

    clock = {"t": 100.0}
    monkeypatch.setattr(tp, "time", SimpleNamespace(perf_counter=lambda: clock["t"], time=time.time,
                                                    monotonic=time.monotonic))

    class Window(TelemetryPipelineMixin):
        def __init__(self):
            self._pending_packets = deque(maxlen=10_000)
            self._serial = None
            self._session_started = None
            self._console = MagicMock()
            self._console_dock = None
            self._table_model = MagicMock()
            self._plot_last_redraw = 0.0
            self._plot_redraw_interval_s = 0.05
            self.handled = []

        def _handle_packet(self, packet, pre_decoded=None, rx_perf=None):
            self.handled.append(packet.frame_id)
            clock["t"] += 0.0005                       # 0.5 ms of GUI work per packet

        def _stage_table_cells(self):
            pass

        def _refresh_counts_label(self):
            pass

        def _redraw_plot(self):
            pass

    win = Window()
    win._pending_packets.extend(
        (ParsedPacket(raw=b"", frame_id=i, payload=b"", ok=True), None, 0.0) for i in range(1000))
    win._flush_ui_inner()
    first = len(win.handled)
    budget_packets = int(tp.FLUSH_BUDGET_S / 0.0005)
    assert budget_packets <= first <= budget_packets + 32       # checked every 32 packets
    assert len(win._pending_packets) == 1000 - first
    flushes = 1
    while win._pending_packets:
        win._flush_ui_inner()
        flushes += 1
    assert win.handled == list(range(1000))                      # in order, exactly once
    assert flushes >= 1000 // (budget_packets + 32)


def test_queue_saturation_warning_is_rate_limited(caplog):
    class Window(TelemetryPipelineMixin):
        def __init__(self):
            self._pending_packets = deque(maxlen=100)
            self._serial = None

    win = Window()
    pkt = (ParsedPacket(raw=b"", frame_id=1, payload=b"", ok=True), None, 0.0)
    with caplog.at_level("WARNING", logger="bytehound.ui"):
        for _ in range(200):
            win._on_packets_received([pkt] * 50)
    saturations = [r for r in caplog.records if "saturated" in r.getMessage()]
    assert len(saturations) == 1
    assert win._backpressure_dropped_count == 200 * 50 - 100


def test_finishing_wait_blocks_the_gui_at_most_one_short_poll_at_a_time(qapp, monkeypatch):
    """Stop Logging waits for segment finishing on the GUI thread; each
    blocking wait must be short so the window keeps responding."""
    from app.ui import logging_session as ls

    assert ls.LoggingSessionMixin._DRAIN_POLL_MS <= 50
    waits = []

    class SlowDrainer:
        def __init__(self):
            self.calls = 0

        def await_drain(self, timeout=None):
            waits.append(timeout)
            self.calls += 1
            return self.calls >= 5

        def pending_rows(self):
            return 1

    class Host(ls.LoggingSessionMixin):
        def __init__(self):
            self.activity = []

        def _log_activity(self, msg):
            self.activity.append(msg)

    monkeypatch.setattr(ls, "QProgressDialog", lambda *a, **k: MagicMock(wasCanceled=lambda: False))
    Host()._wait_for_logger_drain([("logging session", SlowDrainer())])
    assert len(waits) == 5 and max(waits) <= 0.05
