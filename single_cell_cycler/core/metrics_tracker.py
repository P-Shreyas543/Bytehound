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
    dcir_1s_mohm: Optional[float] = None    # 1s pulse resistance (mOhm)
    dcir_10s_mohm: Optional[float] = None   # Standard 10s pulse resistance (mOhm, IEC 62660-1 / USABC)
    dcir_30s_mohm: Optional[float] = None   # 30s pulse resistance (mOhm)
    dcir_mohm: Optional[float] = None       # Primary/representative pulse resistance (mOhm)
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
    dcir_1s_mohm: Optional[float] = None
    dcir_10s_mohm: Optional[float] = None
    dcir_mohm: Optional[float] = None


@dataclass
class DCIRMeasurement:
    """Standardized pulse resistance measurement record (IEC 62660-1 / USABC)."""
    timestamp: float
    cycle_index: int
    step_index: int
    step_name: str
    step_type: StepType
    baseline_voltage: float
    baseline_current: float
    pulse_current: float
    delta_current: float
    r_1s_mohm: Optional[float] = None
    r_10s_mohm: Optional[float] = None
    r_30s_mohm: Optional[float] = None


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
        self.dcir_measurements: List[DCIRMeasurement] = []

        # Numerical integration state
        self._last_telemetry: Optional[CellDataTelemetry] = None
        self._last_time: Optional[float] = None

        # DCIR baseline capture
        self._dcir_v0: Optional[float] = None
        self._dcir_i0: Optional[float] = None
        self._dcir_captured_time: Optional[float] = None

    def restore_state(
        self,
        total_test_start_time: float,
        cumulative_charge_mah: float,
        cumulative_discharge_mah: float,
        cumulative_charge_mwh: float,
        cumulative_discharge_mwh: float,
        current_cycle_index: int,
        step_history: List[StepMetrics],
        cycle_summaries: List[CycleSummary],
    ) -> None:
        """Restore integrated test metrics from crash journal (IMP-08)."""
        self.total_test_start_time = total_test_start_time
        self.cumulative_charge_mah = cumulative_charge_mah
        self.cumulative_discharge_mah = cumulative_discharge_mah
        self.cumulative_charge_mwh = cumulative_charge_mwh
        self.cumulative_discharge_mwh = cumulative_discharge_mwh
        self.current_cycle_index = current_cycle_index
        self.step_history = list(step_history)
        self.cycle_summaries = list(cycle_summaries)
        self.current_step_metrics = None
        self._last_telemetry = None
        self._last_time = None

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

            # Standardized Pulse DCIR measurement (IEC 62660-1 / USABC)
            if (
                self._dcir_v0 is not None
                and self._dcir_i0 is not None
                and self._dcir_captured_time is not None
            ):
                elapsed_dcir = now - self._dcir_captured_time
                delta_i = abs(telemetry.current - self._dcir_i0)
                delta_v = abs(telemetry.voltage - self._dcir_v0)
                if delta_i >= 0.1:  # Minimum 100mA delta required for valid DCIR
                    r_ohms = delta_v / delta_i
                    r_mohm = round(r_ohms * 1000.0, 2)

                    # 1s pulse resistance (0.7s - 1.3s)
                    if 0.7 <= elapsed_dcir <= 1.3 and self.current_step_metrics.dcir_1s_mohm is None:
                        self.current_step_metrics.dcir_1s_mohm = r_mohm
                        if self.current_step_metrics.dcir_mohm is None:
                            self.current_step_metrics.dcir_mohm = r_mohm

                    # Standard 10s pulse resistance (9.5s - 10.5s, IEC 62660-1 / USABC)
                    if 9.5 <= elapsed_dcir <= 10.5 and self.current_step_metrics.dcir_10s_mohm is None:
                        self.current_step_metrics.dcir_10s_mohm = r_mohm
                        self.current_step_metrics.dcir_mohm = r_mohm  # Standard 10s replaces 1s as primary metric

                    # 30s pulse resistance (29.0s - 31.0s)
                    if 29.0 <= elapsed_dcir <= 31.0 and self.current_step_metrics.dcir_30s_mohm is None:
                        self.current_step_metrics.dcir_30s_mohm = r_mohm

        self._last_time = now
        self._last_telemetry = telemetry

    def complete_step(self, cutoff_reason: str) -> StepMetrics:
        """Mark active step as completed and archive in history."""
        now = self._last_time if self._last_time is not None else time.time()
        if self.current_step_metrics is not None:
            self.current_step_metrics.end_time = now
            self.current_step_metrics.duration_s = max(0.0, now - self.current_step_metrics.start_time)
            self.current_step_metrics.cutoff_reason = cutoff_reason

            # Record DCIR measurement if captured during this step
            if (
                self.current_step_metrics.dcir_1s_mohm is not None
                or self.current_step_metrics.dcir_10s_mohm is not None
                or self.current_step_metrics.dcir_mohm is not None
            ):
                meas = DCIRMeasurement(
                    timestamp=now,
                    cycle_index=self.current_step_metrics.cycle_index,
                    step_index=self.current_step_metrics.step_index,
                    step_name=self.current_step_metrics.step_name,
                    step_type=self.current_step_metrics.step_type,
                    baseline_voltage=self._dcir_v0 or 0.0,
                    baseline_current=self._dcir_i0 or 0.0,
                    pulse_current=self.current_step_metrics.peak_current,
                    delta_current=abs(self.current_step_metrics.peak_current - (self._dcir_i0 or 0.0)),
                    r_1s_mohm=self.current_step_metrics.dcir_1s_mohm,
                    r_10s_mohm=self.current_step_metrics.dcir_10s_mohm,
                    r_30s_mohm=self.current_step_metrics.dcir_30s_mohm,
                )
                self.dcir_measurements.append(meas)

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

        # Grab standard DCIR if measured in any step of this cycle
        dcir_10s = next((s.dcir_10s_mohm for s in cycle_steps if s.dcir_10s_mohm is not None), None)
        dcir_1s = next((s.dcir_1s_mohm for s in cycle_steps if s.dcir_1s_mohm is not None), None)
        dcir_fallback = next((s.dcir_mohm for s in cycle_steps if s.dcir_mohm is not None), None)
        dcir_val = dcir_10s if dcir_10s is not None else (dcir_1s if dcir_1s is not None else dcir_fallback)

        summary = CycleSummary(
            cycle_index=cycle_index,
            charge_capacity_mah=round(q_chg, 2),
            discharge_capacity_mah=round(q_dis, 2),
            charge_energy_mwh=round(e_chg, 2),
            discharge_energy_mwh=round(e_dis, 2),
            coulombic_efficiency_pct=round(coulombic_eff, 2),
            energy_efficiency_pct=round(energy_eff, 2),
            duration_s=round(duration, 1),
            dcir_1s_mohm=dcir_1s,
            dcir_10s_mohm=dcir_10s,
            dcir_mohm=dcir_val,
        )
        self.cycle_summaries.append(summary)
        return summary
