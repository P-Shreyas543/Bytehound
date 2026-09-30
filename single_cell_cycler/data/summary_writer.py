"""CSV generator for completed step history and cycle summary metrics."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import List

from ..core.dqv_analysis import DQVProfile
from ..core.metrics_tracker import CycleSummary, StepMetrics

logger = logging.getLogger("SingleCellCycler.SummaryWriter")


def write_step_summary_csv(file_path: str | Path, steps: List[StepMetrics]) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "cycle_index",
        "step_index",
        "step_name",
        "step_type",
        "duration_s",
        "start_voltage_v",
        "end_voltage_v",
        "peak_current_a",
        "peak_temp_c",
        "capacity_mah",
        "energy_mwh",
        "dcir_1s_mohm",
        "dcir_10s_mohm",
        "dcir_30s_mohm",
        "dcir_mohm",
        "cutoff_reason",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in steps:
            writer.writerow({
                "cycle_index": s.cycle_index,
                "step_index": s.step_index,
                "step_name": s.step_name,
                "step_type": s.step_type.value,
                "duration_s": round(s.duration_s, 2),
                "start_voltage_v": round(s.start_voltage, 4),
                "end_voltage_v": round(s.end_voltage, 4),
                "peak_current_a": round(s.peak_current, 3),
                "peak_temp_c": round(s.peak_temp, 1),
                "capacity_mah": round(s.capacity_mah, 2),
                "energy_mwh": round(s.energy_mwh, 2),
                "dcir_1s_mohm": s.dcir_1s_mohm if s.dcir_1s_mohm is not None else "",
                "dcir_10s_mohm": s.dcir_10s_mohm if s.dcir_10s_mohm is not None else "",
                "dcir_30s_mohm": s.dcir_30s_mohm if s.dcir_30s_mohm is not None else "",
                "dcir_mohm": s.dcir_mohm if s.dcir_mohm is not None else "",
                "cutoff_reason": s.cutoff_reason,
            })
    logger.info(f"Saved step summary to {path}")


def write_cycle_summary_csv(file_path: str | Path, cycles: List[CycleSummary]) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "cycle_index",
        "charge_capacity_mah",
        "discharge_capacity_mah",
        "charge_energy_mwh",
        "discharge_energy_mwh",
        "coulombic_efficiency_pct",
        "energy_efficiency_pct",
        "duration_s",
        "dcir_1s_mohm",
        "dcir_10s_mohm",
        "dcir_mohm",
        "dqv_peak_voltage_v",
        "dqv_peak_height_mah_v",
        "dqv_peak_shift_mv",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in cycles:
            writer.writerow({
                "cycle_index": c.cycle_index,
                "charge_capacity_mah": c.charge_capacity_mah,
                "discharge_capacity_mah": c.discharge_capacity_mah,
                "charge_energy_mwh": c.charge_energy_mwh,
                "discharge_energy_mwh": c.discharge_energy_mwh,
                "coulombic_efficiency_pct": c.coulombic_efficiency_pct,
                "energy_efficiency_pct": c.energy_efficiency_pct,
                "duration_s": c.duration_s,
                "dcir_1s_mohm": c.dcir_1s_mohm if c.dcir_1s_mohm is not None else "",
                "dcir_10s_mohm": c.dcir_10s_mohm if c.dcir_10s_mohm is not None else "",
                "dcir_mohm": c.dcir_mohm if c.dcir_mohm is not None else "",
                "dqv_peak_voltage_v": c.dqv_peak_voltage_v if c.dqv_peak_voltage_v is not None else "",
                "dqv_peak_height_mah_v": c.dqv_peak_height_mah_v if c.dqv_peak_height_mah_v is not None else "",
                "dqv_peak_shift_mv": c.dqv_peak_shift_mv if c.dqv_peak_shift_mv is not None else "",
            })
    logger.info(f"Saved cycle summary to {path}")


def write_dqv_curves_csv(file_path: str | Path, profiles: List[DQVProfile]) -> None:
    """Save full dQ/dV differential capacity curves to CSV (Option A)."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "cycle_index",
        "step_index",
        "step_type",
        "voltage_v",
        "capacity_mah",
        "dq_dv_mah_v",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in profiles:
            caps = p.capacities if len(p.capacities) == len(p.voltages) else [0.0] * len(p.voltages)
            for v, q, dq in zip(p.voltages, caps, p.dq_dv):
                writer.writerow({
                    "cycle_index": p.cycle_index,
                    "step_index": p.step_index,
                    "step_type": p.step_type,
                    "voltage_v": round(float(v), 4),
                    "capacity_mah": round(float(q), 2),
                    "dq_dv_mah_v": round(float(dq), 2),
                })
    logger.info(f"Saved dQ/dV curve datasets to {path}")
