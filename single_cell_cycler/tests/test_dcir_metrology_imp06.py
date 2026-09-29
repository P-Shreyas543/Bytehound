"""Automated test suite for Standardized Pulse DCIR (IEC 62660-1 / USABC) - IMP-06."""

import csv
from pathlib import Path
import pytest

from single_cell_cycler.comm.packet_codec import CellDataTelemetry
from single_cell_cycler.core.metrics_tracker import (
    DCIRMeasurement,
    MetricsTracker,
    StepType,
)
from single_cell_cycler.data.summary_writer import (
    write_cycle_summary_csv,
    write_step_summary_csv,
)


def test_standardized_pulse_dcir_1s_10s_30s():
    """Verify IEC 62660-1 pulse resistance measurement against synthetic pulse."""
    tracker = MetricsTracker()

    # Step 1: Rest step (establishes baseline V0 = 3.800V, I0 = 0.0A)
    t0 = 1000.0
    telem_rest = CellDataTelemetry(voltage=3.800, current=0.0, terminal_temp=25.0, body_temp=25.0, timestamp=t0)
    tracker.start_step(1, 1, "Rest", StepType.REST, telem_rest)
    tracker.update(telem_rest)
    tracker.complete_step("Time cutoff")

    # Step 2: 2.0 A Discharge Pulse
    # Baseline was V0 = 3.800, I0 = 0.0
    # True impedances: R_1s = 15.0 mOhm, R_10s = 18.0 mOhm, R_30s = 22.0 mOhm
    t_pulse_start = t0 + 10.0
    telem_init = CellDataTelemetry(voltage=3.800, current=-2.0, terminal_temp=25.0, body_temp=25.0, timestamp=t_pulse_start)
    tracker.start_step(1, 2, "Discharge Pulse", StepType.DISCHARGE, telem_init)

    # Telemetry frame at t = 1.0s (delta_v = 2.0 * 0.015 = 0.030V -> V = 3.770V)
    telem_1s = CellDataTelemetry(voltage=3.770, current=-2.0, terminal_temp=25.1, body_temp=25.1, timestamp=t_pulse_start + 1.0)
    tracker.update(telem_1s)
    assert tracker.current_step_metrics.dcir_1s_mohm == 15.0
    assert tracker.current_step_metrics.dcir_mohm == 15.0  # Temporary primary until 10s

    # Telemetry frame at t = 10.0s (delta_v = 2.0 * 0.018 = 0.036V -> V = 3.764V)
    telem_10s = CellDataTelemetry(voltage=3.764, current=-2.0, terminal_temp=25.3, body_temp=25.3, timestamp=t_pulse_start + 10.0)
    tracker.update(telem_10s)
    assert tracker.current_step_metrics.dcir_10s_mohm == 18.0
    assert tracker.current_step_metrics.dcir_mohm == 18.0  # Standard 10s replaces 1s as primary metric

    # Telemetry frame at t = 30.0s (delta_v = 2.0 * 0.022 = 0.044V -> V = 3.756V)
    telem_30s = CellDataTelemetry(voltage=3.756, current=-2.0, terminal_temp=25.5, body_temp=25.5, timestamp=t_pulse_start + 30.0)
    tracker.update(telem_30s)
    assert tracker.current_step_metrics.dcir_30s_mohm == 22.0

    finished_step = tracker.complete_step("Time cutoff")
    assert finished_step.dcir_1s_mohm == 15.0
    assert finished_step.dcir_10s_mohm == 18.0
    assert finished_step.dcir_30s_mohm == 22.0
    assert finished_step.dcir_mohm == 18.0

    # Verify DCIR measurement history logged
    assert len(tracker.dcir_measurements) == 1
    m = tracker.dcir_measurements[0]
    assert m.r_1s_mohm == 15.0
    assert m.r_10s_mohm == 18.0
    assert m.r_30s_mohm == 22.0

    # Verify CycleSummary incorporates standardized 10s DCIR
    c_sum = tracker.compute_cycle_summary(1)
    assert c_sum.dcir_10s_mohm == 18.0
    assert c_sum.dcir_1s_mohm == 15.0
    assert c_sum.dcir_mohm == 18.0


def test_dcir_csv_summary_generation(tmp_path: Path):
    """Verify that CSV exports include all standardized DCIR columns and metrics."""
    tracker = MetricsTracker()

    # Create dummy step with DCIR metrics
    t0 = 100.0
    telem_rest = CellDataTelemetry(voltage=3.900, current=0.0, terminal_temp=25.0, body_temp=25.0, timestamp=t0)
    tracker.start_step(1, 1, "Rest", StepType.REST, telem_rest)
    tracker.update(telem_rest)
    tracker.complete_step("Rest Done")

    t1 = t0 + 10.0
    telem_pulse = CellDataTelemetry(voltage=3.900, current=-1.0, terminal_temp=25.0, body_temp=25.0, timestamp=t1)
    tracker.start_step(1, 2, "Pulse", StepType.DISCHARGE, telem_pulse)
    tracker.update(CellDataTelemetry(voltage=3.880, current=-1.0, terminal_temp=25.0, body_temp=25.0, timestamp=t1 + 1.0))
    tracker.update(CellDataTelemetry(voltage=3.875, current=-1.0, terminal_temp=25.0, body_temp=25.0, timestamp=t1 + 10.0))
    tracker.complete_step("Pulse Done")

    c_sum = tracker.compute_cycle_summary(1)

    # Write step CSV
    step_csv = tmp_path / "test_steps.csv"
    write_step_summary_csv(step_csv, tracker.step_history)
    assert step_csv.exists()

    with step_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert "dcir_1s_mohm" in reader.fieldnames
        assert "dcir_10s_mohm" in reader.fieldnames
        assert "dcir_30s_mohm" in reader.fieldnames
        assert "dcir_mohm" in reader.fieldnames
        pulse_row = rows[1]
        assert float(pulse_row["dcir_1s_mohm"]) == 20.0
        assert float(pulse_row["dcir_10s_mohm"]) == 25.0
        assert float(pulse_row["dcir_mohm"]) == 25.0

    # Write cycle CSV
    cycle_csv = tmp_path / "test_cycles.csv"
    write_cycle_summary_csv(cycle_csv, tracker.cycle_summaries)
    assert cycle_csv.exists()

    with cycle_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        c_rows = list(reader)
        assert "dcir_1s_mohm" in reader.fieldnames
        assert "dcir_10s_mohm" in reader.fieldnames
        assert "dcir_mohm" in reader.fieldnames
        c_row = c_rows[0]
        assert float(c_row["dcir_10s_mohm"]) == 25.0
        assert float(c_row["dcir_mohm"]) == 25.0
