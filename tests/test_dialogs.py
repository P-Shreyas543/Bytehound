"""Tests for dialogs."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from app.ui.dialogs import PlotTriggerDialog, PollingConfigDialog
from app.decoder.types import PollingScheduleSpec


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


def test_polling_config_dialog_modbus(qapp):
    settings = QSettings("BytehoundTest", "Test")
    settings.clear()

    # Configure some settings
    settings.setValue("poll/pipelining", True)
    settings.setValue("poll/pipeline_depth", 4)

    schedules = [
        PollingScheduleSpec(target_id=0x01, interval_ms=1000, timeout_ms=100, enabled=True)
    ]

    # Test Modbus RTU is True
    dlg_modbus = PollingConfigDialog(schedules, settings, is_modbus=True)

    # Verify pipelining controls are disabled and checked state is False
    assert not dlg_modbus._pipeline_chk.isEnabled()
    assert not dlg_modbus._pipeline_chk.isChecked()
    assert not dlg_modbus._pipeline_depth.isEnabled()
    assert dlg_modbus._pipeline_depth.value() == 1

    enabled_pipe, depth, gap = dlg_modbus.get_pipelining()
    assert enabled_pipe is False
    assert depth == 1

    # Test Modbus RTU is False
    dlg_normal = PollingConfigDialog(schedules, settings, is_modbus=False)

    # Verify pipelining controls are enabled
    assert dlg_normal._pipeline_chk.isEnabled()
    assert dlg_normal._pipeline_chk.isChecked()
    assert dlg_normal._pipeline_depth.isEnabled()
    assert dlg_normal._pipeline_depth.value() == 4

    enabled_pipe, depth, gap = dlg_normal.get_pipelining()
    assert enabled_pipe is True
    assert depth == 4

    settings.clear()
