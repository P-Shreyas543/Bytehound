"""UI integration tests for IMP-10: Pre-Flight Hardware Sanity Handshake & Dialog."""

import os
import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.comm.packet_codec import BoardParamsTelemetry, CellDataTelemetry
from single_cell_cycler.core.preflight_checker import CheckStatus, PreflightSanityChecker
from single_cell_cycler.ui.main_window import MainWindow
from single_cell_cycler.ui.widgets.preflight_dialog import PreflightDialog


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_preflight_initial_state(qapp):
    """Verify MainWindow has preflight button initialized in offline/untested state."""
    win = MainWindow()
    assert hasattr(win, "btn_preflight")
    assert "Pre-Flight" in win.btn_preflight.text()


def test_main_window_run_preflight_nominal(qapp):
    """Verify run_preflight_check with valid telemetry updates UI button to green 4/4 Passed."""
    win = MainWindow()
    win.transceiver.isRunning = lambda: True

    # Inject mock healthy telemetry
    win._last_cell_data = CellDataTelemetry(voltage=3.680, current=0.002, terminal_temp=24.5, body_temp=24.7)
    win._last_board_params = BoardParamsTelemetry(ambient_temp=24.3, charge_voltage=0.0, load_voltage=0.0)
    win.engine.safety_monitor.last_telemetry_time = 1000.0

    # Mock time.time() age
    import time
    orig_time = time.time
    time.time = lambda: 1000.1  # 100 ms age

    try:
        report = win.run_preflight_check()
        assert report.passed is True
        assert report.failure_count == 0
        assert "4/4 Passed" in win.btn_preflight.text()
        assert "#064e3b" in win.btn_preflight.styleSheet()
    finally:
        time.time = orig_time


def test_main_window_preflight_blocks_test_on_failure(qapp):
    """Verify _start_test is halted if critical preflight check fails (e.g. 0.00V)."""
    win = MainWindow()
    win.transceiver.isRunning = lambda: True
    win.engine.safety_monitor.last_telemetry_time = 1000.0

    # Inject detached lead (0.00V)
    win._last_cell_data = CellDataTelemetry(voltage=0.010, current=0.000, terminal_temp=25.0, body_temp=25.0)

    import time
    orig_time = time.time
    time.time = lambda: 1000.1

    try:
        win._start_test()
        # Engine should NOT have started
        from single_cell_cycler.core.cycler_engine import EngineState
        assert win.engine.state == EngineState.IDLE
        assert "Failed" in win.btn_preflight.text()
    finally:
        time.time = orig_time


def test_preflight_dialog_population(qapp):
    """Verify PreflightDialog populates table rows and reflects report status."""
    checker = PreflightSanityChecker()
    cell_data = CellDataTelemetry(voltage=3.700, current=0.000, terminal_temp=25.0, body_temp=25.2)
    board_params = BoardParamsTelemetry(ambient_temp=25.0, charge_voltage=0.0, load_voltage=0.0)
    report = checker.evaluate(
        cell_data=cell_data,
        board_params=board_params,
        readbacks={},
        last_telemetry_age_s=0.1,
        cell_id=2,
    )

    dlg = PreflightDialog(report=report)
    assert dlg.table.rowCount() == 4
    assert dlg.table.item(0, 0).text() == "● PASS"
    assert dlg.table.item(1, 0).text() == "● PASS"
    assert dlg.table.item(2, 0).text() == "● PASS"
    assert dlg.table.item(3, 0).text() == "● PASS"
    assert "Cell 2" in dlg.lbl_subtitle.text()
    assert dlg.btn_proceed.isEnabled() is True
