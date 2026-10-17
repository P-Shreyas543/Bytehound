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
    real = card.val_label.style()

    class Style:
        def polish(self, w):
            calls.append("polish")
            real.polish(w)

        def unpolish(self, w):
            calls.append("unpolish")
            real.unpolish(w)

    card.val_label.style = Style
    card.status_pill.style = Style
    card.update_value(0.0, "ok")
    after_first = calls.count("polish")
    assert after_first <= 2                    # label (+ pill unless already "ok")
    for i in range(1, 100):
        card.update_value(float(i), "ok")
    assert calls.count("polish") == after_first   # unchanged state: no style pass
    card.update_value(5.0, "warning")
    assert calls.count("polish") == after_first + 2
    assert card.status_pill.text() == "WARN" and card.val_label.text() == "5.000"
    card.deleteLater()


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
