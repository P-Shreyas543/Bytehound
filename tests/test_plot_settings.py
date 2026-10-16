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

    # Initial dialog state: default budget, 5-minute window
    dlg = PlotSettingsDialog(settings)
    assert dlg._budget_spin.value() == 512
    assert dlg._window_combo.currentIndex() == 3  # default 5 minutes (300s)

    # Change settings
    dlg._budget_spin.setValue(1024)
    dlg._window_combo.setCurrentIndex(1)  # 1 minute (60s)
    dlg._on_accept()

    # Verify QSettings saved correctly
    assert int(settings.value("plot/history_budget_mb")) == 1024
    assert int(settings.value("plot/window_seconds")) == 60

    budget, win_s = dlg.get_values()
    assert budget == 1024
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
            return 64, 120  # budget = 64 MB, window = 120s

    monkeypatch.setattr("app.ui.dialogs.PlotSettingsDialog", MockPlotSettingsDialog)

    win = MainWindow()

    # Two signals with long, uncapped histories.
    bufs = {}
    for key in [(1, "A"), (1, "B")]:
        buf = TimeSeriesBuffer(max_samples=None)
        for i in range(2_000_000):
            buf.append(float(i), 1.0)
        win._plot_history[key] = buf
        bufs[key] = buf

    win._on_plot_settings()

    # 64 MB shared by 2 signals → each capped so both fit, trimmed at once.
    cap = win._plot_history_max_samples
    assert win._plot_history_budget_mb == 64
    assert cap == win._history_cap_per_signal(2)
    for buf in bufs.values():
        assert buf._max_samples == cap
        assert len(buf) == cap
        assert buf.last_x() == 1_999_999.0
    total = sum(TimeSeriesBuffer.bytes_for(b._max_samples) for b in bufs.values())
    assert total <= 64 * 1_000_000

    # A third signal lowers everyone's share.
    win._plot_history[(1, "C")].append(0.0, 0.0)
    assert win._plot_history_max_samples == win._history_cap_per_signal(3) < cap
    assert all(len(b) <= win._plot_history_max_samples for b in bufs.values())

    # Verify display window was updated
    assert win._plot_window_seconds == 120

    win.close()

def test_mainwindow_plot_color_customization(qapp, monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    class MockSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__("BytehoundTestOrg", "BytehoundTestApp")
            self.clear()

    monkeypatch.setattr("app.ui.main_window.QSettings", MockSettings)
    monkeypatch.setattr("app.ui.main_window.ConnectionDialog", lambda *args, **kwargs: None)

    # Mock QColorDialog.getColor to return QColor("#ff00ff") (magenta)
    monkeypatch.setattr(QColorDialog, "getColor", lambda *args, **kwargs: QColor("#ff00ff"))

    win = MainWindow()

    # Assign a mock config with a signal
    class MockSignal:
        frame_id = 0x1000
        signal_name = "Battery_Voltage"

    class MockConfig:
        all_signals = [MockSignal()]

    win._config = MockConfig()
    from app.ui.plot_panel import TimeSeriesBuffer
    win._plot_history[(0x1000, "Battery_Voltage")] = TimeSeriesBuffer(max_samples=None)
    monkeypatch.setattr(win._plot_dock, "isVisible", lambda: True)
    for panel in win._plot_panels:
        monkeypatch.setattr(panel.plot_item, "isVisible", lambda: True)

    win._add_signal_to_panel(0, (0x1000, "Battery_Voltage"))

    # Check that it initially gets the default palette color
    palette = win._current_plot_palette()
    assert len(palette) > 0
    assert win._settings.value("plot/colors/Battery_Voltage") is None

    # Build menu and trigger select_color on the menu row
    from PySide6.QtWidgets import QMenu
    dummy_menu = QMenu()
    row = win._build_panel_signal_menu_row(0, (0x1000, "Battery_Voltage"), "#ffffff", dummy_menu)

    # Trigger click on the dot QToolButton
    dot_btn = None
    for child in row.children():
        from PySide6.QtWidgets import QToolButton
        if isinstance(child, QToolButton) and child.text() == "●":
            dot_btn = child
            break

    assert dot_btn is not None
    dot_btn.click() # triggers select_color()

    # Check that custom color was saved in settings
    assert win._settings.value("plot/colors/Battery_Voltage") == "#ff00ff"

    # Verify redraw uses the custom color for curves
    panel = win._plot_panels[0]
    win._redraw_plot()

    curve = panel.curves[(0x1000, "Battery_Voltage")]
    assert curve._bh_color == "#ff00ff"

    win.close()


def test_mainwindow_add_calculated_signal_to_plot(qapp, monkeypatch):
    class MockSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__("BytehoundTestOrg", "BytehoundTestApp")
            self.clear()

    monkeypatch.setattr("app.ui.main_window.QSettings", MockSettings)
    monkeypatch.setattr("app.ui.main_window.ConnectionDialog", lambda *args, **kwargs: None)

    win = MainWindow()

    # Assign a mock config
    class MockConfig:
        all_signals = []

    win._config = MockConfig()
    from app.ui.plot_panel import TimeSeriesBuffer
    calc_key = ("calc", "Cell Voltages max")
    win._plot_history[calc_key] = TimeSeriesBuffer(max_samples=None)
    monkeypatch.setattr(win._plot_dock, "isVisible", lambda: True)
    for panel in win._plot_panels:
        monkeypatch.setattr(panel.plot_item, "isVisible", lambda: True)

    # Adding calculated signal should not throw ValueError
    win._add_signal_to_panel(0, calc_key)

    # Redrawing plot with calculated signal should not throw ValueError
    win._redraw_plot()

    # Building menu row with calculated signal should not throw ValueError
    from PySide6.QtWidgets import QMenu
    dummy_menu = QMenu()
    row = win._build_panel_signal_menu_row(0, calc_key, "#ffffff", dummy_menu)
    assert row is not None

    # Verify label / names are formatted with str(calc_key[0]) instead of hex
    panel = win._plot_panels[0]
    curve = panel.curves[calc_key]
    assert curve.name() == "calc Cell Voltages max"

    # Removing calculated signal should not throw ValueError
    win._remove_signal_from_panel(0, calc_key)

    win.close()

