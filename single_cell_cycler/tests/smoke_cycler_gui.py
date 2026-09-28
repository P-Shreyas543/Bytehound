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

    # Verify live plot has data points
    assert len(window.live_plots.voltages) > 0, "No voltage points plotted"

    # Start test
    window._start_test()
    assert window.engine.state.value == "Running"

    # Push a running telemetry packet
    window.transceiver.cell_data_received.emit(CellDataTelemetry(3.860, 1.250, 26.6, 27.1))
    app.processEvents()

    # Emergency stop
    window._emergency_stop()
    assert window.engine.state.value == "Safety Stop"

    # Clean close
    window.close()
    app.processEvents()
    print("Headless GUI Smoke Test Passed Successfully!")


if __name__ == "__main__":
    test_gui_headless()
