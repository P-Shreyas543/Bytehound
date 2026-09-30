"""Automated test suite for LivePlotWidget Differential Capacity Tab (IMP-05)."""

import os
import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from single_cell_cycler.comm.packet_codec import CellDataTelemetry
from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dqv_tab_existence_and_structure(qapp):
    widget = LivePlotWidget()
    assert widget.tabs.count() >= 4
    tab_names = [widget.tabs.tabText(i) for i in range(widget.tabs.count())]
    assert any("dQ/dV" in name for name in tab_names)
    assert hasattr(widget, "plot_dqv")
    assert hasattr(widget, "curve_dqv_active")
    assert hasattr(widget, "scatter_dqv_peaks")
    assert hasattr(widget, "crosshair_v_dqv")
    assert hasattr(widget, "lbl_hud_dqv")


def test_dqv_live_stream_and_archival(qapp):
    widget = LivePlotWidget()
    widget.set_relay_state(True, cell_num=1)
    widget.notify_step_started(cycle_idx=1, step_idx=1, step_type="Charge")

    # Generate synthetic NMC charge curve (3.0V -> 4.2V, 2000 mAh)
    n_pts = 100
    for idx in range(n_pts):
        frac = idx / float(n_pts)
        volt = 3.0 + 1.2 * frac + 0.1 * np.sin(frac * np.pi)
        cap = frac * 2000.0
        telem = CellDataTelemetry(
            voltage=round(float(volt), 3),
            current=1.5,
            terminal_temp=25.0,
            body_temp=25.5,
            timestamp=float(idx),
        )
        widget.add_telemetry(telem, step_mah=cap)

    # Check active buffers populated
    assert len(widget._dqv_v_buf) == n_pts
    assert len(widget._dqv_q_buf) == n_pts

    # Switch to dQ/dV tab
    widget.tabs.setCurrentIndex(3)
    widget._render_tab(3, force=True)

    # Verify active curve received data
    v_data, y_data = widget.curve_dqv_active.getData()
    assert v_data is not None and len(v_data) > 0
    assert y_data is not None and len(y_data) == len(v_data)

    # Step finishes: call reset_step_vq() to archive
    widget.reset_step_vq()
    assert len(widget._dqv_profiles) == 1
    assert len(widget._dqv_history_curves) == 1
    assert len(widget._dqv_v_buf) == 0

    # Start next step (Discharge)
    widget.notify_step_started(cycle_idx=1, step_idx=2, step_type="Discharge")
    for idx in range(n_pts):
        frac = idx / float(n_pts)
        volt = 4.2 - 1.2 * frac
        cap = frac * 1950.0
        telem = CellDataTelemetry(
            voltage=round(float(volt), 3),
            current=-1.5,
            terminal_temp=26.0,
            body_temp=26.5,
            timestamp=float(100 + idx),
        )
        widget.add_telemetry(telem, step_mah=cap)

    widget.reset_step_vq()
    assert len(widget._dqv_profiles) == 2
    assert len(widget._dqv_history_curves) == 2


def test_dqv_mode_and_smoothing_toggles(qapp):
    widget = LivePlotWidget()
    widget.set_relay_state(True, cell_num=1)
    widget.notify_step_started(cycle_idx=1, step_idx=1, step_type="Charge")

    # Add mock data
    for i in range(50):
        v = 3.2 + (i / 50.0) * 0.8
        q = i * 20.0
        widget.add_telemetry(CellDataTelemetry(voltage=v, current=1.0, terminal_temp=25.0, body_temp=25.0, timestamp=float(i)), step_mah=q)

    widget.reset_step_vq()
    assert len(widget._dqv_history_curves) == 1

    # Toggle to Absolute mode
    widget.set_dqv_mode(False)
    assert widget._dqv_butterfly is False

    # Toggle smoothing to 10 mV
    widget.set_dqv_smoothing(dv=0.010, window=17)
    assert widget._dqv_dv == 0.010
    assert widget._dqv_window == 17

    # Toggle back to Butterfly
    widget.set_dqv_mode(True)
    assert widget._dqv_butterfly is True


def test_dqv_hover_and_reset(qapp):
    widget = LivePlotWidget()
    widget.set_relay_state(True, cell_num=1)
    widget.notify_step_started(cycle_idx=1, step_idx=1, step_type="Charge")

    for i in range(30):
        v = 3.0 + (i / 30.0) * 1.0
        q = i * 15.0
        widget.add_telemetry(CellDataTelemetry(voltage=v, current=1.0, terminal_temp=25.0, body_temp=25.0, timestamp=float(i)), step_mah=q)

    widget.tabs.setCurrentIndex(3)
    widget._render_tab(3, force=True)

    # Simulate mouse moved inside scene
    rect = widget.plot_dqv.plotItem.sceneBoundingRect()
    center_pt = rect.center()
    widget._on_mouse_moved_dqv(center_pt)
    assert widget.crosshair_v_dqv.isVisible()
    assert "V" in widget.lbl_hud_dqv.text()

    # Reset all
    widget.reset_all()
    assert len(widget._dqv_profiles) == 0
    assert len(widget._dqv_history_curves) == 0
    assert not widget.crosshair_v_dqv.isVisible()


def test_dqv_history_retention_across_step_transitions_and_rest(qapp):
    """Verify that dQ/dV curves and peak markers do not vanish when steps end or transition to Rest."""
    widget = LivePlotWidget()
    widget.set_relay_state(True, cell_num=1)

    # 1. Run Step 1: Charge
    widget.notify_step_started(cycle_idx=1, step_idx=1, step_type="Charge")
    for i in range(40):
        frac = i / 40.0
        v = 3.2 + 0.8 * frac + 0.05 * np.sin(frac * np.pi)
        q = frac * 2000.0
        widget.add_telemetry(
            CellDataTelemetry(voltage=v, current=1.5, terminal_temp=25.0, body_temp=25.5, timestamp=float(i)),
            step_mah=q,
        )

    # 2. Step 1 completes and transitions to Step 2 (Rest)
    # This reproduces the exact sequence from MainWindow
    widget.reset_step_vq(step_type="Charge", cycle_idx=1, step_idx=1)
    widget.notify_step_started(cycle_idx=1, step_idx=2, step_type="Rest")

    # Historical curve MUST be archived and visible on plot_dqv
    assert len(widget._dqv_profiles) == 1, "Charge dQ/dV profile must be stored in history"
    assert len(widget._dqv_history_curves) == 1, "Charge dQ/dV historical curve item must exist"

    # Switch to dQ/dV tab during Rest
    widget.tabs.setCurrentIndex(3)
    widget._render_tab(3, force=True)

    # Historical curve on plot_dqv must have data
    hist_prof, hist_item = widget._dqv_history_curves[0]
    hist_x, hist_y = hist_item.getData()
    assert len(hist_x) > 0, "Historical dQ/dV curve data must NOT be empty during Rest"
    assert "historical profile" in widget.lbl_dqv_context.text()

    # Peak markers must remain visible
    if hist_prof.peaks:
        assert len(widget._latest_dqv_peaks) == len(hist_prof.peaks)
        assert len(widget.scatter_dqv_peaks.data) > 0, "Peaks must NOT vanish during Rest"

    # 3. Rest step runs (should not produce dQ/dV or overwrite history)
    for i in range(20):
        widget.add_telemetry(
            CellDataTelemetry(voltage=4.15, current=0.0, terminal_temp=25.0, body_temp=25.0, timestamp=float(40 + i)),
            step_mah=0.0,
        )
    widget.reset_step_vq(step_type="Rest", cycle_idx=1, step_idx=2)
    assert len(widget._dqv_profiles) == 1, "Rest step must not add fake dQ/dV profile"

    # 4. Step 3: Discharge
    widget.notify_step_started(cycle_idx=1, step_idx=3, step_type="Discharge")
    for i in range(40):
        frac = i / 40.0
        v = 4.15 - 0.8 * frac
        q = frac * 1950.0
        widget.add_telemetry(
            CellDataTelemetry(voltage=v, current=-1.5, terminal_temp=26.0, body_temp=26.0, timestamp=float(60 + i)),
            step_mah=q,
        )

    widget.reset_step_vq(step_type="Discharge", cycle_idx=1, step_idx=3)

    # Both Charge and Discharge must be preserved in history
    assert len(widget._dqv_profiles) == 2, "Both Charge and Discharge profiles must be retained"
    assert len(widget._dqv_history_curves) == 2, "Both historical curves must be present on plot"

