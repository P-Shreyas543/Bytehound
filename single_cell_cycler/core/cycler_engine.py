"""Automated Test Recipe Execution Engine and State Machine."""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from ..comm.packet_codec import (
    BoardParamsTelemetry,
    CellDataTelemetry,
    FaultSoCTelemetry,
)
from ..comm.protocol_defs import (
    FRAME_CHARGE_CTRL,
    FRAME_CHARGE_SEL,
    FRAME_DISCHARGE_CTRL,
    FRAME_DISCHARGE_SEL,
    FRAME_RELAY_CTRL,
    ChargeControlBits,
    ChargeSelectBits,
    DischargeControlBits,
    DischargeSelectBits,
    RelayControlBits,
)
from .cutoff_detector import CutoffDetector
from .metrics_tracker import CycleSummary, MetricsTracker, StepMetrics
from .profile_model import StepType, TestRecipe, TestStep
from .safety_monitor import SafetyMonitor

logger = logging.getLogger("SingleCellCycler.Engine")


class EngineState(str, Enum):
    IDLE = "Idle"
    RUNNING = "Running"
    PAUSED = "Paused"
    STEP_TRANSITION = "Step Transition"
    COMPLETED = "Completed"
    ABORTED = "Aborted"
    SAFETY_STOP = "Safety Stop"


class CyclerEngine(QObject):
    """Orchestrates test steps, cut-offs, loops, and hardware control."""

    # Qt Signals
    state_changed = Signal(str, str)              # state_enum_val, message
    step_started = Signal(int, int, str, str)     # cycle_idx, step_idx, step_name, step_type
    step_completed = Signal(object)               # StepMetrics
    cycle_completed = Signal(object)              # CycleSummary
    recipe_completed = Signal(str)                # summary message
    safety_tripped = Signal(str)                  # reason

    def __init__(
        self,
        command_sender: Callable[[int, int, int], None],
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._command_sender = command_sender
        self.state = EngineState.IDLE

        self.recipe: Optional[TestRecipe] = None
        self.metrics_tracker = MetricsTracker()
        self.cutoff_detector = CutoffDetector()
        self.safety_monitor = SafetyMonitor(command_sender)

        # Execution tracking
        self.selected_cell: int = 1  # 1 = Cell 1 (bit 1 = 0), 2 = Cell 2 (bit 1 = 1)
        self.current_cycle = 1
        self.current_step_idx = 0  # 0-indexed into recipe.steps
        self.active_step: Optional[TestStep] = None
        self._loop_counters: Dict[int, int] = {}  # step_idx -> remaining loops
        self._last_telemetry: Optional[CellDataTelemetry] = None

        # Watchdog periodic timer (1s)
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(1000)
        self._watchdog_timer.timeout.connect(self._on_watchdog_tick)
        self._watchdog_timer.start()

    def load_recipe(self, recipe: TestRecipe) -> None:
        if self.state in (EngineState.RUNNING, EngineState.STEP_TRANSITION):
            raise RuntimeError("Cannot load recipe while a test is actively running")
        self.recipe = recipe
        self._reset_execution_state()
        self._set_state(EngineState.IDLE, f"Loaded recipe: {recipe.recipe_name} ({len(recipe.steps)} steps)")

    def start_test(self) -> None:
        if not self.recipe or not self.recipe.steps:
            raise ValueError("No valid recipe loaded")
        if self.safety_monitor.is_tripped:
            raise RuntimeError(f"Cannot start test: Safety tripped ({self.safety_monitor.trip_reason})")

        self.safety_monitor.last_telemetry_time = time.time()
        self.metrics_tracker.reset_all()
        self._reset_execution_state()
        self._set_state(EngineState.RUNNING, "Starting Test Profile")
        self._execute_next_step()

    def pause_test(self) -> None:
        if self.state == EngineState.RUNNING:
            self._set_state(EngineState.PAUSED, "Test Paused by Operator")
            # Set hardware to safe holding state (disable charge & discharge)
            self._command_sender(FRAME_CHARGE_CTRL, 0x00, 1)
            self._command_sender(FRAME_DISCHARGE_CTRL, 0x00, 1)

    def resume_test(self) -> None:
        if self.state == EngineState.PAUSED:
            self._set_state(EngineState.RUNNING, "Resuming Test Profile")
            if self.active_step:
                self._apply_hardware_for_step(self.active_step)

    def stop_test(self) -> None:
        """Gracefully stop test and disconnect cell."""
        self._safe_idle_hardware()
        self._set_state(EngineState.ABORTED, "Test Aborted by Operator")

    def skip_step(self) -> None:
        """Skip current step and advance to the next step immediately."""
        if self.state in (EngineState.RUNNING, EngineState.PAUSED) and self.active_step:
            logger.info(f"Skipping active step: {self.active_step.name}")
            finished_step = self.metrics_tracker.complete_step("Skipped by Operator")
            self.step_completed.emit(finished_step)
            self.current_step_idx += 1
            self._execute_next_step()

    def emergency_stop(self) -> None:
        """Instant emergency shutdown."""
        if self.state != EngineState.SAFETY_STOP:
            self.safety_monitor.emergency_stop()
            self._set_state(EngineState.SAFETY_STOP, "EMERGENCY STOP EXECUTED")
            self.safety_tripped.emit("Manual Emergency Stop")

    def on_cell_telemetry(self, telemetry: CellDataTelemetry) -> None:
        """Main real-time update loop driven by incoming 0x1000 frames."""
        self._last_telemetry = telemetry

        # 1. Safety check
        if not self.safety_monitor.check_telemetry(telemetry):
            if self.state != EngineState.SAFETY_STOP:
                self._set_state(EngineState.SAFETY_STOP, self.safety_monitor.trip_reason)
                self.safety_tripped.emit(self.safety_monitor.trip_reason)
            return

        # 2. Update metrics integration
        self.metrics_tracker.update(telemetry)

        # 3. If running, evaluate cut-offs
        if self.state == EngineState.RUNNING and self.active_step:
            step_m = self.metrics_tracker.current_step_metrics
            elapsed_s = step_m.duration_s if step_m else 0.0
            cap_mah = step_m.capacity_mah if step_m else 0.0

            result = self.cutoff_detector.evaluate(
                step=self.active_step,
                telemetry=telemetry,
                step_elapsed_time_s=elapsed_s,
                step_capacity_mah=cap_mah,
            )

            if result.is_triggered:
                logger.info(f"Cut-off Triggered for {self.active_step.name}: {result.trigger_reason}")
                finished_step = self.metrics_tracker.complete_step(result.trigger_reason)
                self.step_completed.emit(finished_step)
                self.current_step_idx += 1
                self._execute_next_step()

    def on_fault_soc_telemetry(self, fault_soc: FaultSoCTelemetry) -> None:
        """Driven by incoming 0x3000 frames."""
        if not self.safety_monitor.check_bms_faults(fault_soc):
            if self.state != EngineState.SAFETY_STOP:
                self._set_state(EngineState.SAFETY_STOP, self.safety_monitor.trip_reason)
                self.safety_tripped.emit(self.safety_monitor.trip_reason)

    def _execute_next_step(self) -> None:
        """Step sequencer and loop dispatcher."""
        if not self.recipe:
            return

        if self.current_step_idx >= len(self.recipe.steps):
            # Finished all steps in recipe!
            cycle_sum = self.metrics_tracker.compute_cycle_summary(self.current_cycle)
            self.cycle_completed.emit(cycle_sum)
            self._safe_idle_hardware()
            self._set_state(EngineState.COMPLETED, f"Test Completed Successfully ({self.current_cycle} cycles)")
            self.recipe_completed.emit(f"Test finished across {self.current_cycle} cycles")
            return

        step = self.recipe.steps[self.current_step_idx]

        # Handle LOOP step
        if step.step_type == StepType.LOOP:
            rem_loops = self._loop_counters.get(self.current_step_idx, step.loop_count)
            if rem_loops > 1:
                self._loop_counters[self.current_step_idx] = rem_loops - 1
                cycle_sum = self.metrics_tracker.compute_cycle_summary(self.current_cycle)
                self.cycle_completed.emit(cycle_sum)
                self.current_cycle += 1
                target_0idx = max(0, min(len(self.recipe.steps) - 1, step.loop_target_step - 1))
                logger.info(f"Looping back to Step {target_0idx + 1}, remaining iterations: {rem_loops - 1}")
                self.current_step_idx = target_0idx
                self._execute_next_step()
                return
            else:
                # Finished this loop group, reset counter and advance
                self._loop_counters[self.current_step_idx] = step.loop_count
                self.current_step_idx += 1
                self._execute_next_step()
                return

        # Regular step (Charge, Discharge, Rest)
        self.active_step = step
        self._apply_hardware_for_step(step)
        self.metrics_tracker.start_step(
            cycle_index=self.current_cycle,
            step_index=self.current_step_idx + 1,
            step_name=step.name,
            step_type=step.step_type,
            initial_telemetry=self._last_telemetry,
        )
        self.step_started.emit(self.current_cycle, self.current_step_idx + 1, step.name, step.step_type.value)

    def _apply_hardware_for_step(self, step: TestStep) -> None:
        """Translate step configuration into exact 0x6000 - 0x6004 TX commands."""
        # 1. Ensure Cell Relay is enabled and correct cell selected
        # Bit 0: Cell Enable (1 = enabled)
        # Bit 1: Cell Select (0 = Cell 1, 1 = Cell 2)
        relay_payload = RelayControlBits.CELL_ENABLE
        cell_num = self.selected_cell
        if cell_num == 2:
            relay_payload |= RelayControlBits.CELL_SELECT
        self._command_sender(FRAME_RELAY_CTRL, int(relay_payload), 1)

        if step.step_type == StepType.CHARGE:
            # Turn off discharge first & clear loads
            self._command_sender(FRAME_DISCHARGE_CTRL, 0x00, 1)
            self._command_sender(FRAME_DISCHARGE_SEL, 0x00, 1)

            # Build Charge Select payload (0x6001)
            # Bit 0: Max Charge Voltage (0 = 3.6V, 1 = 4.2V)
            # Bit 1: Charge Current 1 (+0.5A)
            # Bit 2: Charge Current 2 (+1.0A)
            chg_sel = 0
            if step.max_charge_voltage:
                chg_sel |= ChargeSelectBits.MAX_CHARGE_VOLTAGE
            if step.charge_current_1:
                chg_sel |= ChargeSelectBits.MAX_CHARGE_CURRENT_1
            if step.charge_current_2:
                chg_sel |= ChargeSelectBits.MAX_CHARGE_CURRENT_2
            self._command_sender(FRAME_CHARGE_SEL, chg_sel, 1)

            # Reset comparator pulse (bit 1 high then low)
            self._command_sender(FRAME_CHARGE_CTRL, int(ChargeControlBits.CHARGE_COMPARATOR_RESET), 1)
            # Enable Charge (0x6002 bit 0)
            self._command_sender(FRAME_CHARGE_CTRL, int(ChargeControlBits.CHARGE_ENABLE), 1)

        elif step.step_type == StepType.DISCHARGE:
            # Turn off charge first
            self._command_sender(FRAME_CHARGE_CTRL, 0x00, 1)

            # Build Discharge Load Select payload (0x6004)
            # L1=0.2A, L2=0.4A, L3=0.8A, L4=1.6A (0..15 -> 0.0..3.0A)
            dis_sel = step.discharge_load_decimal
            self._command_sender(FRAME_DISCHARGE_SEL, dis_sel, 1)

            # Reset discharge comparator pulse
            self._command_sender(FRAME_DISCHARGE_CTRL, int(DischargeControlBits.DISCHARGE_COMPARATOR_RESET), 1)
            # Enable Discharge (0x6003 bit 0)
            self._command_sender(FRAME_DISCHARGE_CTRL, int(DischargeControlBits.DISCHARGE_ENABLE), 1)

        elif step.step_type == StepType.REST:
            # Disable both charge and discharge, clear loads
            self._command_sender(FRAME_CHARGE_CTRL, 0x00, 1)
            self._command_sender(FRAME_DISCHARGE_CTRL, 0x00, 1)
            self._command_sender(FRAME_DISCHARGE_SEL, 0x00, 1)

    def _safe_idle_hardware(self) -> None:
        """Place hardware in safe non-energized state."""
        self._command_sender(FRAME_CHARGE_CTRL, 0x00, 1)
        self._command_sender(FRAME_DISCHARGE_CTRL, 0x00, 1)
        self._command_sender(FRAME_DISCHARGE_SEL, 0x00, 1)
        self._command_sender(FRAME_RELAY_CTRL, 0x00, 1)

    def _reset_execution_state(self) -> None:
        self.current_cycle = 1
        self.current_step_idx = 0
        self.active_step = None
        self._loop_counters.clear()
        if self.recipe:
            for i, s in enumerate(self.recipe.steps):
                if s.step_type == StepType.LOOP:
                    self._loop_counters[i] = s.loop_count

    def _set_state(self, new_state: EngineState, msg: str = "") -> None:
        if self.state == new_state and new_state in (EngineState.SAFETY_STOP, EngineState.IDLE, EngineState.PAUSED):
            return
        self.state = new_state
        logger.info(f"Engine State -> {new_state.value}: {msg}")
        self.state_changed.emit(new_state.value, msg)

    def _on_watchdog_tick(self) -> None:
        if self.state == EngineState.RUNNING:
            if not self.safety_monitor.check_watchdog():
                if self.state != EngineState.SAFETY_STOP:
                    self._set_state(EngineState.SAFETY_STOP, self.safety_monitor.trip_reason)
                    self.safety_tripped.emit(self.safety_monitor.trip_reason)
