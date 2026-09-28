"""Unit tests for battery metrology, Coulomb counting, and efficiency."""

import pytest
from single_cell_cycler.comm.packet_codec import CellDataTelemetry
from single_cell_cycler.core.metrics_tracker import MetricsTracker
from single_cell_cycler.core.profile_model import StepType


def test_coulomb_counting_accuracy():
    tracker = MetricsTracker()
    tracker.start_step(1, 1, "CC Charge 1A", StepType.CHARGE)

    # Simulate 1.000 A constant current over 3600 seconds (1 hour) at 100ms intervals
    # Total charge should be exactly 1000.0 mAh
    dt = 0.1  # 100 ms
    t = 0.0
    for step_num in range(36000):
        t += dt
        telemetry = CellDataTelemetry(voltage=3.700, current=1.000, terminal_temp=25.0, body_temp=25.0, timestamp=t)
        tracker.update(telemetry)

    finished = tracker.complete_step("Timeout")
    # Expected: 1.0 A * 1.0 h = 1000 mAh
    assert pytest.approx(finished.capacity_mah, rel=1e-3) == 1000.0
    # Expected energy: 3.7 V * 1.0 A * 1.0 h = 3.7 Wh = 3700 mWh
    assert pytest.approx(finished.energy_mwh, rel=1e-3) == 3700.0


def test_cycle_summary_and_coulombic_efficiency():
    tracker = MetricsTracker()

    # Step 1: Charge 1000 mAh
    t = 1000.0
    tracker.start_step(1, 1, "Charge", StepType.CHARGE, CellDataTelemetry(3.8, 1.0, 25.0, 25.0, timestamp=t))
    t += 3600.0
    tracker.update(CellDataTelemetry(4.2, 1.0, 25.0, 25.0, timestamp=t))
    tracker.complete_step("V max")

    # Step 2: Rest 10s
    tracker.start_step(1, 2, "Rest", StepType.REST, CellDataTelemetry(4.18, 0.0, 25.0, 25.0, timestamp=t))
    t += 10.0
    tracker.update(CellDataTelemetry(4.18, 0.0, 25.0, 25.0, timestamp=t))
    tracker.complete_step("Rest done")

    # Step 3: Discharge 980 mAh (0.98 hours at 1.0A = 3528 seconds)
    tracker.start_step(1, 3, "Discharge", StepType.DISCHARGE, CellDataTelemetry(4.0, -1.0, 25.0, 25.0, timestamp=t))
    t += 3528.0
    tracker.update(CellDataTelemetry(3.0, -1.0, 25.0, 25.0, timestamp=t))
    tracker.complete_step("V min")

    summary = tracker.compute_cycle_summary(1)

    assert pytest.approx(summary.charge_capacity_mah, rel=1e-2) == 1000.0
    assert pytest.approx(summary.discharge_capacity_mah, rel=1e-2) == 980.0
    # Coulombic Efficiency: 980 / 1000 = 98.0 %
    assert pytest.approx(summary.coulombic_efficiency_pct, rel=1e-2) == 98.0
