"""Unit tests for deterministic cut-off detection engine."""

from single_cell_cycler.comm.packet_codec import CellDataTelemetry
from single_cell_cycler.core.cutoff_detector import CutoffDetector
from single_cell_cycler.core.profile_model import CutoffCondition, CutoffType, StepType, TestStep


def test_voltage_upper_cutoff():
    detector = CutoffDetector(current_taper_arming_delay_s=2.0)
    step = TestStep(
        step_index=1,
        name="Charge",
        step_type=StepType.CHARGE,
        cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MAX, 4.200, True)],
    )

    # 1. Below cut-off
    res = detector.evaluate(step, CellDataTelemetry(4.180, 1.5, 25.0, 25.0), 10.0, 50.0)
    assert not res.is_triggered

    # 2. At / Above cut-off
    res = detector.evaluate(step, CellDataTelemetry(4.201, 1.5, 25.0, 25.0), 15.0, 70.0)
    assert res.is_triggered
    assert "Voltage reached" in res.trigger_reason


def test_voltage_lower_cutoff():
    detector = CutoffDetector()
    step = TestStep(
        step_index=1,
        name="Discharge",
        step_type=StepType.DISCHARGE,
        cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MIN, 2.800, True)],
    )

    # Above cut-off
    res = detector.evaluate(step, CellDataTelemetry(2.950, -2.0, 26.0, 26.0), 100.0, 200.0)
    assert not res.is_triggered

    # Tripped
    res = detector.evaluate(step, CellDataTelemetry(2.795, -2.0, 26.0, 26.0), 150.0, 300.0)
    assert res.is_triggered
    assert "2.795" in res.trigger_reason


def test_current_taper_cutoff_arming_delay():
    detector = CutoffDetector(current_taper_arming_delay_s=3.0)
    step = TestStep(
        step_index=1,
        name="CV Charge",
        step_type=StepType.CHARGE,
        cutoffs=[CutoffCondition(CutoffType.CURRENT_MIN, 0.050, True)],
    )

    # At t=1.0s, current is 0.02A (ramp-up transient): should NOT trigger due to arming delay
    res = detector.evaluate(step, CellDataTelemetry(4.200, 0.020, 25.0, 25.0), 1.0, 1.0)
    assert not res.is_triggered

    # At t=5.0s, current has tapered to 0.040A: should trigger!
    res = detector.evaluate(step, CellDataTelemetry(4.200, 0.040, 25.0, 25.0), 5.0, 100.0)
    assert res.is_triggered
    assert "Current tapered to 0.040" in res.trigger_reason


def test_duration_and_capacity_cutoffs():
    detector = CutoffDetector()
    step = TestStep(
        step_index=1,
        name="Rest",
        step_type=StepType.REST,
        cutoffs=[
            CutoffCondition(CutoffType.DURATION_MAX, 600.0, True),
            CutoffCondition(CutoffType.CAPACITY_MAX, 1500.0, True),
        ],
    )

    # Duration below limit
    res = detector.evaluate(step, CellDataTelemetry(3.80, 0.0, 25.0, 25.0), 590.0, 0.0)
    assert not res.is_triggered

    # Duration reached
    res = detector.evaluate(step, CellDataTelemetry(3.80, 0.0, 25.0, 25.0), 601.0, 0.0)
    assert res.is_triggered
    assert "Step duration" in res.trigger_reason
