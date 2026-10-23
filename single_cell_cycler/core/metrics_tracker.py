"""Real-time battery metrology, Coulomb counting, energy, and efficiency tracker."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..comm.packet_codec import CellDataTelemetry
from .dqv_analysis import DQVPeak, DQVProfile, compute_dq_dv, find_dqv_peaks
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
    # dQ/dV Peak Analysis (Option B)
    dqv_peak_voltage_v: Optional[float] = None     # Voltage of primary phase transition peak (V)
    dqv_peak_height_mah_v: Optional[float] = None  # Height of primary phase transition peak (mAh/V)
    dqv_peak_shift_mv: Optional[float] = None      # Voltage shift in mV relative to Cycle 1


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
        self.dqv_profiles: List[DQVProfile] = []

        # Buffer for dQ/dV curve computation (Option A + B)
        self._step_v_buf: List[float] = []
        self._step_q_buf: List[float] = []

        # Numerical integration state
        self._last_telemetry: Optional[CellDataTelemetry] = None
        self._last_time: Optional[float] = None

        # DCIR baseline capture
        self._dcir_v0: Optional[float] = None
        self._dcir_i0: Optional[float] = None
        self._dcir_captured_time: Optional[float] = None
        self._dcir_pulse_start_time: Optional[float] = None
        self._resting_v0: Optional[float] = None
        self._resting_i0: Optional[float] = None

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
        self._step_v_buf.clear()
        self._step_q_buf.clear()

        # Store baseline for DCIR estimation if moving to an active Charge/Discharge step
        if step_type in (StepType.CHARGE, StepType.DISCHARGE):
            if self._resting_v0 is not None:
                self._dcir_v0 = self._resting_v0
                self._dcir_i0 = self._resting_i0
            elif self._last_telemetry is not None:
                self._dcir_v0 = self._last_telemetry.voltage
                self._dcir_i0 = self._last_telemetry.current
            else:
                self._dcir_v0 = v_init
                self._dcir_i0 = 0.0
            self._dcir_captured_time = now
            init_i = initial_telemetry.current if initial_telemetry else 0.0
            if abs(init_i - (self._dcir_i0 or 0.0)) >= 0.1:
                self._dcir_pulse_start_time = now
            else:
                self._dcir_pulse_start_time = None
        else:
            self._dcir_v0 = None
            self._dcir_i0 = None
            self._dcir_captured_time = None
            self._dcir_pulse_start_time = None

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
                and self.current_step_metrics.step_type in (StepType.CHARGE, StepType.DISCHARGE)
            ):
                delta_i = abs(telemetry.current - self._dcir_i0)
                delta_v = abs(telemetry.voltage - self._dcir_v0)
                if delta_i >= 0.1:  # Minimum 100mA delta required for valid DCIR
                    if self._dcir_pulse_start_time is None:
                        self._dcir_pulse_start_time = now

                    elapsed_dcir = now - self._dcir_pulse_start_time
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
                        if self.current_step_metrics.dcir_mohm is None:
                            self.current_step_metrics.dcir_mohm = r_mohm

            # Buffer raw (V, Q) samples for Differential Capacity Analysis (dQ/dV vs V)
            if self.current_step_metrics.step_type in (StepType.CHARGE, StepType.DISCHARGE):
                self._step_v_buf.append(telemetry.voltage)
                self._step_q_buf.append(abs(self.current_step_metrics.capacity_mah))

        self._last_time = now
        self._last_telemetry = telemetry

    def complete_step(self, cutoff_reason: str) -> StepMetrics:
        """Mark active step as completed and archive in history."""
        now = self._last_time if self._last_time is not None else time.time()
        if self.current_step_metrics is not None:
            self.current_step_metrics.end_time = now
            self.current_step_metrics.duration_s = max(0.0, now - self.current_step_metrics.start_time)
            self.current_step_metrics.cutoff_reason = cutoff_reason

            # Record resting baseline when a REST step completes
            if self.current_step_metrics.step_type == StepType.REST:
                if self._last_telemetry is not None:
                    self._resting_v0 = self._last_telemetry.voltage
                    self._resting_i0 = self._last_telemetry.current
            else:
                self._resting_v0 = None
                self._resting_i0 = None

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

            # Compute Differential Capacity Curve (dQ/dV vs V) & Peak Detection (Option A + B)
            if (
                self.current_step_metrics.step_type in (StepType.CHARGE, StepType.DISCHARGE)
                and len(self._step_v_buf) >= 15
            ):
                try:
                    import numpy as np
                    v_arr = np.array(self._step_v_buf)
                    q_arr = np.array(self._step_q_buf)
                    v_grid, dqdv, q_grid = compute_dq_dv(
                        v_arr,
                        q_arr,
                        step_type=self.current_step_metrics.step_type.value,
                        return_capacity=True,
                    )
                    if len(v_grid) > 0:
                        pks = find_dqv_peaks(v_grid, dqdv)
                        prof = DQVProfile(
                            cycle_index=self.current_step_metrics.cycle_index,
                            step_index=self.current_step_metrics.step_index,
                            step_type=self.current_step_metrics.step_type.value,
                            voltages=v_grid,
                            dq_dv=dqdv,
                            capacities=q_grid,
                            peaks=pks,
                        )
                        self.dqv_profiles.append(prof)
                except Exception:
                    pass

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

        # Extract primary dQ/dV peak for this cycle (prefer Charge step, fallback to Discharge)
        cycle_dqv = [p for p in self.dqv_profiles if p.cycle_index == cycle_index and p.peaks]
        chg_dqv = next((p for p in cycle_dqv if "charge" in p.step_type.lower()), None)
        selected_dqv = chg_dqv if chg_dqv else (cycle_dqv[0] if cycle_dqv else None)

        pk_v = None
        pk_h = None
        shift_mv = None

        if selected_dqv and selected_dqv.peaks:
            primary_pk = max(selected_dqv.peaks, key=lambda pk: pk.prominence)
            pk_v = primary_pk.voltage
            pk_h = primary_pk.dq_dv

            # Reference Cycle 1 primary peak to track voltage shift (polarization/aging)
            c1_dqv = [
                p for p in self.dqv_profiles
                if p.cycle_index == 1 and p.peaks and p.step_type == selected_dqv.step_type
            ]
            if c1_dqv and c1_dqv[0].peaks:
                c1_primary = max(c1_dqv[0].peaks, key=lambda pk: pk.prominence)
                shift_mv = round((pk_v - c1_primary.voltage) * 1000.0, 1)
            elif cycle_index == 1:
                shift_mv = 0.0

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
            dqv_peak_voltage_v=pk_v,
            dqv_peak_height_mah_v=pk_h,
            dqv_peak_shift_mv=shift_mv,
        )
        self.cycle_summaries.append(summary)
        return summary
