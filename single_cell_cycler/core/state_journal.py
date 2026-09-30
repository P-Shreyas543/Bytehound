"""Atomic State Journaling and Power-Loss / Crash Recovery Engine (IMP-08).

Saves active cycler state atomically using temporary write + replace, allowing
seamless recovery from unexpected workstation reboots or power loss during
multi-day battery qualification tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from .metrics_tracker import CycleSummary, StepMetrics
from .profile_model import StepType, TestRecipe

from single_cell_cycler.config.cycler_config import DEFAULT_LOG_DIR

logger = logging.getLogger("SingleCellCycler.StateJournal")

DEFAULT_JOURNAL_FILENAME = ".active_test_journal.json"


@dataclass
class TestJournalData:
    """Snapshot of active cycler execution state for crash recovery."""
    __test__ = False
    version: str = "1.0"
    active: bool = True
    timestamp: float = 0.0
    recipe_name: str = ""
    recipe_path: Optional[str] = None
    recipe_dict: Dict[str, Any] = field(default_factory=dict)
    selected_cell: int = 1
    current_cycle: int = 1
    current_step_idx: int = 0
    step_name: str = ""
    step_type: str = ""
    loop_counters: Dict[str, int] = field(default_factory=dict)
    cumulative_charge_mah: float = 0.0
    cumulative_discharge_mah: float = 0.0
    cumulative_charge_mwh: float = 0.0
    cumulative_discharge_mwh: float = 0.0
    total_test_start_time: float = 0.0
    step_history: List[Dict[str, Any]] = field(default_factory=list)
    cycle_summaries: List[Dict[str, Any]] = field(default_factory=list)
    csv_log_file: Optional[str] = None


def step_metrics_to_dict(m: StepMetrics) -> Dict[str, Any]:
    return {
        "cycle_index": m.cycle_index,
        "step_index": m.step_index,
        "step_name": m.step_name,
        "step_type": m.step_type.value,
        "start_time": m.start_time,
        "end_time": m.end_time,
        "duration_s": m.duration_s,
        "start_voltage": m.start_voltage,
        "end_voltage": m.end_voltage,
        "peak_current": m.peak_current,
        "peak_temp": m.peak_temp,
        "capacity_mah": m.capacity_mah,
        "energy_mwh": m.energy_mwh,
        "dcir_1s_mohm": m.dcir_1s_mohm,
        "dcir_10s_mohm": m.dcir_10s_mohm,
        "dcir_30s_mohm": m.dcir_30s_mohm,
        "dcir_mohm": m.dcir_mohm,
        "cutoff_reason": m.cutoff_reason,
    }


def step_metrics_from_dict(d: Dict[str, Any]) -> StepMetrics:
    return StepMetrics(
        cycle_index=int(d["cycle_index"]),
        step_index=int(d["step_index"]),
        step_name=str(d["step_name"]),
        step_type=StepType(d["step_type"]),
        start_time=float(d["start_time"]),
        end_time=float(d.get("end_time", 0.0)),
        duration_s=float(d.get("duration_s", 0.0)),
        start_voltage=float(d.get("start_voltage", 0.0)),
        end_voltage=float(d.get("end_voltage", 0.0)),
        peak_current=float(d.get("peak_current", 0.0)),
        peak_temp=float(d.get("peak_temp", 0.0)),
        capacity_mah=float(d.get("capacity_mah", 0.0)),
        energy_mwh=float(d.get("energy_mwh", 0.0)),
        dcir_1s_mohm=d.get("dcir_1s_mohm"),
        dcir_10s_mohm=d.get("dcir_10s_mohm"),
        dcir_30s_mohm=d.get("dcir_30s_mohm"),
        dcir_mohm=d.get("dcir_mohm"),
        cutoff_reason=str(d.get("cutoff_reason", "")),
    )


def cycle_summary_to_dict(s: CycleSummary) -> Dict[str, Any]:
    return {
        "cycle_index": s.cycle_index,
        "charge_capacity_mah": s.charge_capacity_mah,
        "discharge_capacity_mah": s.discharge_capacity_mah,
        "charge_energy_mwh": s.charge_energy_mwh,
        "discharge_energy_mwh": s.discharge_energy_mwh,
        "coulombic_efficiency_pct": s.coulombic_efficiency_pct,
        "energy_efficiency_pct": s.energy_efficiency_pct,
        "duration_s": s.duration_s,
        "dcir_1s_mohm": s.dcir_1s_mohm,
        "dcir_10s_mohm": s.dcir_10s_mohm,
        "dcir_mohm": s.dcir_mohm,
    }


def cycle_summary_from_dict(d: Dict[str, Any]) -> CycleSummary:
    return CycleSummary(
        cycle_index=int(d["cycle_index"]),
        charge_capacity_mah=float(d.get("charge_capacity_mah", 0.0)),
        discharge_capacity_mah=float(d.get("discharge_capacity_mah", 0.0)),
        charge_energy_mwh=float(d.get("charge_energy_mwh", 0.0)),
        discharge_energy_mwh=float(d.get("discharge_energy_mwh", 0.0)),
        coulombic_efficiency_pct=float(d.get("coulombic_efficiency_pct", 0.0)),
        energy_efficiency_pct=float(d.get("energy_efficiency_pct", 0.0)),
        duration_s=float(d.get("duration_s", 0.0)),
        dcir_1s_mohm=d.get("dcir_1s_mohm"),
        dcir_10s_mohm=d.get("dcir_10s_mohm"),
        dcir_mohm=d.get("dcir_mohm"),
    )


class StateJournalManager:
    """Manages atomic writing, loading, and recovery of active test journals."""

    def __init__(self, journal_dir: str | Path | None = None):
        self.journal_dir = Path(journal_dir) if journal_dir is not None else DEFAULT_LOG_DIR
        try:
            self.journal_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.journal_dir = Path.home() / ".bytehound" / "cycler" / "logs"
            self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.journal_dir / DEFAULT_JOURNAL_FILENAME
        self.tmp_path = self.journal_dir / f"{DEFAULT_JOURNAL_FILENAME}.tmp"

    def is_recovery_available(self) -> bool:
        """Check if an unclosed active test journal exists."""
        if not self.journal_path.exists():
            return False
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return bool(data.get("active", False) and data.get("recipe_dict"))
        except Exception as e:
            logger.warning(f"Failed to inspect recovery journal: {e}")
            return False

    def write_journal(self, journal: TestJournalData) -> bool:
        """Atomically persist test state to journal file."""
        try:
            journal.timestamp = time.time()
            data = asdict(journal)
            with open(self.tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace ensures crash never leaves a half-written file
            os.replace(self.tmp_path, self.journal_path)
            return True
        except Exception as e:
            logger.error(f"Failed to write atomic state journal: {e}")
            return False

    def read_journal(self) -> Optional[TestJournalData]:
        """Read and validate active journal file."""
        if not self.journal_path.exists():
            return None
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data.get("active", False):
                return None
            return TestJournalData(
                version=data.get("version", "1.0"),
                active=data.get("active", True),
                timestamp=data.get("timestamp", 0.0),
                recipe_name=data.get("recipe_name", ""),
                recipe_path=data.get("recipe_path"),
                recipe_dict=data.get("recipe_dict", {}),
                selected_cell=data.get("selected_cell", 1),
                current_cycle=data.get("current_cycle", 1),
                current_step_idx=data.get("current_step_idx", 0),
                step_name=data.get("step_name", ""),
                step_type=data.get("step_type", ""),
                loop_counters=data.get("loop_counters", {}),
                cumulative_charge_mah=data.get("cumulative_charge_mah", 0.0),
                cumulative_discharge_mah=data.get("cumulative_discharge_mah", 0.0),
                cumulative_charge_mwh=data.get("cumulative_charge_mwh", 0.0),
                cumulative_discharge_mwh=data.get("cumulative_discharge_mwh", 0.0),
                total_test_start_time=data.get("total_test_start_time", 0.0),
                step_history=data.get("step_history", []),
                cycle_summaries=data.get("cycle_summaries", []),
                csv_log_file=data.get("csv_log_file"),
            )
        except Exception as e:
            logger.error(f"Failed to read test journal: {e}")
            return None

    def clear_journal(self) -> None:
        """Mark journal inactive and remove file upon normal test conclusion or discard."""
        try:
            if self.journal_path.exists():
                with open(self.tmp_path, "w", encoding="utf-8") as f:
                    json.dump({"active": False, "timestamp": time.time()}, f)
                    f.flush()
                os.replace(self.tmp_path, self.journal_path)
                os.remove(self.journal_path)
            if self.tmp_path.exists():
                os.remove(self.tmp_path)
            logger.info("State journal cleared")
        except Exception as e:
            logger.warning(f"Error clearing state journal: {e}")
