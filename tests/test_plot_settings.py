"""Tests for PlotSettingsDialog and plot settings application logic."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import QSettings

from app.ui.dialogs import PlotSettingsDialog
from app.ui.main_window import MainWindow
from app.ui.plot_panel import TimeSeriesBuffer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_plot_settings_dialog_save(qapp):
    settings = QSettings("BytehoundTest", "TestPlotSettingsDialog")
    settings.clear()

    # Initial dialog state
    dlg = PlotSettingsDialog(settings)
    assert not dlg._cap_chk.isChecked()
    assert dlg._window_combo.currentIndex() == 3  # default 5 minutes (300s)

    # Change settings
    dlg._cap_chk.setChecked(True)
    dlg._cap_spin.setValue(50000)
    dlg._window_combo.setCurrentIndex(1)  # 1 minute (60s)
    dlg._on_accept()

    # Verify QSettings saved correctly
    assert int(settings.value("plot/history_max_samples")) == 50000
    assert int(settings.value("plot/window_seconds")) == 60

    cap, win_s = dlg.get_values()
    assert cap == 50000
    assert win_s == 60

    settings.clear()


def test_mainwindow_plot_settings_application(qapp, monkeypatch):
    class MockSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__("BytehoundTestOrg", "BytehoundTestApp")
            self.clear()

    monkeypatch.setattr("app.ui.main_window.QSettings", MockSettings)
    monkeypatch.setattr("app.ui.main_window.ConnectionDialog", lambda *args, **kwargs: None)

    # Mock PlotSettingsDialog to return specific values on exec
    class MockPlotSettingsDialog:
        def __init__(self, settings, parent=None):
            pass
        def exec(self):
            return QDialog.DialogCode.Accepted
        def get_values(self):
            return 25000, 120  # cap = 25000, window = 120s

    monkeypatch.setattr("app.ui.dialogs.PlotSettingsDialog", MockPlotSettingsDialog)

    win = MainWindow()

    # Create dummy buffer in plot history
    key = (1, "TestSignal")
    buf = TimeSeriesBuffer(max_samples=None)
    # Populate buffer with 30000 samples
    for i in range(30000):
        buf.append(float(i), 1.0)
    assert len(buf) == 30000

    win._plot_history[key] = buf

    # Trigger plot settings update
    win._on_plot_settings()

    # Verify memory cap is applied to existing buffer
    assert win._plot_history_max_samples == 25000
    assert buf._max_samples == 25000
    
    # Verify oldest chunks were dropped to conform to new max_samples limit
    # Note: drop is chunk-based (CHUNK_SIZE = 16384).
    # Total samples 30000 = 1 frozen chunk (16384) + 1 cur chunk (13616).
    # Since 1 chunk of 16384 is less than 25000 cap, it is not dropped.
    # Let's add more chunks so it drops.
    for i in range(30000, 60000):
        buf.append(float(i), 1.0)
    
    # Total samples = 60000. Chunk size = 16384.
    # Frozen chunks = 3 (49152 samples) + current fill (10848).
    # Since 3 * 16384 = 49152 > 25000, calling set_max_samples(25000) should drop oldest chunks.
    buf.set_max_samples(25000)
    # 49152 - 16384 = 32768 (still > 25000), drop next: 32768 - 16384 = 16384 (<= 25000), stops dropping.
    # So frozen chunks remaining = 1. Total samples = 16384 + 10848 = 27232.
    assert len(buf) == 27232

    # Verify display window was updated
    assert win._plot_window_seconds == 120

    win.close()
