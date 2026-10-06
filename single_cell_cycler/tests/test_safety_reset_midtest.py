"""A stale safety-trip banner must never be able to knock a running test into Idle.

Field report (Oct 2026): mid-discharge the GUI showed "Idle" while the load stayed on;
step/total capacity froze, so cut-offs and most safety trips were no longer evaluated.
Path: a step-setup failure tripped the panel without latching the interlock, the next
test started anyway, and pressing the still-enabled Reset forced the engine to Idle.
"""

import os

import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.core.cycler_engine import EngineState
from single_cell_cycler.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


def _start_and_reach_running(window: MainWindow) -> None:
    engine = window.engine
    engine.start_test()
    window._set_test_running_ui(True)
    # Offline the controller auto-acknowledges its writes, so setup may already be done
    if engine.state == EngineState.STEP_TRANSITION:
        engine._on_transition_completed(engine.active_step)
    assert engine.state == EngineState.RUNNING


def test_step_setup_failure_latches_interlock(qapp):
    window = MainWindow()
    try:
        _start_and_reach_running(window)
        window.engine._on_transition_failed("0x6004 readback not confirmed")

        assert window.engine.state == EngineState.SAFETY_STOP
        assert window.safety_panel.btn_reset.isEnabled()
        # The trip must block the next START until the operator resets it
        assert window.engine.safety_monitor.is_tripped
        window._update_start_gate()
        assert "reset the safety interlock" in window.btn_start_stop.toolTip()
    finally:
        window.close()


def test_reset_button_cannot_idle_a_running_test(qapp):
    window = MainWindow()
    try:
        _start_and_reach_running(window)
        window.engine._on_transition_failed("0x6004 readback not confirmed")
        window.safety_panel.btn_reset.click()           # operator clears the trip
        assert window.engine.state == EngineState.IDLE

        _start_and_reach_running(window)
        assert not window.safety_panel.btn_reset.isEnabled()

        # Even if the reset handler is reached while a test owns the hardware, it must not
        # change the engine state
        window._on_reset_safety()
        assert window.engine.state == EngineState.RUNNING
    finally:
        window.close()


def test_new_test_clears_stale_trip_banner(qapp):
    window = MainWindow()
    try:
        window.safety_panel.set_tripped("old trip from a previous run")
        window.engine.safety_monitor.reset_safety()      # interlock cleared some other way
        _start_and_reach_running(window)
        assert not window.safety_panel.btn_reset.isEnabled()
        assert "NOMINAL" in window.safety_panel.lbl_trip_status.text()
    finally:
        window.close()
