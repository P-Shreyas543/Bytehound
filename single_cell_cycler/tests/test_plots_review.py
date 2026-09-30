"""Regression tests for the chart review: temperature, V-Q, dQ/dV, aging, and the
'"charge" in "discharge"' substring bugs found alongside them."""

import os
import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.comm.packet_codec import CellDataTelemetry, FaultSoCTelemetry
from single_cell_cycler.comm.protocol_defs import BMSFaultFlags
from single_cell_cycler.core.metrics_tracker import MetricsTracker
from single_cell_cycler.core.profile_model import StepType
from single_cell_cycler.core.safety_monitor import SafetyMonitor


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


@pytest.fixture
def plots(qapp):
    from single_cell_cycler.ui.widgets.live_plots import LivePlotWidget
    w = LivePlotWidget(max_buffer_points=100_000)
    w.resize(1400, 700)
    w.show()
    qapp.processEvents()
    yield w
    w.close()


def _cuv_fault():
    return FaultSoCTelemetry(fault_byte=int(BMSFaultFlags.CUV), soc_ocv=5.0, soc_cc=5.0,
                             cov=False, cuv=True, occ=False, ocd=False, cot=False, cut=False)


def test_under_voltage_during_discharge_is_not_ignored():
    """'charge' in 'discharge' used to suppress CUV exactly when it matters."""
    mon = SafetyMonitor(command_sender=lambda *a: None)
    assert mon.check_bms_faults(_cuv_fault(), active_step_type="Discharge", cell_voltage=2.7) is False
    assert mon.trip_kind == "voltage"


def test_under_voltage_while_charging_is_still_tolerated():
    mon = SafetyMonitor(command_sender=lambda *a: None)
    assert mon.check_bms_faults(_cuv_fault(), active_step_type="Charge", cell_voltage=2.9) is True


def test_discharge_vq_trace_uses_discharge_colour_and_fit_covers_full_history(plots):
    from single_cell_cycler.ui.widgets import live_plots as lp
    plots.notify_step_started(1, 3, "Discharge")
    plots._relay_on = True
    for k in range(200):
        plots.add_telemetry(CellDataTelemetry(voltage=4.1 - k * 0.006, current=-1.2,
                                              terminal_temp=27.0, body_temp=27.0,
                                              timestamp=time.time() + k), step_mah=k * 5.5)
    plots.reset_step_vq(step_type="Discharge", cycle_idx=1, step_idx=3)

    stype, item, caps, volts = plots._vq_history_curves[-1]
    assert item.opts["pen"].color().name() == pg_color(lp._AGING_Q_DIS_COLOR)
    plots.plot_vq.setXRange(0, 50)                       # user zoomed in before
    plots.fit_vq_view()
    assert plots.plot_vq.viewRange()[0][1] >= caps.max()  # whole ~1100 mAh curve in view


def pg_color(c):
    import pyqtgraph as pg
    return pg.mkColor(c).name()


def test_dqv_buffer_excludes_constant_voltage_tail(plots):
    plots.notify_step_started(1, 1, "Charge")
    plots._relay_on = True
    t0 = time.time()
    for k in range(100):                                   # CC phase at 1.5 A
        plots.add_telemetry(CellDataTelemetry(voltage=3.6 + k * 0.006, current=1.5,
                                              terminal_temp=27.0, body_temp=27.0, timestamp=t0 + k), k * 4.0)
    n_cc = len(plots._dqv_v_buf)
    for k in range(100):                                   # CV phase: 4.2 V, current tapering
        plots.add_telemetry(CellDataTelemetry(voltage=4.2, current=1.4 - k * 0.012,
                                              terminal_temp=27.0, body_temp=27.0, timestamp=t0 + 100 + k), 400 + k)
    assert n_cc == 100
    # Only the first CV samples still carrying >= 90 % of the CC current are kept (1.40..1.35 A);
    # the long taper tail (95 samples down to 0.2 A) is excluded
    assert len(plots._dqv_v_buf) <= n_cc + 6
    assert min(plots._dqv_q_buf) >= 0 and len(plots._dqv_v_buf) < 150


def test_metrics_dqv_and_dcir_ignore_cv_tail_and_missing_baseline():
    mt = MetricsTracker()
    t0 = 1_000_000.0
    mt.start_step(1, 1, "Charge", StepType.CHARGE, initial_telemetry=None)   # no reading before start
    for k in range(60):
        mt.update(CellDataTelemetry(voltage=3.7 + k * 0.005, current=1.5, terminal_temp=25, body_temp=25,
                                    timestamp=t0 + k))
    step = mt.current_step_metrics
    assert step.dcir_mohm is None                          # baseline would have been 0 V (≈2300 mΩ)
    n_cc = len(mt._step_v_buf)
    for k in range(60):
        mt.update(CellDataTelemetry(voltage=4.2, current=1.3 - k * 0.02, terminal_temp=25, body_temp=25,
                                    timestamp=t0 + 60 + k))
    assert len(mt._step_v_buf) <= n_cc + 2


def test_temperature_axis_follows_the_data(plots):
    plots._relay_on = True
    plots.notify_step_started(1, 1, "Charge")
    t0 = plots.start_epoch
    for k in range(300):
        plots.add_telemetry(CellDataTelemetry(voltage=3.9, current=1.0, terminal_temp=25 + k * 0.01,
                                              body_temp=24.6 + k * 0.01, timestamp=t0 + k), k)
    plots.tabs.setCurrentIndex(1)
    plots._dirty = True
    plots.tick_update()
    lo, hi = plots.plot_temp.viewRange()[1]
    assert 20.0 < lo < 25.0 and 28.0 < hi < 35.0           # not a fixed 0–70 °C


def test_aging_cycle_axis_shows_whole_cycles_and_reaches_eol(plots):
    for c, q in enumerate([1166, 1142, 1120, 1097, 1075], start=1):
        plots.add_cycle_summary(c, q, 100.0, charge_mah=q, energy_eff=94.0, dcir_mohm=80.0)
    plots.tabs.setCurrentIndex(4)
    plots._render_aging_tab()
    plots.fit_aging_view()
    axis = plots.plot_aging_cap.getAxis("bottom")
    x0, x1 = plots.plot_aging_cap.viewRange()[0]
    ticks = [v for _, vals in axis.tickValues(x0, x1, 1200) for v in vals]
    assert ticks and all(float(v).is_integer() for v in ticks)
    eol = plots._last_forecast.projected_eol_cycle
    assert eol and x1 >= eol                               # the 80 % crossing is on screen


# --- Partial first cycle (recipe starts with a charge from an unknown charge level) -------------

def _engine_with(steps):
    from single_cell_cycler.core.cycler_engine import CyclerEngine
    from single_cell_cycler.core.profile_model import TestRecipe
    engine = CyclerEngine(command_sender=lambda *a: None)
    engine.load_recipe(TestRecipe(recipe_name="r", steps=steps))
    return engine


def _step(idx, stype):
    from single_cell_cycler.core.profile_model import TestStep
    return TestStep(step_index=idx, name=f"S{idx}", step_type=stype)


def test_cycle1_flagged_partial_only_when_recipe_starts_with_charge():
    from single_cell_cycler.core.metrics_tracker import CycleSummary
    eng = _engine_with([_step(1, StepType.REST), _step(2, StepType.CHARGE), _step(3, StepType.DISCHARGE)])
    c1, c2 = CycleSummary(cycle_index=1), CycleSummary(cycle_index=2)
    eng._flag_partial_cycle(c1); eng._flag_partial_cycle(c2)
    assert c1.partial_initial_charge is True and c2.partial_initial_charge is False

    eng = _engine_with([_step(1, StepType.DISCHARGE), _step(2, StepType.CHARGE)])
    c1 = CycleSummary(cycle_index=1)
    eng._flag_partial_cycle(c1)
    assert c1.partial_initial_charge is False          # full discharge first: cycle 1 is valid


def test_partial_flag_survives_crash_recovery_journal():
    from single_cell_cycler.core.metrics_tracker import CycleSummary
    from single_cell_cycler.core.state_journal import cycle_summary_from_dict, cycle_summary_to_dict
    c = CycleSummary(cycle_index=1, coulombic_efficiency_pct=110.6, partial_initial_charge=True)
    assert cycle_summary_from_dict(cycle_summary_to_dict(c)).partial_initial_charge is True
    assert cycle_summary_from_dict({"cycle_index": 2}).partial_initial_charge is False   # old journals


def test_partial_cycle_is_off_the_efficiency_trend_and_axis(plots):
    plots.add_cycle_summary(1, 1166, 110.6, charge_mah=1054, energy_eff=103.0, dcir_mohm=70, partial=True)
    for c in range(2, 6):
        plots.add_cycle_summary(c, 1166 - 22 * c, 100.0, charge_mah=1166 - 22 * c, energy_eff=94.0, dcir_mohm=90)
    x, y = plots.curve_aging_ce.getData()
    assert 1.0 not in list(x) and max(y) <= 100.0
    px, py = plots.scatter_aging_partial_eff.getData()
    assert list(px) == [1.0, 1.0] and 110.6 in list(py)
    assert plots.plot_aging_eff.viewRange()[1][1] >= 110.6  # still visible, as a hollow labelled marker
    assert "partial" in plots.lbl_aging_data_state.text()
    plots.reset_all()
    assert plots._partial_labels == [] and len(plots.scatter_aging_partial_eff.getData()[0]) == 0


def test_report_average_ce_excludes_partial_cycle_and_footnotes_it(tmp_path):
    from single_cell_cycler.core.metrics_tracker import CycleSummary
    from single_cell_cycler.data.report_generator import generate_html_report
    cycles = [CycleSummary(cycle_index=1, discharge_capacity_mah=1166, charge_capacity_mah=1054,
                           coulombic_efficiency_pct=110.6, partial_initial_charge=True)]
    cycles += [CycleSummary(cycle_index=c, discharge_capacity_mah=1100, charge_capacity_mah=1100,
                            coulombic_efficiency_pct=99.5) for c in range(2, 5)]
    html_text = generate_html_report(tmp_path / "r.html", cycles=cycles).read_text(encoding="utf-8")
    assert "99.50%" in html_text                          # average of cycles 2-4 only
    assert "102.28%" not in html_text                     # the average with cycle 1 included
    assert "110.60% *" in html_text and "Partial cycle" in html_text
