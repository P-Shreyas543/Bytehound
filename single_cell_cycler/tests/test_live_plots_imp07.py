"""Integration and unit tests for IMP-07: Tab 5 Cycle Aging & Health tracking in LivePlotWidget."""

import os
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_aging_tab_initialization(qapp):
    widget = LivePlotWidget()
    assert widget.tabs.count() == 5
    assert "Cycle Aging" in widget.tabs.tabText(4)
    assert hasattr(widget, "plot_aging_cap")
    assert hasattr(widget, "plot_aging_eff")
    assert hasattr(widget, "view_aging_dcir")
    assert hasattr(widget, "curve_aging_q_dis")
    assert hasattr(widget, "curve_aging_q_chg")
    assert hasattr(widget, "curve_aging_q_proj")
    assert hasattr(widget, "curve_aging_ce")
    assert hasattr(widget, "curve_aging_ee")
    assert hasattr(widget, "curve_aging_dcir")
    assert hasattr(widget, "line_aging_eol")


def test_aging_tab_data_ingestion_and_forecasting(qapp):
    widget = LivePlotWidget()

    # Ingest 5 cycles of realistic capacity fade (-5 mAh/cycle)
    cycles_data = [
        (1, 2500.0, 99.5, 2512.0, 93.2, 14.8),
        (2, 2495.0, 99.6, 2505.0, 93.4, 14.9),
        (3, 2490.0, 99.65, 2498.0, 93.5, 15.0),
        (4, 2485.0, 99.7, 2492.0, 93.6, 15.1),
        (5, 2480.0, 99.75, 2486.0, 93.7, 15.2),
    ]

    for c_idx, q_dis, ce, q_chg, ee, dcir in cycles_data:
        widget.add_cycle_summary(
            c_idx,
            q_dis,
            ce,
            charge_mah=q_chg,
            energy_eff=ee,
            dcir_mohm=dcir,
        )

    # Verify buffers
    assert len(widget._cycle_indices) == 5
    assert len(widget._cycle_q_dis) == 5
    assert len(widget._cycle_dcir) == 5

    # Verify curve data
    c_x, q_y = widget.curve_aging_q_dis.getData()
    assert list(c_x) == [1, 2, 3, 4, 5]
    assert list(q_y) == [2500.0, 2495.0, 2490.0, 2485.0, 2480.0]

    # Verify 80% EOL line (2500 * 0.8 = 2000)
    assert widget.line_aging_eol.isVisible()
    assert abs(widget.line_aging_eol.value() - 2000.0) < 1e-3

    # Verify projected EOL cycle: 2500 - 5 * n = 2000 => n = 100 cycles
    proj_x, proj_y = widget.curve_aging_q_proj.getData()
    assert len(proj_x) > 5
    assert "Cycle 101" in widget.lbl_aging_health_badge.text() or "Cycle 100" in widget.lbl_aging_health_badge.text()
    assert "Fade: -5.00 mAh/cyc" in widget.lbl_aging_fade_badge.text()

    # Verify efficiency and DCIR curves
    _, ce_y = widget.curve_aging_ce.getData()
    assert len(ce_y) == 5
    assert abs(ce_y[-1] - 99.75) < 1e-2

    _, dcir_y = widget.curve_aging_dcir.getData()
    assert len(dcir_y) == 5
    assert abs(dcir_y[-1] - 15.2) < 1e-2


def test_aging_tab_model_switch_and_fit(qapp):
    widget = LivePlotWidget()
    for c in range(1, 6):
        widget.add_cycle_summary(c, 2500.0 - (c - 1) * 2.0, 99.5, 2510.0, 93.0, 15.0)

    # Switch to exponential model
    widget.set_aging_model("exponential")
    assert widget._aging_model == "exponential"
    assert widget.curve_aging_q_proj.getData()[0] is not None

    # Switch back to linear
    widget.set_aging_model("linear")
    assert widget._aging_model == "linear"

    # Fit view does not throw
    widget.fit_aging_view()


def test_aging_tab_reset_all(qapp):
    widget = LivePlotWidget()
    widget.add_cycle_summary(1, 2500.0, 99.5, 2510.0, 93.0, 15.0)
    assert len(widget._cycle_indices) == 1

    widget.reset_all()
    assert len(widget._cycle_indices) == 0
    assert len(widget._cycle_q_dis) == 0
    assert len(widget._cycle_dcir) == 0
    assert not widget.line_aging_eol.isVisible()


def test_vq_curve_rest_exclusion_and_charge_discharge_styling(qapp):
    from single_cell_cycler.comm.packet_codec import CellDataTelemetry
    widget = LivePlotWidget()
    widget.set_relay_state(True, cell_num=1)

    # 1. Rest Step: must be ignored by V-Q buffers
    widget.notify_step_started(cycle_idx=1, step_idx=1, step_type="Rest")
    for sec in range(20):
        widget.add_telemetry(CellDataTelemetry(voltage=3.85, current=0.0, terminal_temp=25.0, body_temp=25.0, timestamp=float(sec)), step_mah=0.0)
    assert len(widget._vq_cap) == 0
    assert len(widget._vq_volt) == 0
    widget.reset_step_vq()
    assert len(widget._vq_history_curves) == 0  # No vertical line archived!

    # 2. Charge Step: populated and styled as Charge
    widget.notify_step_started(cycle_idx=1, step_idx=2, step_type="Charge")
    for sec in range(30):
        widget.add_telemetry(CellDataTelemetry(voltage=3.0 + sec * 0.04, current=1.5, terminal_temp=25.0, body_temp=25.0, timestamp=float(20 + sec)), step_mah=sec * 30.0)
    assert len(widget._vq_cap) == 30
    widget.tabs.setCurrentIndex(2)
    widget._render_tab(2, force=True)
    assert widget.curve_vq_current.isVisible()

    widget.reset_step_vq()
    assert len(widget._vq_history_curves) == 1
    assert len(widget._vq_cap) == 0

    # 3. Discharge Step: populated and styled as Discharge
    widget.notify_step_started(cycle_idx=1, step_idx=3, step_type="Discharge")
    for sec in range(30):
        widget.add_telemetry(CellDataTelemetry(voltage=4.2 - sec * 0.04, current=-1.5, terminal_temp=25.0, body_temp=25.0, timestamp=float(50 + sec)), step_mah=sec * 30.0)
    widget.reset_step_vq()
    assert len(widget._vq_history_curves) == 2

    # Auto-fit V-Q view does not crash and properly bounds window
    widget.fit_vq_view()
    y_range = widget.plot_vq.viewRange()[1]
    assert y_range[0] >= 0.0
    assert y_range[1] <= 6.0

    # 4. Clear History
    widget.clear_chart_history()
    assert len(widget._vq_history_curves) == 0


def test_aging_tab_outlier_efficiency_and_single_dcir_framing(qapp):
    widget = LivePlotWidget()

    # Cycle 1: unconditioned with CE = 260.4% (charge 969 mAh, discharge 2523 mAh) and DCIR = 56.01 mOhm
    widget.add_cycle_summary(1, discharge_mah=2523.87, coulombic_eff=260.4, charge_mah=969.22, energy_eff=231.34, dcir_mohm=56.01)
    # Cycle 2: normal CE = 99.98% and no DCIR measurement
    widget.add_cycle_summary(2, discharge_mah=2522.35, coulombic_eff=99.98, charge_mah=2522.97, energy_eff=94.72, dcir_mohm=None)

    widget.fit_aging_view()

    # 1. Efficiency Y range must adapt and not clip 260.4%
    eff_y_range = widget.plot_aging_eff.viewRange()[1]
    assert eff_y_range[1] >= 260.0, f"Expected Y-max >= 260.0, got {eff_y_range[1]}"

    # 2. DCIR ViewBox must handle 1 data point without zero-range failure
    dcir_y_range = widget.view_aging_dcir.viewRange()[1]
    assert dcir_y_range[1] > dcir_y_range[0], "DCIR Y range must have positive span"
    assert dcir_y_range[0] <= 56.01 <= dcir_y_range[1]

    # 3. Capacity plot must frame around ~2000-2600 mAh, not 0 to 50,000
    cap_y_range = widget.plot_aging_cap.viewRange()[1]
    assert cap_y_range[0] >= 1800.0, f"Expected capacity Y-min around ~1900-2000, got {cap_y_range[0]}"
    assert cap_y_range[1] <= 2800.0, f"Expected capacity Y-max around ~2600-2700, got {cap_y_range[1]}"

