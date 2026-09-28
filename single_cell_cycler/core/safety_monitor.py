"""Continuous safety monitor, BMS fault detector, and emergency shutoff dispatcher."""

from __future__ import annotations

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
    BMSFaultFlags,
    FAULT_LABELS,
)

logger = logging.getLogger("SingleCellCycler.SafetyMonitor")


@dataclass
class SafetyLimits:
    max_voltage_v: float = 4.250       # Absolute upper cell voltage limit
    min_voltage_v: float = 2.400       # Absolute lower cell voltage limit
    max_charge_current_a: float = 6.0  # Max charge current limit
    max_discharge_current_a: float = 25.0 # Max discharge current limit
    max_temp_c: float = 60.0           # Max safe temperature limit
    watchdog_timeout_s: float = 3.0    # Comm timeout before safety stop


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

        # 4. Temperature limit
        max_temp = max(cell_data.body_temp, cell_data.terminal_temp)
        if max_temp > self.limits.max_temp_c:
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell temperature {max_temp:.1f} °C exceeded limit {self.limits.max_temp_c:.1f} °C"
            )
            return False

        return True

    def check_bms_faults(self, fault_soc: FaultSoCTelemetry) -> bool:
        """Scan Frame 0x3000 fault flags.
        
        Returns True if safe, False if tripped.
        """
        self.last_telemetry_time = time.time()
        self.active_faults.clear()

        for flag, label in FAULT_LABELS.items():
            if fault_soc.fault_byte & flag:
                self.active_faults.append(label)

        if self.active_faults and not self.is_tripped:
            fault_str = ", ".join(self.active_faults)
            self._trigger_shutdown(f"HARDWARE BMS FAULT DETECTED: {fault_str}")
            return False

        return True

    def check_watchdog(self) -> bool:
        """Verify communications heartbeat.
        
        Returns True if alive, False if watchdog timeout.
        """
        if self.is_tripped:
            return False

        elapsed = time.time() - self.last_telemetry_time
        if elapsed > self.limits.watchdog_timeout_s:
            self._trigger_shutdown(f"COMMUNICATION WATCHDOG: No telemetry for {elapsed:.1f} s")
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

    def _trigger_shutdown(self, reason: str) -> None:
        """Execute hardware safe-state shutdown with priority 0."""
        self.is_tripped = True
        self.trip_reason = reason
        logger.critical(f"Executing Emergency Safety Shutdown: {reason}")

        try:
            # Safely de-energize all 5 control registers (0x6000 - 0x6004) with Priority 0
            for frame_id in ALL_CONTROL_FRAMES:
                self._command_sender(frame_id, 0x00, 0)
        except Exception as exc:
            logger.error(f"Error during emergency shutdown commands: {exc}")
