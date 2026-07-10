"""Tests for X-Y scatter plotting and regression."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from app.ui.xy_plot import XYPlotWindow
from app.ui.log_io import LogEntry

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app

def test_xy_plot_swap_axes(qapp):
    entry = LogEntry("dummy_id", "test.csv", "Test Log", "#000")
    entry.columns = {
        "Time": np.array([0, 1, 2]),
        "Voltage": np.array([10, 11, 12]),
        "Current": np.array([1, 2, 3]),
    }

    logs = {"dummy_id": entry}
    win = XYPlotWindow(logs)

    # Select axes
    win._x_combo.setCurrentText("Voltage")
    win._y_combo.setCurrentText("Current")

    assert win._x_combo.currentText() == "Voltage"
    assert win._y_combo.currentText() == "Current"

    # Swap
    win._swap_axes()

    assert win._x_combo.currentText() == "Current"
    assert win._y_combo.currentText() == "Voltage"

def test_xy_plot_regression_no_crash_on_empty(qapp):
    entry = LogEntry("dummy_id", "test.csv", "Test Log", "#000")
    entry.columns = {
        "Voltage": np.array([]),
        "Current": np.array([]),
    }
    logs = {"dummy_id": entry}
    win = XYPlotWindow(logs)

    win._x_combo.setCurrentText("Voltage")
    win._y_combo.setCurrentText("Current")
    win._regress_cb.setChecked(True)

    win._do_plot() # Should not crash
    assert len(win._curves) == 1 # Empty scatter plot item added

def test_xy_plot_regression_valid_data(qapp):
    entry = LogEntry("dummy_id", "test.csv", "Test Log", "#000")
    entry.columns = {
        "Voltage": np.array([1, 2, 3, 4, 5]),
        "Current": np.array([2, 4, 6, 8, 10]),
    }
    logs = {"dummy_id": entry}
    win = XYPlotWindow(logs)

    win._x_combo.setCurrentText("Voltage")
    win._y_combo.setCurrentText("Current")
    win._regress_cb.setChecked(True)

    win._do_plot()
    # 1 scatter + 1 regression line
    assert len(win._curves) == 2


def test_xy_plot_min_max_markers(qapp):
    entry = LogEntry("dummy_id", "test.csv", "Test Log", "#000")
    entry.columns = {
        "Voltage": np.array([10, 20, 30, 40, 50]),
        "Current": np.array([1, 5, 2, 8, 3]),
    }
    logs = {"dummy_id": entry}
    win = XYPlotWindow(logs)

    win._x_combo.setCurrentText("Voltage")
    win._y_combo.setCurrentText("Current")

    # Enable Min and Max markers
    win._show_min_cb.setChecked(True)
    win._show_max_cb.setChecked(True)

    win._do_plot()

    # 1 scatter + 2 min items (Min X, Min Y same point) + 4 max items (Max X, Max Y distinct points)
    assert len(win._curves) == 7
