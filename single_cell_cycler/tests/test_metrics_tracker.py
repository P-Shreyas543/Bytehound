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


def test_dqv_curve_logging_and_cycle_peak_tracking(tmp_path):
    """Verify Option A (dedicated dQ/dV curve CSV) and Option B (peak metrics in cycle summary)."""
    from single_cell_cycler.data.summary_writer import write_cycle_summary_csv, write_dqv_curves_csv
    import numpy as np

    tracker = MetricsTracker()

    # Step 1: Synthesize a realistic charge step with 100 points from 3.2V to 4.2V
    t = 0.0
    tracker.start_step(1, 1, "CC Charge", StepType.CHARGE, CellDataTelemetry(3.20, 1.0, 25.0, 25.0, timestamp=t))
    v_points = np.linspace(3.20, 4.20, 100)
    # Add a transition plateau around 3.70V
    v_curve = np.sort(v_points + 0.05 * np.tanh((np.linspace(0, 1, 100) - 0.5) * 8))
    for v in v_curve:
        t += 36.0
        tracker.update(CellDataTelemetry(voltage=float(v), current=1.0, terminal_temp=25.0, body_temp=25.0, timestamp=t))

    finished = tracker.complete_step("Target Voltage")

    # Verify that a dQ/dV profile was generated
    assert len(tracker.dqv_profiles) == 1
    prof = tracker.dqv_profiles[0]
    assert prof.cycle_index == 1
    assert prof.step_index == 1
    assert len(prof.voltages) > 0
    assert len(prof.dq_dv) == len(prof.voltages)

    # Compute cycle summary (Option B)
    summary = tracker.compute_cycle_summary(1)
    if prof.peaks:
        assert summary.dqv_peak_voltage_v is not None
        assert summary.dqv_peak_height_mah_v is not None
        assert summary.dqv_peak_shift_mv == 0.0  # Cycle 1 shift is 0.0 mV

    # Test Option A: Write dQ/dV curves to CSV
    dqv_csv = tmp_path / "dqv_curves.csv"
    write_dqv_curves_csv(dqv_csv, tracker.dqv_profiles)
    assert dqv_csv.exists()
    content = dqv_csv.read_text(encoding="utf-8")
    assert "cycle_index,step_index,step_type,voltage_v,capacity_mah,dq_dv_mah_v" in content
    assert "Charge" in content

    # Test Option B: Write cycle summary with dQ/dV peak columns
    cycle_csv = tmp_path / "summary_cycles.csv"
    write_cycle_summary_csv(cycle_csv, tracker.cycle_summaries)
    assert cycle_csv.exists()
    c_content = cycle_csv.read_text(encoding="utf-8")
    assert "dqv_peak_voltage_v" in c_content
    assert "dqv_peak_height_mah_v" in c_content
    assert "dqv_peak_shift_mv" in c_content

