"""Regression tests for issues found in the October 2026 field screenshots."""

import os
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    w = MainWindow()
    yield w
    w.close()


def test_fallback_bms_identity_includes_port_when_adapter_serials_match(window, monkeypatch):
    # Both benches' CP210x adapters report serial "0001"
    ports = [SimpleNamespace(device="COM3", serial_number="0001", description="CP210x"),
             SimpleNamespace(device="COM9", serial_number="0001", description="CP210x")]
    monkeypatch.setattr("serial.tools.list_ports.comports", lambda: ports)
    window.webhook_notifier.settings.bms_serial_number = ""

    window._set_bms_identity_from_port("COM3")
    first = window.lbl_bms_identity.text()
    window._set_bms_identity_from_port("COM9")
    second = window.lbl_bms_identity.text()

    assert first != second
    assert "COM3" in first and "0001" in first
    # The fallback is session-only: never stored as the configured BMS serial
    assert window.webhook_notifier.settings.bms_serial_number == ""
    assert "COM9" in window.webhook_notifier._bms_identity()

    window.webhook_notifier.settings.bms_serial_number = "BMS-0042"
    window._set_bms_identity_from_port("COM9")
    assert window.webhook_notifier._bms_identity() == "BMS-0042"


def test_second_instance_on_same_pc_is_refused(qapp, tmp_path):
    from single_cell_cycler.main import acquire_single_instance_lock

    first = acquire_single_instance_lock(tmp_path)
    assert first is not None
    assert acquire_single_instance_lock(tmp_path) is None     # same PC, same lock folder
    first.unlock()
    again = acquire_single_instance_lock(tmp_path)
    assert again is not None                                  # free again once the first exits
    again.unlock()


def test_aging_partial_cycle_does_not_stretch_efficiency_axis_and_no_fake_eol(qapp):
    from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget

    plots = LivePlotWidget()
    # Screenshot 5: cycle 1 partial (676 mAh charged) -> CE 370 %, EE 330 %
    plots.add_cycle_summary(1, 2505.9, 370.4, charge_mah=676.5, energy_eff=325.8, dcir_mohm=60.1, partial=True)
    plots.add_cycle_summary(2, 2510.0, 99.0, charge_mah=2536.1, energy_eff=93.9, dcir_mohm=59.2)
    plots.add_cycle_summary(3, 2510.8, 99.0, charge_mah=2537.1, energy_eff=93.8, dcir_mohm=59.3)

    lo, hi = plots.plot_aging_eff.viewRange()[1]
    assert hi < 110.0                                   # was ~355 %
    _, ys = plots.scatter_aging_partial_eff.getData()
    assert max(ys) <= hi                                # partial markers pinned inside the view
    assert any("CE 370%" in lbl.toPlainText() for lbl in plots._partial_labels)

    assert "no fade detected" in plots.lbl_aging_health_badge.text()
    assert "> 3,000" not in plots.lbl_aging_health_badge.text()
    assert "none detected" in plots.lbl_aging_fade_badge.text()


def test_cycle_dcir_prefers_the_discharge_step():
    from single_cell_cycler.core.metrics_tracker import MetricsTracker, StepMetrics
    from single_cell_cycler.core.profile_model import StepType

    mt = MetricsTracker()
    mt.step_history = [
        StepMetrics(cycle_index=1, step_index=1, step_name="Charge", step_type=StepType.CHARGE, start_time=0.0, dcir_10s_mohm=91.2),
        StepMetrics(cycle_index=1, step_index=3, step_name="Discharge", step_type=StepType.DISCHARGE, start_time=0.0, dcir_10s_mohm=59.2),
    ]
    assert mt.compute_cycle_summary(1).dcir_10s_mohm == 59.2


def test_dqv_readout_follows_the_cursor_not_the_live_curve_end(qapp):
    import numpy as np
    from PySide6.QtCore import QPointF
    from single_cell_cycler.core.dqv_analysis import DQVProfile
    from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget

    plots = LivePlotWidget()
    plots.resize(1200, 700)
    plots.show()
    plots.tabs.setCurrentIndex(3)
    qapp.processEvents()

    # Finished cycle-3 discharge covering 2.8-4.17 V; live cycle-4 discharge only down to 3.575 V
    v_hist = np.linspace(2.8, 4.17, 275)
    plots._plot_historical_dqv(DQVProfile(cycle_index=3, step_index=3, step_type="discharge",
                                          voltages=v_hist, dq_dv=-1000.0 - 0 * v_hist, peaks=[]))
    v_live = np.linspace(3.575, 4.17, 120)
    plots.curve_dqv_active.setData(v_live, -2000.0 + 0 * v_live)
    plots._current_step_type = "discharge"
    plots.plot_dqv.setXRange(2.5, 4.3, padding=0.0)
    plots.plot_dqv.setYRange(-5000, 5000, padding=0.0)
    qapp.processEvents()

    scene_pos = plots.plot_dqv.plotItem.vb.mapViewToScene(QPointF(3.22, 0.0))
    plots._on_mouse_moved_dqv(scene_pos)
    text = plots.lbl_hud_dqv.text()
    assert "3.575" not in text
    assert "3.22" in text and "C3" in text and "-1000.0" in text
    plots.close()


def test_dqv_live_edge_hook_is_not_reported_as_a_peak(qapp):
    import numpy as np
    from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget

    plots = LivePlotWidget()
    plots._current_step_type = "discharge"
    plots._current_cycle_idx = 4
    # Discharge in progress: 4.17 V down to 3.575 V, with a real feature at 4.00 V
    v = np.linspace(4.17, 3.575, 1200)
    q = np.cumsum(np.full_like(v, 1.2)) + 400.0 * np.exp(-((v - 4.0) / 0.02) ** 2).cumsum() / 100.0
    for vi, qi in zip(v, q):
        plots._dqv_v_buf.append(vi)
        plots._dqv_q_buf.append(qi)
    plots._render_dqv_active()
    volts = [p.voltage for p in plots._latest_dqv_peaks]
    assert all(abs(v - 3.575) > plots._dqv_window * plots._dqv_dv for v in volts)
    assert not any(abs(v - 3.612) < 0.005 for v in volts)     # the unfiltered finder reports 3.612 V
    assert any(abs(v - 4.0) < 0.01 for v in volts)            # the real feature is kept


def test_ocv_soc_flagged_under_load(qapp):
    from single_cell_cycler.comm.packet_codec import CellDataTelemetry, FaultSoCTelemetry
    from single_cell_cycler.ui.widgets.kpi_dashboard import KPIDashboard

    dash = KPIDashboard()
    soc = FaultSoCTelemetry(fault_byte=0, cov=False, cuv=False, occ=False, ocd=False, cot=False, cut=False,
                            soc_ocv=23.5, soc_cc=41.9, soc_ekf=43.3, extended=True)
    dash.update_cell_data(CellDataTelemetry(voltage=3.565, current=-1.151, terminal_temp=28.4, body_temp=28.4))
    dash.update_fault_soc(soc)
    assert "under load" in dash.card_soc.lbl_sub.text()
    dash.update_cell_data(CellDataTelemetry(voltage=3.9, current=0.0, terminal_temp=28.4, body_temp=28.4))
    dash.update_fault_soc(soc)
    assert "under load" not in dash.card_soc.lbl_sub.text()


def test_current_zero_offset_at_rest_is_reported_once(window):
    from single_cell_cycler.comm.packet_codec import CellDataTelemetry

    window._last_cell_data = CellDataTelemetry(voltage=4.18, current=0.015, terminal_temp=28.0, body_temp=28.0)
    window._report_current_zero_offset("Rest")
    window._report_current_zero_offset("Rest")
    offsets = [m for _, _, m in window._event_records if "zero offset" in m]
    assert len(offsets) == 1 and "+0.015 A" in offsets[0]

    window._zero_offset_reported = False
    window._report_current_zero_offset("Discharge")          # only rests (cell disconnected) count
    assert len([m for _, _, m in window._event_records if "zero offset" in m]) == 1


def test_vi_chart_uses_compact_axes_for_li_ion_and_full_for_low_voltage(qapp):
    import numpy as np
    from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget, _fmt_hms

    plots = LivePlotWidget()
    plots._apply_vi_y_range(np.array([2.8, 3.6, 4.19]), np.array([-1.15, 0.0, 1.5]))
    v_lo, v_hi = plots.plot_vi.viewRange()[1]
    i_lo, i_hi = plots.view_current.viewRange()[1]
    assert (round(v_lo, 2), round(v_hi, 2)) == (2.0, 4.5)
    assert (round(i_lo, 2), round(i_hi, 2)) == (-3.0, 2.0)
    # Gridlines coincide: same relative position for 0 A and 3.5 V
    assert abs((3.5 - v_lo) / (v_hi - v_lo) - (0.0 - i_lo) / (i_hi - i_lo)) < 1e-9

    plots._apply_vi_y_range(np.array([1.6, 2.4, 2.8]), np.array([-1.0, 1.0]))      # LTO
    assert tuple(round(x, 2) for x in plots.plot_vi.viewRange()[1]) == (0.0, 6.0)

    assert _fmt_hms(35534.3) == "9:52:14.3"

    for label in ("S1 Charge", "S2 Rest", "S3 Discharge"):
        plots.add_event_marker(label)
    assert plots.lbl_event_strip.text().startswith("Events: S3 Discharge")


def test_recipe_tab_names_estimate_and_loop_columns(qapp):
    from single_cell_cycler.ui.widgets.profile_editor import ProfileEditorWidget

    ed = ProfileEditorWidget()
    names = [ed.combo_presets.itemText(i) for i in range(ed.combo_presets.count())]
    assert "CCCV Cycling (15 Cycles)" in names and not any(n.startswith("Cccv") for n in names)
    ed.combo_presets.setCurrentIndex(names.index("CCCV Cycling (15 Cycles)"))

    # 1.5 A charge + 1.2 A discharge of 3000 mAh + two 10 min rests: ~290 min, not the 320 of the time limits
    summary = ed.lbl_recipe_summary.text()
    assert "est. ~290 min/cycle" in summary

    assert not ed.table_steps.verticalHeader().isVisible()
    loop_row = len(ed.current_recipe.steps) - 1
    assert ed.table_steps.cellWidget(loop_row, 6) is not None             # Loop step keeps its spin boxes
    assert ed.table_steps.cellWidget(0, 5) is None and ed.table_steps.item(0, 5).text() == "—"


@pytest.mark.parametrize("num, name, expected", [
    (3, "3. CC Discharge (1.2A to 2.8V)", "3. CC Discharge (1.2A to 2.8V)"),
    (3, "Step 3", "Step 3"),
    (3, "Rest", "Step 3: Rest"),
    (1, "10 min rest", "Step 1: 10 min rest"),      # a different leading number is kept as text
    (12, "12) Long rest", "12) Long rest"),
])
def test_step_label_adds_the_number_only_once(num, name, expected):
    from single_cell_cycler.core.profile_model import step_label

    assert step_label(num, name) == expected


def test_kpi_titles_name_the_cell_at_startup(window):
    assert window.dashboard.card_voltage.lbl_title.text().upper().startswith("CELL 1")
    assert window.dashboard.card_current.lbl_title.text().upper().startswith("CELL 1")


def test_manual_controls_follow_hardware_readback(qapp):
    from single_cell_cycler.comm.packet_codec import CommandEchoTelemetry
    from single_cell_cycler.comm.protocol_defs import FRAME_CHARGE_SEL, FRAME_DISCHARGE_SEL, FRAME_RELAY_CTRL
    from single_cell_cycler.ui.widgets.manual_control import ManualControlWidget

    sent = []
    w = ManualControlWidget(command_sender=lambda f, v, p: sent.append((f, v)))
    w.set_connection_available(True)
    w.set_test_active(True)                       # screenshot 8: locked during a test
    w.on_command_echo(CommandEchoTelemetry(frame_id=FRAME_RELAY_CTRL, payload_byte=0x01))
    w.on_command_echo(CommandEchoTelemetry(frame_id=FRAME_CHARGE_SEL, payload_byte=0x07))
    w.on_command_echo(CommandEchoTelemetry(frame_id=FRAME_DISCHARGE_SEL, payload_byte=0x06))
    assert w.chk_relay_en.isChecked()
    assert "0x01" in w.lbl_relay_summary.text()
    assert w.chk_curr_1.isChecked() and w.chk_curr_2.isChecked()
    assert w.chk_load_2.isChecked() and w.chk_load_3.isChecked() and not w.chk_load_1.isChecked()

    # Test ends: unlocked controls start from the hardware state
    w.on_command_echo(CommandEchoTelemetry(frame_id=FRAME_RELAY_CTRL, payload_byte=0x00))
    w.set_test_active(False)
    assert not w.chk_relay_en.isChecked()

    # The operator's own edits are not overwritten by readback until they press Send
    w.chk_curr_1.setChecked(False)
    w.on_command_echo(CommandEchoTelemetry(frame_id=FRAME_CHARGE_SEL, payload_byte=0x07))
    assert not w.chk_curr_1.isChecked()
    w._send_chg_sel()
    assert sent[-1] == (FRAME_CHARGE_SEL, 0x05)
    w.on_command_echo(CommandEchoTelemetry(frame_id=FRAME_CHARGE_SEL, payload_byte=0x05))
    assert not w.chk_curr_1.isChecked() and w.chk_curr_2.isChecked()
