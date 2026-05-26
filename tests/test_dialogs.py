"""Tests for dialogs."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from app.ui.dialogs import PlotTriggerDialog

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app

def test_plot_trigger_dialog(qapp):
    dlg = PlotTriggerDialog(["Voltage", "Current"])
    
    # Test setting values
    dlg._param_combo.setCurrentText("Voltage")
    dlg._op_combo.setCurrentText(">")
    dlg._val_spin.setValue(12.5)
    
    dlg._action_pause.setChecked(True)
    dlg._action_log.setChecked(False)
    
    res = dlg.get_trigger()
    assert res["param"] == "Voltage"
    assert res["op"] == ">"
    assert res["value"] == 12.5
    assert res["pause"] is True
    assert res["log"] is False
