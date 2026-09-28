"""CSV generator for completed step history and cycle summary metrics."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import List

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
        "dcir_mohm",
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
                "dcir_mohm": c.dcir_mohm if c.dcir_mohm is not None else "",
            })
    logger.info(f"Saved cycle summary to {path}")
