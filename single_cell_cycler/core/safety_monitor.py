"""Continuous safety monitor, BMS fault detector, and emergency shutoff dispatcher."""

from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from ..comm.packet_codec import CellDataTelemetry, FaultSoCTelemetry
from ..comm.protocol_defs import (
    ALL_CONTROL_FRAMES,
    FRAME_CHARGE_CTRL,
    FRAME_CHARGE_SEL,
    FRAME_DISCHARGE_CTRL,
    FRAME_DISCHARGE_SEL,
    FRAME_RELAY_CTRL,
    RelayControlBits,
    BMSFaultFlags,
    FAULT_LABELS,
)

logger = logging.getLogger("SingleCellCycler.SafetyMonitor")


@dataclass
class SafetyLimits:
    max_voltage_v: float = 4.250          # Absolute upper cell voltage limit
    min_voltage_v: float = 2.400          # Absolute lower cell voltage limit
    max_charge_current_a: float = 6.0     # Max charge current limit
    max_discharge_current_a: float = 25.0 # Max discharge current limit
    max_temp_c: float = 60.0              # Max safe temperature limit

    # Rate-of-Rise Thermal Trigger (IMP-09)
    max_temp_rate_of_rise_c_per_min: float = 1.5  # Max safe rate of rise (dT/dt in °C/min)
    temp_rate_window_s: float = 15.0              # Moving window duration for slope calculation (s)
    temp_rate_sustain_s: float = 2.5              # Duration condition must be sustained before trip (s)

    # Watchdog timeout: how long with no telemetry before triggering safety stop.
    # Set conservatively to 8 s to account for:
    #   - Windows CP210x USB driver frame-drop gaps (can be 1-3 s)
    #   - MCU comparator reset latency (~200-500 ms per reset)
    #   - CC→CV transition firmware pause (up to ~1 s)
    # The start-test pre-flight check already enforces < 3 s before allowing START.
    watchdog_timeout_s: float = 8.0


class SafetyMonitor:
    """Monitors telemetry for BMS faults and software safety limits."""

    def __init__(
        self,
        command_sender: Callable[[int, int, int], None],
        limits: Optional[SafetyLimits] = None,
    ):
        """command_sender: callable taking (frame_id, payload_byte, priority)"""
        self._command_sender = command_sender
        self.limits = limits or SafetyLimits()

        self.is_tripped = False
        self.trip_reason = ""
        self.last_telemetry_time = time.time()
        self.active_faults: list[str] = []
        self.selected_cell: int = 1

        # Rate-of-rise thermal runaway detection (IMP-09)
        self._temp_history: collections.deque = collections.deque(maxlen=300)
        self._rate_trip_start_time: Optional[float] = None
        self.last_rate_of_rise_c_per_min: float = 0.0

    def check_telemetry(self, cell_data: CellDataTelemetry) -> bool:
        """Verify cell data against software safety guardrails.
        
        Returns True if safe, False if tripped.
        """
        now = time.time()
        self.last_telemetry_time = now

        if self.is_tripped:
            return False

        # 1. Overvoltage limit
        if cell_data.voltage > self.limits.max_voltage_v:
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell Voltage {cell_data.voltage:.3f} V exceeded safety limit {self.limits.max_voltage_v:.3f} V"
            )
            return False

        # 2. Undervoltage limit
        if cell_data.voltage < self.limits.min_voltage_v:
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell Voltage {cell_data.voltage:.3f} V dropped below safety limit {self.limits.min_voltage_v:.3f} V"
            )
            return False

        # 3. Overcurrent limits
        if cell_data.current > self.limits.max_charge_current_a:
            self._trigger_shutdown(
                f"SAFETY TRIP: Charge current {cell_data.current:.3f} A exceeded limit {self.limits.max_charge_current_a:.3f} A"
            )
            return False

        if abs(cell_data.current) > self.limits.max_discharge_current_a and cell_data.current < 0:
            self._trigger_shutdown(
                f"SAFETY TRIP: Discharge current {abs(cell_data.current):.3f} A exceeded limit {self.limits.max_discharge_current_a:.3f} A"
            )
            return False

        # 4. Temperature absolute limit
        max_temp = max(cell_data.body_temp, cell_data.terminal_temp)
        if max_temp > self.limits.max_temp_c:
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell temperature {max_temp:.1f} °C exceeded limit {self.limits.max_temp_c:.1f} °C"
            )
            return False

        # 5. Temperature rate-of-rise limit (dT/dt) early runaway trigger (IMP-09)
        t_sample = cell_data.timestamp if cell_data.timestamp > 0 else now
        self._temp_history.append((t_sample, max_temp))

        # Purge samples older than temp_rate_window_s * 1.5
        min_cutoff = t_sample - (self.limits.temp_rate_window_s * 1.5)
        while len(self._temp_history) > 1 and self._temp_history[0][0] < min_cutoff:
            self._temp_history.popleft()

        # Evaluate slope if we have at least 5.0 seconds of history in the window
        earliest_t, earliest_temp = self._temp_history[0]
        dt = t_sample - earliest_t
        if dt >= 5.0:
            dT = max_temp - earliest_temp
            rate_c_per_min = (dT / dt) * 60.0
            self.last_rate_of_rise_c_per_min = rate_c_per_min

            if rate_c_per_min >= self.limits.max_temp_rate_of_rise_c_per_min:
                if self._rate_trip_start_time is None:
                    self._rate_trip_start_time = t_sample
                elif (t_sample - self._rate_trip_start_time) >= self.limits.temp_rate_sustain_s:
                    self._trigger_shutdown(
                        f"SAFETY TRIP: Rate of temperature rise exceeded limit: {rate_c_per_min:.2f} °C/min "
                        f"(limit: {self.limits.max_temp_rate_of_rise_c_per_min:.2f} °C/min sustained for {self.limits.temp_rate_sustain_s:.1f}s)"
                    )
                    return False
            else:
                self._rate_trip_start_time = None

        return True

    def check_bms_faults(
        self,
        fault_soc: FaultSoCTelemetry,
        active_step_type: Optional[str] = None,
        cell_voltage: Optional[float] = None,
        is_transitioning: bool = False,
    ) -> bool:
        """Scan Frame 0x3000 fault flags.
        
        Returns True if safe, False if tripped.
        Contextual tolerance:
        - During Step Transitions: Comparator flags (OCC, OCD, COV, CUV) are actively being
          sequenced and reset via hardware pulses; only thermal emergencies (COT, CUT) trip.
        - During Charge or Rest above min_voltage_v (2.4V): CUV (Under Voltage) is expected
          post-discharge comparator hysteresis and does not trip safety.
        - During Discharge: COV (Over Voltage) is expected at high initial SoC.
        - During Rest: OCC and OCD are suppressed because current is physically 0 A; any
          tripped comparator bits reflect un-cleared latches or turn-off transients.
        """
        if self.is_tripped:
            return False

        self.last_telemetry_time = time.time()
        self.active_faults.clear()

        step_type_str = str(active_step_type).lower() if active_step_type else ""

        for flag, label in FAULT_LABELS.items():
            if fault_soc.fault_byte & flag:
                # During step transitions, comparator resets (0->1->0) and relay switches are in progress.
                # Suppress comparator latches so we do not flood emergency shutdown commands.
                if is_transitioning and flag in (
                    BMSFaultFlags.OCC,
                    BMSFaultFlags.OCD,
                    BMSFaultFlags.COV,
                    BMSFaultFlags.CUV,
                ):
                    continue

                # Handle comparator hysteresis during normal transitions
                if flag == BMSFaultFlags.CUV:
                    if "charge" in step_type_str:
                        continue  # Expected while recovering from low voltage
                    if "rest" in step_type_str and (cell_voltage is None or cell_voltage >= self.limits.min_voltage_v):
                        continue  # Expected post-discharge relaxation above 2.4V
                elif flag == BMSFaultFlags.COV:
                    if "discharge" in step_type_str:
                        continue  # Expected at start of discharge from 4.2V
                elif flag in (BMSFaultFlags.OCC, BMSFaultFlags.OCD):
                    if "rest" in step_type_str:
                        continue  # Zero current in rest; ignore un-cleared comparator latches

                self.active_faults.append(label)

        if self.active_faults and not self.is_tripped:
            fault_str = ", ".join(self.active_faults)
            self._trigger_shutdown(f"HARDWARE BMS FAULT DETECTED: {fault_str}")
            return False

        return True

    def check_watchdog(self) -> bool:
        """Verify communications heartbeat.

        Returns True if alive, False if watchdog timeout expired.
        The timeout is intentionally generous (8 s) to survive CP210x USB
        driver gaps and MCU comparator reset pauses without false-tripping.
        """
        if self.is_tripped:
            return False

        elapsed = time.time() - self.last_telemetry_time
        if elapsed > self.limits.watchdog_timeout_s:
            self._trigger_shutdown(
                f"COMMUNICATION WATCHDOG TIMEOUT: No telemetry received for "
                f"{elapsed:.1f} s (limit: {self.limits.watchdog_timeout_s:.0f} s). "
                f"Check USB connection and MCU power."
            )
            return False

        return True

    def emergency_stop(self) -> None:
        """Manual Emergency Stop invoked by user."""
        self._trigger_shutdown("MANUAL EMERGENCY STOP TRIGGERED BY OPERATOR")

    def reset_safety(self) -> None:
        """Clear tripped status after issue resolution."""
        self.is_tripped = False
        self.trip_reason = ""
        self.active_faults.clear()
        self.last_telemetry_time = time.time()
        self._temp_history.clear()
        self._rate_trip_start_time = None
        self.last_rate_of_rise_c_per_min = 0.0

    def _trigger_shutdown(self, reason: str) -> None:
        """Execute hardware safe-state shutdown with priority 0."""
        self.is_tripped = True
        self.trip_reason = reason
        logger.critical(f"Executing Emergency Safety Shutdown: {reason}")

        try:
            # Safely de-energize active charge/discharge controls with Priority 0
            self._command_sender(FRAME_CHARGE_CTRL, 0x00, 0)
            self._command_sender(FRAME_DISCHARGE_CTRL, 0x00, 0)
            self._command_sender(FRAME_CHARGE_SEL, 0x00, 0)
            self._command_sender(FRAME_DISCHARGE_SEL, 0x00, 0)
            # De-energize cell enable while preserving selected cell position
            relay_idle = int(RelayControlBits.CELL_SELECT) if self.selected_cell == 2 else 0x00
            self._command_sender(FRAME_RELAY_CTRL, relay_idle, 0)
        except Exception as exc:
            logger.error(f"Error during emergency shutdown commands: {exc}")
