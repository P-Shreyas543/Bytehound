"""Real-time battery metrology, Coulomb counting, energy, and efficiency tracker."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..comm.packet_codec import CellDataTelemetry
from .profile_model import StepType


@dataclass
class StepMetrics:
    cycle_index: int
    step_index: int
    step_name: str
    step_type: StepType
    start_time: float
    end_time: float = 0.0
    duration_s: float = 0.0
    start_voltage: float = 0.0
    end_voltage: float = 0.0
    peak_current: float = 0.0
    peak_temp: float = 0.0
    capacity_mah: float = 0.0       # Net charge/discharge capacity in this step
    energy_mwh: float = 0.0         # Net energy in this step
    dcir_mohm: Optional[float] = None
    cutoff_reason: str = ""


@dataclass
class CycleSummary:
    cycle_index: int
    charge_capacity_mah: float = 0.0
    discharge_capacity_mah: float = 0.0
    charge_energy_mwh: float = 0.0
    discharge_energy_mwh: float = 0.0
    coulombic_efficiency_pct: float = 0.0
    energy_efficiency_pct: float = 0.0
    duration_s: float = 0.0
    dcir_mohm: Optional[float] = None


class MetricsTracker:
    """Manages integration of capacity, energy, efficiency, and resistance."""

    def __init__(self):
        self.reset_all()

    def reset_all(self) -> None:
        self.total_test_start_time = time.time()
        self.cumulative_charge_mah = 0.0
        self.cumulative_discharge_mah = 0.0
        self.cumulative_charge_mwh = 0.0
        self.cumulative_discharge_mwh = 0.0

        self.current_cycle_index = 1
        self.current_step_metrics: Optional[StepMetrics] = None
        self.step_history: List[StepMetrics] = []
        self.cycle_summaries: List[CycleSummary] = []

        # Numerical integration state
        self._last_telemetry: Optional[CellDataTelemetry] = None
        self._last_time: Optional[float] = None

        # DCIR baseline capture
        self._dcir_v0: Optional[float] = None
        self._dcir_i0: Optional[float] = None
        self._dcir_captured_time: Optional[float] = None

    def start_step(self, cycle_index: int, step_index: int, step_name: str, step_type: StepType, initial_telemetry: Optional[CellDataTelemetry] = None) -> None:
        now = initial_telemetry.timestamp if (initial_telemetry and initial_telemetry.timestamp > 0) else time.time()
        v_init = initial_telemetry.voltage if initial_telemetry else 0.0
        t_init = max(initial_telemetry.body_temp, initial_telemetry.terminal_temp) if initial_telemetry else 0.0

        self.current_step_metrics = StepMetrics(
            cycle_index=cycle_index,
            step_index=step_index,
            step_name=step_name,
            step_type=step_type,
            start_time=now,
            start_voltage=v_init,
            end_voltage=v_init,
            peak_temp=t_init,
        )
        self.current_cycle_index = cycle_index

        # Store baseline for DCIR estimation if moving from Rest to active step
        if self._last_telemetry is not None:
            self._dcir_v0 = self._last_telemetry.voltage
            self._dcir_i0 = self._last_telemetry.current
            self._dcir_captured_time = now

        self._last_time = now
        self._last_telemetry = initial_telemetry

    def update(self, telemetry: CellDataTelemetry) -> None:
        """Called for every incoming telemetry frame to integrate Ah and Wh."""
        now = telemetry.timestamp if telemetry.timestamp > 0 else time.time()

        if self.current_step_metrics is not None:
            if self.current_step_metrics.start_time == 0.0:
                self.current_step_metrics.start_time = now

            if self._last_telemetry is not None and self._last_time is not None:
                dt_s = now - self._last_time
                if 0 < dt_s <= 3600.0:
                    # Trapezoidal integration for Current: (I0 + I1) / 2 * dt
                    avg_i = (self._last_telemetry.current + telemetry.current) / 2.0
                    d_mah = (avg_i * dt_s / 3600.0) * 1000.0

                    # Trapezoidal integration for Power: (V0*I0 + V1*I1) / 2 * dt
                    p0 = self._last_telemetry.voltage * self._last_telemetry.current
                    p1 = telemetry.voltage * telemetry.current
                    avg_p = (p0 + p1) / 2.0
                    d_mwh = (avg_p * dt_s / 3600.0) * 1000.0

                    self.current_step_metrics.capacity_mah += d_mah
                    self.current_step_metrics.energy_mwh += d_mwh

                    if d_mah > 0:
                        self.cumulative_charge_mah += d_mah
                        self.cumulative_charge_mwh += d_mwh
                    else:
                        self.cumulative_discharge_mah += abs(d_mah)
                        self.cumulative_discharge_mwh += abs(d_mwh)

            # Update step tracking bounds
            self.current_step_metrics.end_voltage = telemetry.voltage
            self.current_step_metrics.duration_s = max(0.0, now - self.current_step_metrics.start_time)
            self.current_step_metrics.peak_current = max(self.current_step_metrics.peak_current, abs(telemetry.current))
            self.current_step_metrics.peak_temp = max(
                self.current_step_metrics.peak_temp,
                telemetry.body_temp,
                telemetry.terminal_temp,
            )

            # DCIR check at ~0.5s - 1.0s after step onset
            if (
                self._dcir_v0 is not None
                and self._dcir_i0 is not None
                and self._dcir_captured_time is not None
                and self.current_step_metrics.dcir_mohm is None
            ):
                elapsed_dcir = now - self._dcir_captured_time
                if 0.5 <= elapsed_dcir <= 1.5:
                    delta_i = abs(telemetry.current - self._dcir_i0)
                    delta_v = abs(telemetry.voltage - self._dcir_v0)
                    if delta_i >= 0.2:  # Minimum 200mA delta required for valid DCIR
                        r_ohms = delta_v / delta_i
                        self.current_step_metrics.dcir_mohm = round(r_ohms * 1000.0, 2)

        self._last_time = now
        self._last_telemetry = telemetry

    def complete_step(self, cutoff_reason: str) -> StepMetrics:
        """Mark active step as completed and archive in history."""
        now = self._last_time if self._last_time is not None else time.time()
        if self.current_step_metrics is not None:
            self.current_step_metrics.end_time = now
            self.current_step_metrics.duration_s = max(0.0, now - self.current_step_metrics.start_time)
            self.current_step_metrics.cutoff_reason = cutoff_reason
            self.step_history.append(self.current_step_metrics)
            finished_step = self.current_step_metrics
            self.current_step_metrics = None
            return finished_step
        
        # Fallback dummy step
        return StepMetrics(
            cycle_index=self.current_cycle_index,
            step_index=0,
            step_name="Done",
            step_type=StepType.REST,
            start_time=now,
            end_time=now,
        )

    def compute_cycle_summary(self, cycle_index: int) -> CycleSummary:
        """Aggregate all steps belonging to cycle_index and compute efficiencies."""
        cycle_steps = [s for s in self.step_history if s.cycle_index == cycle_index]
        q_chg = sum(abs(s.capacity_mah) for s in cycle_steps if s.step_type == StepType.CHARGE)
        q_dis = sum(abs(s.capacity_mah) for s in cycle_steps if s.step_type == StepType.DISCHARGE)
        e_chg = sum(abs(s.energy_mwh) for s in cycle_steps if s.step_type == StepType.CHARGE)
        e_dis = sum(abs(s.energy_mwh) for s in cycle_steps if s.step_type == StepType.DISCHARGE)
        duration = sum(s.duration_s for s in cycle_steps)

        coulombic_eff = (q_dis / q_chg * 100.0) if q_chg > 0 else 0.0
        energy_eff = (e_dis / e_chg * 100.0) if e_chg > 0 else 0.0

        # Grab DCIR if measured in any discharge step
        dcir_val = next((s.dcir_mohm for s in cycle_steps if s.dcir_mohm is not None), None)

        summary = CycleSummary(
            cycle_index=cycle_index,
            charge_capacity_mah=round(q_chg, 2),
            discharge_capacity_mah=round(q_dis, 2),
            charge_energy_mwh=round(e_chg, 2),
            discharge_energy_mwh=round(e_dis, 2),
            coulombic_efficiency_pct=round(coulombic_eff, 2),
            energy_efficiency_pct=round(energy_eff, 2),
            duration_s=round(duration, 1),
            dcir_mohm=dcir_val,
        )
        self.cycle_summaries.append(summary)
        return summary
