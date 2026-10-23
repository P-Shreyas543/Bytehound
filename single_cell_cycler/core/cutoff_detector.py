"""Deterministic cut-off condition evaluation engine for single-cell cycler."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from ..comm.packet_codec import CellDataTelemetry
from .profile_model import CutoffCondition, CutoffType, TestStep

logger = logging.getLogger("SingleCellCycler.CutoffDetector")


@dataclass(slots=True)
class CutoffResult:
    is_triggered: bool
    trigger_reason: str
    condition: Optional[CutoffCondition] = None


class CutoffDetector:
    """Evaluates active step cutoffs against incoming telemetry and step progress."""

    def __init__(self, current_taper_arming_delay_s: float = 3.0):
        self.arming_delay_s = current_taper_arming_delay_s

    def evaluate(
        self,
        step: TestStep,
        telemetry: CellDataTelemetry,
        step_elapsed_time_s: float,
        step_capacity_mah: float,
        comparator_tripped: bool = False,
    ) -> CutoffResult:
        """Check all enabled cut-off conditions for the active step.
        
        Returns CutoffResult with is_triggered=True and human-readable reason.
        """
        has_taper_cutoff = any(
            c.cutoff_type == CutoffType.CURRENT_MIN and c.enabled for c in step.cutoffs
        )

        for cond in step.cutoffs:
            if not cond.enabled:
                continue

            # 1. Voltage Upper Cutoff (e.g. 4.20 V during charge)
            # When current taper cut-off is also enabled, voltage reaching the target marks the CV phase entry,
            # so the step continues until current tapers rather than ending immediately at full current.
            if cond.cutoff_type == CutoffType.VOLTAGE_MAX:
                if not has_taper_cutoff and telemetry.voltage >= cond.threshold:
                    return CutoffResult(
                        is_triggered=True,
                        trigger_reason=f"Voltage reached {telemetry.voltage:.3f} V >= target {cond.threshold:.3f} V",
                        condition=cond,
                    )

            # 2. Voltage Lower Cutoff (e.g. 2.80 V during discharge)
            elif cond.cutoff_type == CutoffType.VOLTAGE_MIN:
                if telemetry.voltage <= cond.threshold:
                    return CutoffResult(
                        is_triggered=True,
                        trigger_reason=f"Voltage reached {telemetry.voltage:.3f} V <= target {cond.threshold:.3f} V",
                        condition=cond,
                    )

            # 3. Current Taper / Cutoff (e.g. <= 0.18 A during CV phase)
            elif cond.cutoff_type == CutoffType.CURRENT_MIN:
                has_v_max = any(c.cutoff_type == CutoffType.VOLTAGE_MAX and c.enabled for c in step.cutoffs)
                v_max_thresh = next(
                    (c.threshold for c in step.cutoffs if c.cutoff_type == CutoffType.VOLTAGE_MAX and c.enabled),
                    None,
                )
                is_armed = False
                if has_v_max and v_max_thresh is not None:
                    # Armed when voltage is near CV regulation setpoint (within 0.05V) and arming delay has passed
                    if telemetry.voltage >= (v_max_thresh - 0.05) and step_elapsed_time_s >= self.arming_delay_s:
                        is_armed = True
                else:
                    if step_elapsed_time_s >= self.arming_delay_s:
                        is_armed = True

                if is_armed:
                    current_mag = abs(telemetry.current)
                    if current_mag <= cond.threshold:
                        return CutoffResult(
                            is_triggered=True,
                            trigger_reason=f"Current tapered to {telemetry.current:.3f} A <= target {cond.threshold:.3f} A",
                            condition=cond,
                        )

            # 4. Overcurrent Cutoff
            elif cond.cutoff_type == CutoffType.CURRENT_MAX:
                current_mag = abs(telemetry.current)
                if current_mag >= cond.threshold:
                    return CutoffResult(
                        is_triggered=True,
                        trigger_reason=f"Current exceeded {telemetry.current:.3f} A >= limit {cond.threshold:.3f} A",
                        condition=cond,
                    )

            # 5. Step Duration Cutoff
            elif cond.cutoff_type == CutoffType.DURATION_MAX:
                if step_elapsed_time_s >= cond.threshold:
                    return CutoffResult(
                        is_triggered=True,
                        trigger_reason=f"Step duration {step_elapsed_time_s:.1f} s >= limit {cond.threshold:.1f} s",
                        condition=cond,
                    )

            # 6. Step Capacity Cutoff
            elif cond.cutoff_type == CutoffType.CAPACITY_MAX:
                if abs(step_capacity_mah) >= cond.threshold:
                    return CutoffResult(
                        is_triggered=True,
                        trigger_reason=f"Step capacity {abs(step_capacity_mah):.1f} mAh >= target {cond.threshold:.1f} mAh",
                        condition=cond,
                    )

            # 7. Temperature Cutoff
            elif cond.cutoff_type == CutoffType.TEMP_MAX:
                max_temp = max(telemetry.body_temp, telemetry.terminal_temp)
                if max_temp >= cond.threshold:
                    return CutoffResult(
                        is_triggered=True,
                        trigger_reason=f"Cell temperature reached {max_temp:.1f} °C >= safety limit {cond.threshold:.1f} °C",
                        condition=cond,
                    )

            # 8. Hardware Comparator Trip
            elif cond.cutoff_type == CutoffType.COMPARATOR_TRIP:
                if comparator_tripped:
                    return CutoffResult(
                        is_triggered=True,
                        trigger_reason="Hardware comparator tripped on BMS board",
                        condition=cond,
                    )

        return CutoffResult(is_triggered=False, trigger_reason="")
