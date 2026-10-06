"""Voltage faults: a step that moves the cell back into range may run; hard limits stop and latch.

Agreed 2026-10-06: after CUV the next charge must run, after COV the next rest / discharge
must run, without latching. Below the hard charge floor (2.0 V for NMC) charging is refused
and the test stops for inspection; above the hard ceiling (max + 0.10 V) the test stops.
"""

import os

import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.comm.packet_codec import CellDataTelemetry, FaultSoCTelemetry
from single_cell_cycler.comm.protocol_defs import BMSFaultFlags
from single_cell_cycler.core.cycler_engine import CyclerEngine, EngineState
from single_cell_cycler.core.profile_model import CutoffCondition, CutoffType, StepType, TestRecipe, TestStep

COV, CUV = int(BMSFaultFlags.COV), int(BMSFaultFlags.CUV)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


def _recipe(first_type=StepType.DISCHARGE):
    dis = TestStep(step_index=1, name="Discharge", step_type=StepType.DISCHARGE,
                   discharge_load_2=True, discharge_load_3=True,
                   cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MIN, 2.8, True, "")])
    chg = TestStep(step_index=2, name="Charge", step_type=StepType.CHARGE, max_charge_voltage=True,
                   charge_current_1=True, charge_current_2=True,
                   cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MAX, 4.2, True, ""),
                            CutoffCondition(CutoffType.CURRENT_MIN, 0.18, True, "")])
    rest = TestStep(step_index=3, name="Rest", step_type=StepType.REST,
                    cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 600, True, "")])
    dis2 = TestStep(step_index=4, name="Discharge2", step_type=StepType.DISCHARGE, discharge_load_2=True,
                    cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MIN, 2.8, True, "")])
    steps = [dis, chg, rest, dis2] if first_type == StepType.DISCHARGE else [chg, rest, dis2]
    return TestRecipe(recipe_name="t", chemistry="NMC", steps=steps)


def _engine(recipe):
    eng = CyclerEngine(command_sender=lambda f, v, p: None)
    eng.load_recipe(recipe)
    lim = eng.safety_monitor.limits
    lim.max_voltage_v, lim.min_voltage_v, lim.charge_floor_v = 4.30, 2.75, 2.0     # NMC at START
    ended = []
    eng.step_completed.connect(lambda m: ended.append((m.step_name, m.cutoff_reason)))
    eng.start_test()
    return eng, ended


def _cell(eng, v, i):
    eng.on_cell_telemetry(CellDataTelemetry(voltage=v, current=i, terminal_temp=28.0, body_temp=28.0))


def _faults(eng, byte):
    eng.on_fault_soc_telemetry(FaultSoCTelemetry(fault_byte=byte, cov=bool(byte & COV), cuv=bool(byte & CUV),
                                                 occ=False, ocd=False, cot=False, cut=False,
                                                 soc_ocv=50.0, soc_cc=50.0))


def test_cuv_ends_discharge_and_the_charge_still_runs():
    eng, ended = _engine(_recipe())
    _cell(eng, 3.0, -1.2)
    _faults(eng, CUV)
    assert ended[-1][0] == "Discharge" and "CUV" in ended[-1][1]
    _cell(eng, 2.95, 1.5)
    _faults(eng, CUV)                                   # comparator still flagged while charging
    assert eng.active_step.name == "Charge" and eng.state == EngineState.RUNNING
    assert not eng.safety_monitor.is_tripped


def test_charge_runs_between_hard_floor_and_minimum():
    # Below the 2.75 V software minimum the whole recipe used to collapse step by step
    eng, ended = _engine(_recipe())
    _cell(eng, 2.70, -1.2)
    assert ended[-1][0] == "Discharge"                  # discharge still ends at the minimum
    for v in (2.70, 2.72, 2.76, 2.90):
        _cell(eng, v, 1.5)
    assert eng.active_step.name == "Charge" and eng.state == EngineState.RUNNING


def test_charge_refused_and_latched_below_hard_floor():
    eng, _ = _engine(_recipe())
    _cell(eng, 1.90, -0.4)                              # discharge pulled the cell below 2.0 V
    assert eng.state == EngineState.SAFETY_STOP
    assert eng.safety_monitor.is_tripped                # latched: START needs an operator reset
    assert "floor" in eng.safety_monitor.trip_reason


def test_charge_step_never_starts_on_a_cell_already_below_the_floor():
    eng = CyclerEngine(command_sender=lambda f, v, p: None)
    eng.load_recipe(_recipe(first_type=StepType.CHARGE))
    eng.safety_monitor.limits.charge_floor_v = 2.0
    eng._last_telemetry = CellDataTelemetry(voltage=1.6, current=0.0, terminal_temp=25.0, body_temp=25.0)
    eng.start_test()
    assert eng.state == EngineState.SAFETY_STOP and eng.safety_monitor.is_tripped
    assert "Charge refused" in eng.safety_monitor.trip_reason


def test_cov_ends_charge_and_the_rest_still_runs():
    eng, ended = _engine(_recipe())
    _faults(eng, 0)
    _cell(eng, 2.79, -1.2)                              # discharge -> 2.8 V cut-off
    _cell(eng, 4.18, 1.5)
    _faults(eng, COV)
    assert ended[-1][0] == "Charge" and "COV" in ended[-1][1]
    _cell(eng, 4.17, 0.0)
    _faults(eng, COV)                                   # still flagged in the post-charge rest
    _cell(eng, 4.17, 0.0)
    assert eng.active_step.name == "Rest" and eng.state == EngineState.RUNNING


def test_discharge_runs_above_max_but_hard_ceiling_stops_and_latches():
    eng, _ = _engine(_recipe())
    _cell(eng, 4.33, -1.2)                              # above 4.30 max, below 4.40 ceiling
    assert eng.active_step.name == "Discharge" and eng.state == EngineState.RUNNING
    _cell(eng, 4.45, -1.2)
    assert eng.state == EngineState.SAFETY_STOP and eng.safety_monitor.is_tripped
    assert "ceiling" in eng.safety_monitor.trip_reason
