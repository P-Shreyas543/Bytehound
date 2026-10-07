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

    # Outside [min_voltage_v, max_voltage_v] a step that cannot make it worse is allowed to run:
    # a charge (or rest) below the minimum, a discharge (or rest) above the maximum. Past these
    # hard limits the test stops and latches instead: charging a deeply over-discharged Li-ion
    # cell at full current risks copper dissolution and internal shorts.
    charge_floor_v: float = 2.0           # no charging below this (set per chemistry at START)
    overvoltage_ceiling_margin_v: float = 0.10  # hard ceiling = max_voltage_v + margin

    # Rate-of-Rise Thermal Trigger (IMP-09); operator switch in cycler_settings.json "safety".
    # Off leaves the absolute max_temp_c trip and the BMS COT flag.
    temp_rate_enabled: bool = True
    max_temp_rate_of_rise_c_per_min: float = 1.5  # Max safe rate of rise (dT/dt in °C/min)
    temp_rate_window_s: float = 15.0              # Moving window duration for slope calculation (s)
    temp_rate_sustain_s: float = 2.5              # Duration condition must be sustained before trip (s)
    temp_rate_max_gap_s: float = 2.0              # Telemetry gap that restarts the window (connect, reconnect, stall)

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
        # Returns the latest 0x6000 readback; set by the engine so shutdown never moves Select under a closed Enable
        self.relay_readback: Optional[Callable[[], int]] = None
        # When False, trips are recorded but no hardware writes are sent (engine not Running:
        # hardware is already zeroed and the confirmed sequences own the registers)
        self.armed: bool = True
        # Class of the last trip: voltage | voltage_hard | current | thermal | watchdog | manual
        # ("voltage" ends the step and the test continues; every other class stops the test)
        self.trip_kind: str = ""
        # Type of the step the engine is running ("charge" / "discharge" / "rest"), or None
        self.active_step_type: Optional[str] = None

        # Rate-of-rise thermal runaway detection (IMP-09)
        # Bounded by the time purge; maxlen is only a backstop, large enough for one window at
        # any realistic frame rate (300 would cover just 15 s at 20 Hz and the slope would never run)
        self._temp_history: collections.deque = collections.deque(maxlen=5000)
        self._rate_history_start: Optional[float] = None   # first sample since the last reset / gap
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

        # 1-2. Voltage limits. A step that moves the cell back into range is allowed to run;
        # the hard floor / ceiling always stop the test (see SafetyLimits.charge_floor_v)
        v = cell_data.voltage
        step = (self.active_step_type or "").lower()
        ceiling = self.limits.max_voltage_v + self.limits.overvoltage_ceiling_margin_v
        if v > ceiling:
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell Voltage {v:.3f} V above hard ceiling {ceiling:.3f} V",
                kind="voltage_hard",
            )
            return False
        if v > self.limits.max_voltage_v and step not in ("discharge", "rest"):
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell Voltage {v:.3f} V exceeded safety limit {self.limits.max_voltage_v:.3f} V",
                kind="voltage",
            )
            return False
        if v < self.limits.charge_floor_v:
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell Voltage {v:.3f} V below hard floor {self.limits.charge_floor_v:.3f} V "
                f"(over-discharged: needs operator inspection before any charge)",
                kind="voltage_hard",
            )
            return False
        if v < self.limits.min_voltage_v and step not in ("charge", "rest"):
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell Voltage {v:.3f} V dropped below safety limit {self.limits.min_voltage_v:.3f} V",
                kind="voltage",
            )
            return False

        # 3. Overcurrent limits
        if cell_data.current > self.limits.max_charge_current_a:
            self._trigger_shutdown(
                f"SAFETY TRIP: Charge current {cell_data.current:.3f} A exceeded limit {self.limits.max_charge_current_a:.3f} A",
                kind="current",
            )
            return False

        if abs(cell_data.current) > self.limits.max_discharge_current_a and cell_data.current < 0:
            self._trigger_shutdown(
                f"SAFETY TRIP: Discharge current {abs(cell_data.current):.3f} A exceeded limit {self.limits.max_discharge_current_a:.3f} A",
                kind="current",
            )
            return False

        # 4. Temperature absolute limit
        max_temp = max(cell_data.body_temp, cell_data.terminal_temp)
        if max_temp > self.limits.max_temp_c:
            self._trigger_shutdown(
                f"SAFETY TRIP: Cell temperature {max_temp:.1f} °C exceeded limit {self.limits.max_temp_c:.1f} °C",
                kind="thermal",
            )
            return False

        # 5. Temperature rate-of-rise limit (dT/dt) early runaway trigger (IMP-09)
        if not self.limits.temp_rate_enabled:
            if self._temp_history:
                self._clear_rate_history()     # switched back on later: start a fresh window
            self.last_rate_of_rise_c_per_min = 0.0
            return True
        t_sample = cell_data.timestamp if cell_data.timestamp > 0 else now
        window_s = self.limits.temp_rate_window_s

        # A telemetry gap (connect, reconnect, stalled port) or a clock step restarts the window:
        # readings from before and after it must never be compared
        if self._temp_history:
            gap = t_sample - self._temp_history[-1][0]
            if gap > self.limits.temp_rate_max_gap_s or gap < 0.0:
                logger.debug(f"[Rate-of-rise] {gap:.2f} s telemetry gap: restarting the dT/dt window")
                self._clear_rate_history()
        if self._rate_history_start is None:
            self._rate_history_start = t_sample
        self._temp_history.append((t_sample, cell_data.terminal_temp, cell_data.body_temp))

        while len(self._temp_history) > 1 and self._temp_history[0][0] < t_sample - window_s:
            self._temp_history.popleft()

        # Evaluate only once a full window of uninterrupted data exists. It used to start after 5 s
        # and compare just the oldest and newest samples, so one unsettled reading right after
        # connecting (0.6 \u00b0C in 5 s) read as 7.1 \u00b0C/min (idle trip, 15-cycle run, 2026-10-01).
        if t_sample - self._rate_history_start >= window_s and len(self._temp_history) >= 3:
            rate_c_per_min = self._fitted_rate_c_per_min()
            self.last_rate_of_rise_c_per_min = rate_c_per_min

            if rate_c_per_min >= self.limits.max_temp_rate_of_rise_c_per_min:
                if self._rate_trip_start_time is None:
                    self._rate_trip_start_time = t_sample
                elif (t_sample - self._rate_trip_start_time) >= self.limits.temp_rate_sustain_s:
                    self._log_rate_window(rate_c_per_min)
                    self._trigger_shutdown(
                        f"SAFETY TRIP: Rate of temperature rise exceeded limit: {rate_c_per_min:.2f} \u00b0C/min "
                        f"(limit: {self.limits.max_temp_rate_of_rise_c_per_min:.2f} \u00b0C/min sustained for {self.limits.temp_rate_sustain_s:.1f}s)",
                        kind="thermal",
                    )
                    return False
            else:
                self._rate_trip_start_time = None

        return True

    def _fitted_rate_c_per_min(self) -> float:
        """Rate of rise that BOTH probes agree on: the lower of their least-squares slopes, in \u00b0C/min.

        Runaway heats the whole cell, so terminal and body rise together. A single glitching
        probe does not: in the 15-cycle run (2026-10-01) the terminal probe flipped between
        readings 0.9 \u00b0C apart and the body probe had bursts of its own; either one alone fitted
        4-5 \u00b0C/min for 12-39 s and would have tripped, while the agreed rate never passed 0.7.
        The absolute temperature limit still uses the hotter probe on its own.
        """
        return min(self._probe_slope(1), self._probe_slope(2))

    def _probe_slope(self, column: int) -> float:
        """Least-squares slope of one probe over the window, in \u00b0C/min (1 = terminal, 2 = body)."""
        hist = self._temp_history
        n = len(hist)
        t0 = hist[0][0]
        mean_t = sum(s[0] - t0 for s in hist) / n
        mean_y = sum(s[column] for s in hist) / n
        sxx = sum((s[0] - t0 - mean_t) ** 2 for s in hist)
        if sxx <= 0.0:
            return 0.0
        sxy = sum((s[0] - t0 - mean_t) * (s[column] - mean_y) for s in hist)
        return sxy / sxx * 60.0

    def _log_rate_window(self, rate_c_per_min: float) -> None:
        """Record the readings behind a rate trip, so a false trip can be diagnosed from the log."""
        span = self._temp_history[-1][0] - self._temp_history[0][0]
        parts = []
        for column, name in ((1, "terminal"), (2, "body")):
            temps = [s[column] for s in self._temp_history]
            tail = " ".join(f"{y:.1f}" for y in temps[-20:])
            parts.append(
                f"{name} {self._probe_slope(column):.2f} \u00b0C/min (first {temps[0]:.1f}, last {temps[-1]:.1f}, "
                f"min {min(temps):.1f}, max {max(temps):.1f}; last 20: {tail})"
            )
        logger.warning(
            f"[Rate-of-rise] agreed {rate_c_per_min:.2f} \u00b0C/min over {len(self._temp_history)} samples / "
            f"{span:.1f} s: " + "; ".join(parts)
        )

    def _clear_rate_history(self) -> None:
        self._temp_history.clear()
        self._rate_history_start = None
        self._rate_trip_start_time = None

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

        # Exact step type ("charge" / "discharge" / "rest"); substring tests matched
        # "charge" inside "discharge" and silently ignored under-voltage while discharging
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
                    if step_type_str in ("charge", "rest") and (
                        cell_voltage is None or cell_voltage >= self.limits.charge_floor_v
                    ):
                        continue  # Charging is the cure; resting does no harm (hard floor still applies)
                elif flag == BMSFaultFlags.COV:
                    if step_type_str == "discharge":
                        continue  # Expected at start of discharge from 4.2V
                    if step_type_str == "rest" and (
                        cell_voltage is None or cell_voltage <= self.limits.max_voltage_v
                    ):
                        # Still flagged after an over-voltage ended the charge: it used to end the
                        # post-charge rest at once (CUV in rest was already tolerated)
                        continue
                elif flag in (BMSFaultFlags.OCC, BMSFaultFlags.OCD):
                    if step_type_str == "rest":
                        continue  # Zero current in rest; ignore un-cleared comparator latches

                self.active_faults.append(label)

        if self.active_faults and not self.is_tripped:
            fault_str = ", ".join(self.active_faults)
            self._trigger_shutdown(f"HARDWARE BMS FAULT DETECTED: {fault_str}", kind=self._bms_fault_kind())
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
                f"Check USB connection and MCU power.",
                kind="watchdog",
            )
            return False

        return True

    def emergency_stop(self) -> None:
        """Manual Emergency Stop invoked by user."""
        self._trigger_shutdown("MANUAL EMERGENCY STOP TRIGGERED BY OPERATOR", kind="manual", force=True)

    def latch_trip(self, reason: str, kind: str = "") -> None:
        """Record a trip raised outside the monitor (no hardware writes: the caller idles it).

        Latching makes START wait for an operator reset, as for every other trip.
        """
        self.is_tripped = True
        self.trip_reason = reason
        self.trip_kind = kind

    def reset_safety(self) -> None:
        """Clear tripped status after issue resolution."""
        self.is_tripped = False
        self.trip_reason = ""
        self.trip_kind = ""
        self.active_faults.clear()
        self.last_telemetry_time = time.time()
        self._clear_rate_history()
        self.last_rate_of_rise_c_per_min = 0.0

    def _bms_fault_kind(self) -> str:
        """Most severe class among the active BMS fault flags: thermal > current > voltage."""
        labels = set(self.active_faults)
        if labels & {FAULT_LABELS[BMSFaultFlags.COT], FAULT_LABELS[BMSFaultFlags.CUT]}:
            return "thermal"
        if labels & {FAULT_LABELS[BMSFaultFlags.OCC], FAULT_LABELS[BMSFaultFlags.OCD]}:
            return "current"
        return "voltage"

    def _trigger_shutdown(self, reason: str, kind: str = "", force: bool = False) -> None:
        """Execute hardware safe-state shutdown with priority 0.

        Only sends writes while armed (engine Running) or when forced (manual E-STOP).
        """
        self.is_tripped = True
        self.trip_reason = reason
        self.trip_kind = kind
        if not (self.armed or force):
            logger.info(f"Safety trip recorded without hardware writes (no test running): {reason}")
            return
        logger.critical(f"Executing Emergency Safety Shutdown: {reason}")

        try:
            # Safely de-energize active charge/discharge controls with Priority 0.
            # Discharge: load off before Discharge Enable off (sent back to back, no pause, in an emergency)
            self._command_sender(FRAME_CHARGE_CTRL, 0x00, 0)
            self._command_sender(FRAME_DISCHARGE_SEL, 0x00, 0)
            self._command_sender(FRAME_DISCHARGE_CTRL, 0x00, 0)
            self._command_sender(FRAME_CHARGE_SEL, 0x00, 0)
            # De-energize cell enable while preserving selected cell position
            relay_idle = int(RelayControlBits.CELL_SELECT) if self.selected_cell == 2 else 0x00
            if self.relay_readback is not None:
                rb = self.relay_readback() & int(RelayControlBits.CELL_SELECT | RelayControlBits.CELL_ENABLE)
                if rb & RelayControlBits.CELL_ENABLE:
                    # Enable is closed: keep the Select the board reports so only Cell Enable moves
                    relay_idle = rb & int(RelayControlBits.CELL_SELECT)
            self._command_sender(FRAME_RELAY_CTRL, relay_idle, 0)
        except Exception as exc:
            logger.error(f"Error during emergency shutdown commands: {exc}")
