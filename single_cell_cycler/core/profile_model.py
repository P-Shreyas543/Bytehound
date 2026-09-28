"""Data models for Battery Cell Cycler test profiles, steps, and cut-off conditions."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class StepType(str, Enum):
    CHARGE = "Charge"
    DISCHARGE = "Discharge"
    REST = "Rest"
    LOOP = "Loop"


class CutoffType(str, Enum):
    VOLTAGE_MAX = "Voltage >= Target"          # Upper voltage cutoff (e.g., 4.20V)
    VOLTAGE_MIN = "Voltage <= Target"          # Lower voltage cutoff (e.g., 2.80V)
    CURRENT_MIN = "Current <= Target (Taper)"  # Current taper cutoff (e.g., 0.05A)
    CURRENT_MAX = "Current >= Target"          # Overcurrent cutoff
    DURATION_MAX = "Step Duration >="          # Maximum step time in seconds
    CAPACITY_MAX = "Step Capacity >="          # Maximum step capacity in mAh
    TEMP_MAX = "Temperature >="                # High temperature cutoff in °C
    COMPARATOR_TRIP = "Hardware Comparator Trip" # Trip from board comparator


@dataclass
class CutoffCondition:
    cutoff_type: CutoffType
    threshold: float = 0.0
    enabled: bool = True
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cutoff_type": self.cutoff_type.value,
            "threshold": self.threshold,
            "enabled": self.enabled,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CutoffCondition:
        return cls(
            cutoff_type=CutoffType(data["cutoff_type"]),
            threshold=float(data.get("threshold", 0.0)),
            enabled=bool(data.get("enabled", True)),
            description=str(data.get("description", "")),
        )


@dataclass
class TestStep:
    __test__ = False
    step_index: int
    name: str
    step_type: StepType
    # Hardware Setpoints for 0x6001 & 0x6004
    max_charge_voltage: bool = False   # 0x6001 bit 0
    charge_current_1: bool = True     # 0x6001 bit 1
    charge_current_2: bool = False    # 0x6001 bit 2
    discharge_load_1: bool = False    # 0x6004 bit 0
    discharge_load_2: bool = False    # 0x6004 bit 1
    discharge_load_3: bool = False    # 0x6004 bit 2
    discharge_load_4: bool = False    # 0x6004 bit 3
    cell_select: int = 1              # 0x6000 bit 1 (1 = Cell 1, 2 = Cell 2)
    # Cutoff conditions
    cutoffs: List[CutoffCondition] = field(default_factory=list)
    # Loop parameters
    loop_target_step: int = 1
    loop_count: int = 1

    @property
    def charge_voltage_target(self) -> float:
        """Target CCCV voltage: 4.2V (bit 0 = 1) or 3.6V (bit 0 = 0)."""
        return 4.2 if self.max_charge_voltage else 3.6

    @property
    def charge_current_target(self) -> float:
        """Target charge current in Amperes: 0.0, 0.5, 1.0, or 1.5A."""
        c = 0.0
        if self.charge_current_1:
            c += 0.5
        if self.charge_current_2:
            c += 1.0
        return round(c, 1)

    @property
    def discharge_current_target(self) -> float:
        """Target discharge current in Amperes (0.0 to 3.0A in 0.2A steps)."""
        c = 0.0
        if self.discharge_load_1:
            c += 0.2
        if self.discharge_load_2:
            c += 0.4
        if self.discharge_load_3:
            c += 0.8
        if self.discharge_load_4:
            c += 1.6
        return round(c, 1)

    @property
    def discharge_load_decimal(self) -> int:
        """Decimal register value for 0x6004 (0 to 15)."""
        val = 0
        if self.discharge_load_1:
            val |= 1
        if self.discharge_load_2:
            val |= 2
        if self.discharge_load_3:
            val |= 4
        if self.discharge_load_4:
            val |= 8
        return val

    def set_charge_setpoints(self, max_voltage: float, current_a: float) -> None:
        """Set charge voltage (3.6 or 4.2V) and current (0.0, 0.5, 1.0, 1.5A)."""
        self.max_charge_voltage = (max_voltage >= 4.0)
        if current_a > 1.25:
            self.charge_current_1 = True
            self.charge_current_2 = True
        elif current_a > 0.75:
            self.charge_current_1 = False
            self.charge_current_2 = True
        elif current_a > 0.25:
            self.charge_current_1 = True
            self.charge_current_2 = False
        else:
            self.charge_current_1 = False
            self.charge_current_2 = False

    def set_discharge_current(self, current_a: float) -> None:
        """Set 4-bit discharge load configuration matching target current (0.0 - 3.0A)."""
        decimal_val = round(max(0.0, min(3.0, current_a)) / 0.2)
        self.discharge_load_1 = bool(decimal_val & 1)
        self.discharge_load_2 = bool(decimal_val & 2)
        self.discharge_load_3 = bool(decimal_val & 4)
        self.discharge_load_4 = bool(decimal_val & 8)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "name": self.name,
            "step_type": self.step_type.value,
            "max_charge_voltage": self.max_charge_voltage,
            "charge_current_1": self.charge_current_1,
            "charge_current_2": self.charge_current_2,
            "discharge_load_1": self.discharge_load_1,
            "discharge_load_2": self.discharge_load_2,
            "discharge_load_3": self.discharge_load_3,
            "discharge_load_4": self.discharge_load_4,
            "cell_select": self.cell_select,
            "cutoffs": [c.to_dict() for c in self.cutoffs],
            "loop_target_step": self.loop_target_step,
            "loop_count": self.loop_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TestStep:
        return cls(
            step_index=int(data.get("step_index", 1)),
            name=str(data.get("name", "Step")),
            step_type=StepType(data.get("step_type", StepType.REST.value)),
            max_charge_voltage=bool(data.get("max_charge_voltage", False)),
            charge_current_1=bool(data.get("charge_current_1", True)),
            charge_current_2=bool(data.get("charge_current_2", False)),
            discharge_load_1=bool(data.get("discharge_load_1", False)),
            discharge_load_2=bool(data.get("discharge_load_2", False)),
            discharge_load_3=bool(data.get("discharge_load_3", False)),
            discharge_load_4=bool(data.get("discharge_load_4", False)),
            cell_select=int(data.get("cell_select", 1)),
            cutoffs=[CutoffCondition.from_dict(c) for c in data.get("cutoffs", [])],
            loop_target_step=int(data.get("loop_target_step", 1)),
            loop_count=int(data.get("loop_count", 1)),
        )


@dataclass
class TestRecipe:
    __test__ = False
    recipe_name: str
    description: str = ""
    cell_nominal_capacity_mah: float = 3000.0
    steps: List[TestStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipe_name": self.recipe_name,
            "description": self.description,
            "cell_nominal_capacity_mah": self.cell_nominal_capacity_mah,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TestRecipe:
        return cls(
            recipe_name=str(data.get("recipe_name", "New Recipe")),
            description=str(data.get("description", "")),
            cell_nominal_capacity_mah=float(data.get("cell_nominal_capacity_mah", 3000.0)),
            steps=[TestStep.from_dict(s) for s in data.get("steps", [])],
        )

    def save_json(self, file_path: str | Path) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, file_path: str | Path) -> TestRecipe:
        path = Path(file_path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
