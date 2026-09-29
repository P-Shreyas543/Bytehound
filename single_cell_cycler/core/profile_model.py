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


@dataclass(frozen=True)
class ChemistryDef:
    """Cell chemistry electrical and safety bounds."""
    code: str
    name: str
    nominal_voltage: float
    min_voltage: float
    max_voltage: float
    max_charge_current: float
    max_discharge_current: float
    description: str


CHEMISTRY_PRESETS: Dict[str, ChemistryDef] = {
    "NMC": ChemistryDef(
        code="NMC",
        name="NMC / NCA (3.7V / 4.2V)",
        nominal_voltage=3.70,
        min_voltage=2.80,
        max_voltage=4.25,
        max_charge_current=2.5,
        max_discharge_current=3.0,
        description="Standard Li-ion (3.7V nom, 2.80V – 4.25V safe window)",
    ),
    "LFP": ChemistryDef(
        code="LFP",
        name="LFP / LiFePO4 (3.2V / 3.65V)",
        nominal_voltage=3.20,
        min_voltage=2.50,
        max_voltage=3.65,
        max_charge_current=2.5,
        max_discharge_current=3.0,
        description="High-safety LFP (3.2V nom, 2.50V – 3.65V safe window)",
    ),
    "LTO": ChemistryDef(
        code="LTO",
        name="LTO / Titanate (2.3V / 2.85V)",
        nominal_voltage=2.30,
        min_voltage=1.50,
        max_voltage=2.85,
        max_charge_current=3.0,
        max_discharge_current=3.0,
        description="Ultra-long life LTO (2.3V nom, 1.50V – 2.85V safe window)",
    ),
    "NA_ION": ChemistryDef(
        code="NA_ION",
        name="Sodium-ion / Na-ion (3.1V / 4.0V)",
        nominal_voltage=3.10,
        min_voltage=1.50,
        max_voltage=4.00,
        max_charge_current=2.0,
        max_discharge_current=3.0,
        description="Sodium-ion cell (3.1V nom, 1.50V – 4.00V safe window)",
    ),
    "CUSTOM": ChemistryDef(
        code="CUSTOM",
        name="Custom / Laboratory Unconstrained",
        nominal_voltage=3.60,
        min_voltage=0.50,
        max_voltage=5.00,
        max_charge_current=3.0,
        max_discharge_current=3.0,
        description="Laboratory custom profile (0.50V – 5.00V hardware limits)",
    ),
}


@dataclass
class TestRecipe:
    __test__ = False
    recipe_name: str
    description: str = ""
    cell_nominal_capacity_mah: float = 3000.0
    chemistry: str = "NMC"
    steps: List[TestStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipe_name": self.recipe_name,
            "description": self.description,
            "cell_nominal_capacity_mah": self.cell_nominal_capacity_mah,
            "chemistry": self.chemistry,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TestRecipe:
        return cls(
            recipe_name=str(data.get("recipe_name", "New Recipe")),
            description=str(data.get("description", "")),
            cell_nominal_capacity_mah=float(data.get("cell_nominal_capacity_mah", 3000.0)),
            chemistry=str(data.get("chemistry", "NMC")),
            steps=[TestStep.from_dict(s) for s in data.get("steps", [])],
        )

    def validate_chemistry_limits(self) -> List[str]:
        """Validate all step cutoffs and setpoints against selected cell chemistry boundaries.
        Returns a list of violation error strings (empty if all safe).
        """
        chem = CHEMISTRY_PRESETS.get(self.chemistry, CHEMISTRY_PRESETS["CUSTOM"])
        errors: List[str] = []
        for s in self.steps:
            # Check charge voltage hardware setpoint
            if s.step_type == StepType.CHARGE:
                if s.charge_voltage_target > chem.max_voltage:
                    errors.append(
                        f"Step {s.step_index} ('{s.name}'): Charge setpoint {s.charge_voltage_target:.2f}V "
                        f"exceeds {chem.code} safe max ({chem.max_voltage:.2f}V)"
                    )
                if s.charge_current_target > chem.max_charge_current:
                    errors.append(
                        f"Step {s.step_index} ('{s.name}'): Charge current {s.charge_current_target:.1f}A "
                        f"exceeds {chem.code} safe max ({chem.max_charge_current:.1f}A)"
                    )

            # Check discharge current hardware setpoint
            elif s.step_type == StepType.DISCHARGE:
                if s.discharge_current_target > chem.max_discharge_current:
                    errors.append(
                        f"Step {s.step_index} ('{s.name}'): Discharge current {s.discharge_current_target:.1f}A "
                        f"exceeds {chem.code} safe max ({chem.max_discharge_current:.1f}A)"
                    )

            # Check Cut-off Conditions
            for c in s.cutoffs:
                if not c.enabled:
                    continue
                if c.cutoff_type == CutoffType.VOLTAGE_MAX and c.threshold > chem.max_voltage:
                    errors.append(
                        f"Step {s.step_index} ('{s.name}'): Upper cutoff {c.threshold:.2f}V "
                        f"exceeds {chem.code} safe max ({chem.max_voltage:.2f}V)"
                    )
                elif c.cutoff_type == CutoffType.VOLTAGE_MIN and c.threshold < chem.min_voltage:
                    errors.append(
                        f"Step {s.step_index} ('{s.name}'): Lower cutoff {c.threshold:.2f}V "
                        f"is below {chem.code} safe min ({chem.min_voltage:.2f}V)"
                    )

        return errors

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
