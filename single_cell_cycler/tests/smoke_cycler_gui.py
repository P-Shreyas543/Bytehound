"""Headless smoke test for Single-Cell Cycler GUI."""

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Headless platform offscreen flag for CI / non-display testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from single_cell_cycler.comm.packet_codec import (
    BoardParamsTelemetry,
    CellDataTelemetry,
    FaultSoCTelemetry,
)
from single_cell_cycler.ui.main_window import MainWindow


def test_gui_headless():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    # Mock running transceiver status for test
    window.transceiver.isRunning = lambda: True

    # Emit telemetry to simulate incoming hardware frames
    window.transceiver.cell_data_received.emit(CellDataTelemetry(3.850, 1.250, 26.5, 27.0))
    window.transceiver.board_params_received.emit(BoardParamsTelemetry(25.0, 4.20, 0.0))
    window.transceiver.fault_soc_received.emit(
        FaultSoCTelemetry(0x00, False, False, False, False, False, False, 65.0, 65.0)
    )

    app.processEvents()

    # Check dashboard cards received valid values
    v_text = window.dashboard.card_voltage.lbl_value.text()
    assert v_text != "--", f"Voltage card not populated: {v_text}"
    v_val = float(v_text)
    assert 2.5 <= v_val <= 4.3, f"Voltage out of expected range: {v_val}"

    # Verify initial unified Start/Stop button state
    assert "START" in window.btn_start_stop.text(), f"Expected START button text, got: {window.btn_start_stop.text()}"
    assert window.btn_start_stop.objectName() == "btn_start"
    assert not window.btn_pause.isEnabled()
    assert not window.btn_skip.isEnabled()

    # Start test
    window._start_test()
    from single_cell_cycler.core.cycler_engine import EngineState
    assert window.engine.state in (EngineState.STEP_TRANSITION, EngineState.RUNNING)

    # Verify button toggles to STOP TEST (crimson style)
    assert "STOP" in window.btn_start_stop.text(), f"Expected STOP button text, got: {window.btn_start_stop.text()}"
    assert window.btn_start_stop.objectName() == "btn_stop"
    assert window.btn_pause.isEnabled()
    assert window.btn_skip.isEnabled()

    # Push a running telemetry packet and trigger UI tick
    window._on_ui_tick()
    window.transceiver.cell_data_received.emit(CellDataTelemetry(3.860, 1.250, 26.6, 27.1))
    window._on_ui_tick()
    app.processEvents()

    # Verify live plot buffers have received the data
    assert len(window.live_plots._v) > 0, "No voltage points plotted"
    assert len(window.live_plots._i) > 0, "No current points plotted"

    # Test toggling Start/Stop button directly to stop
    window.btn_start_stop.click()
    app.processEvents()
    assert "START" in window.btn_start_stop.text()
    assert window.btn_start_stop.objectName() == "btn_start"

    # Test cell selection update
    window.combo_active_cell.setCurrentIndex(1)  # Cell 2
    app.processEvents()
    assert "Cell 2" in window.windowTitle()

    # Test font scaling
    window.combo_font.setCurrentIndex(2)  # 12 pt
    app.processEvents()

    # Emergency stop safety check
    window._start_test()
    window._emergency_stop()
    assert window.engine.state.value == "Safety Stop"
    assert "START" in window.btn_start_stop.text()

    # Clean close
    window.close()
    app.processEvents()
    print("Headless GUI Smoke Test Passed Successfully!")


if __name__ == "__main__":
    test_gui_headless()

