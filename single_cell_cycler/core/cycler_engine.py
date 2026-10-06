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
    CommandEchoTelemetry,
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
from .state_journal import (
    StateJournalManager,
    TestJournalData,
    cycle_summary_from_dict,
    cycle_summary_to_dict,
    step_metrics_from_dict,
    step_metrics_to_dict,
)
from .step_transition_controller import StepTransitionController

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
    step_fault = Signal(str)                      # voltage fault ended a step; test continues

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
        self.safety_monitor.armed = False  # engine starts IDLE
        self.transition_controller = StepTransitionController(
            command_sender=command_sender,
            parent=self,
        )
        self.transition_controller.transition_completed.connect(self._on_transition_completed)
        self.transition_controller.transition_status.connect(self._on_transition_status)
        self.transition_controller.transition_failed.connect(self._on_transition_failed)
        self.transition_controller.safe_idle_unconfirmed.connect(self._on_safe_idle_unconfirmed)
        self.safety_monitor.relay_readback = lambda: self.transition_controller.control_readbacks.get(
            FRAME_RELAY_CTRL, 0
        )

        # Execution tracking
        self._selected_cell: int = 1  # 1 = Cell 1 (bit 1 = 0), 2 = Cell 2 (bit 1 = 1)
        self.current_cycle = 1
        self.current_step_idx = 0  # 0-indexed into recipe.steps
        self.active_step: Optional[TestStep] = None
        self._loop_counters: Dict[int, int] = {}  # step_idx -> remaining loops
        self._last_telemetry: Optional[CellDataTelemetry] = None
        self._last_fault_soc: Optional[FaultSoCTelemetry] = None
        self._step_activated_time: float = 0.0
        # (cycle, step_number, step_name, step_type, StepMetrics | None) for the CSV sampler thread.
        # Replaced as one tuple, never mutated, so a row can't mix the old and new step: reading
        # current_step_idx / active_step / current_step_metrics separately produced rows with the
        # new step number but the old step type and a zeroed capacity, and a phantom "step 5".
        self.log_position: Optional[tuple] = None

        # Atomic State Journaling for Crash Recovery (IMP-08)
        self.journal_manager = StateJournalManager()
        self.csv_log_file: Optional[str] = None

        # Watchdog periodic timer (1s)
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(1000)
        self._watchdog_timer.timeout.connect(self._on_watchdog_tick)
        self._watchdog_timer.start()

    @property
    def selected_cell(self) -> int:
        return self._selected_cell

    @selected_cell.setter
    def selected_cell(self, cell_num: int) -> None:
        # The cell is fixed for the whole test: only the Cell Enable relay changes after START
        if self.test_active and cell_num != self._selected_cell:
            logger.warning(
                f"[Engine] Ignoring cell change to Cell {cell_num}: Cell {self._selected_cell} is locked "
                f"while the test is {self.state.value}"
            )
            return
        self._selected_cell = cell_num
        self.safety_monitor.selected_cell = cell_num

    @property
    def test_active(self) -> bool:
        """A test owns the hardware (cell locked) from START until Stop/Complete/Safety Stop."""
        return self.state in (EngineState.RUNNING, EngineState.STEP_TRANSITION, EngineState.PAUSED)

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
        self.metrics_tracker.partial_first_cycle = self._starts_with_charge()
        self._reset_execution_state()
        # A new test always closes the Cell Enable relay itself (confirmed + settled)
        self.transition_controller.relay_owned_by_test = False
        self._set_state(EngineState.STEP_TRANSITION, "Starting Test Profile: initializing hardware...")
        self._sync_journal()
        self._execute_next_step()

    def pause_test(self) -> None:
        if self.state in (EngineState.RUNNING, EngineState.STEP_TRANSITION):
            self.transition_controller.abort()
            # Pause only opens the Cell Enable relay; Cell Select stays on the test cell
            self._safe_idle_hardware(keep_select=True)
            self._set_state(EngineState.PAUSED, "Test Paused by Operator")

    def resume_test(self) -> None:
        if self.state == EngineState.PAUSED:
            if self.active_step:
                self._apply_hardware_for_step(self.active_step)
            else:
                self._set_state(EngineState.RUNNING, "Resuming Test Profile")

    def _close_active_step(self, reason: str) -> None:
        """Complete the active step if running so metrics and summaries record it.

        Never records a dummy step (when current_step_metrics is None).
        """
        if self.metrics_tracker.current_step_metrics is not None:
            finished_step = self.metrics_tracker.complete_step(reason)
            self.step_completed.emit(finished_step)

    def stop_test(self) -> None:
        """Gracefully stop test and disconnect cell."""
        self._close_active_step("Stopped by operator")
        self.transition_controller.abort()
        self._safe_idle_hardware()
        self.journal_manager.clear_journal()
        self._set_state(EngineState.ABORTED, "Test Aborted by Operator")

    def skip_step(self) -> None:
        """Skip current step and advance to the next step immediately."""
        if self.state in (EngineState.RUNNING, EngineState.PAUSED, EngineState.STEP_TRANSITION) and self.active_step:
            self.transition_controller.abort()
            logger.info(f"Skipping active step: {self.active_step.name}")
            finished_step = self.metrics_tracker.complete_step("Skipped by Operator")
            self.step_completed.emit(finished_step)
            self.current_step_idx += 1
            self._execute_next_step()

    def emergency_stop(self) -> None:
        """Instant emergency shutdown: immediate unconfirmed zeros, then the confirmed sequence.

        The immediate burst is sent on every press, including when already in Safety Stop,
        so a repeated E-STOP never waits behind a confirmed sequence that is still retrying.
        """
        self._close_active_step("EMERGENCY STOP")
        self.transition_controller.abort()
        self.safety_monitor.emergency_stop()
        self._safe_idle_hardware()
        if self.state != EngineState.SAFETY_STOP:
            self._set_state(EngineState.SAFETY_STOP, "EMERGENCY STOP EXECUTED")
            self.safety_tripped.emit("Manual Emergency Stop")

    def on_command_echo(self, echo: CommandEchoTelemetry) -> None:
        """Process incoming 0x6000-0x6004 readback frame."""
        self.transition_controller.on_command_echo(echo)

    def on_cell_telemetry(self, telemetry: CellDataTelemetry) -> None:
        """Main real-time update loop driven by incoming 0x1000 frames."""
        self._last_telemetry = telemetry

        # 1. Safety check
        if not self.safety_monitor.check_telemetry(telemetry):
            fault_reason = self.safety_monitor.trip_reason

            # Only hard-trip the interlock during an active test.  In IDLE / PAUSED /
            # COMPLETED / ABORTED states no cell is connected; out-of-range readings
            # (e.g. ~0 V with no cell fitted on the selected position) would otherwise
            # permanently lock the start gate.  Log a warning and clear the trip so the
            # operator can still start a test.  (Cell Select alone routes the selected
            # cell's voltage to the ADC; Cell Enable does not need to be closed to read it.)
            if self.state in (
                EngineState.IDLE,
                EngineState.PAUSED,
                EngineState.COMPLETED,
                EngineState.ABORTED,
            ):
                logger.warning(
                    f"[Engine] Out-of-range telemetry in {self.state.value} (no test running) "
                    f"- suppressing safety trip: {fault_reason}"
                )
                self.safety_monitor.reset_safety()
                return

            if self.state == EngineState.RUNNING and self.active_step:
                self._handle_step_fault(fault_reason)
                return

            if self.state == EngineState.STEP_TRANSITION:
                # Still transitioning hardware to the new step; clear trip flag to allow settling
                self.safety_monitor.reset_safety()
                return

            if self.state != EngineState.SAFETY_STOP:
                self._close_active_step(fault_reason)
                self.transition_controller.abort()
                self._safe_idle_hardware()
                self._set_state(EngineState.SAFETY_STOP, fault_reason)
                self.safety_tripped.emit(fault_reason)
            return

        # 2. Update metrics integration
        self.metrics_tracker.update(telemetry)

        # 3. If running, evaluate cut-offs
        if self.state == EngineState.RUNNING and self.active_step:
            step_m = self.metrics_tracker.current_step_metrics
            elapsed_s = step_m.duration_s if step_m else 0.0
            cap_mah = step_m.capacity_mah if step_m else 0.0

            soc_val = self._last_fault_soc.soc_main if self._last_fault_soc else None
            result = self.cutoff_detector.evaluate(
                step=self.active_step,
                telemetry=telemetry,
                step_elapsed_time_s=elapsed_s,
                step_capacity_mah=cap_mah,
                current_soc=soc_val,
            )

            if result.is_triggered:
                logger.info(f"Cut-off Triggered for {self.active_step.name}: {result.trigger_reason}")
                finished_step = self.metrics_tracker.complete_step(result.trigger_reason)
                self.step_completed.emit(finished_step)
                self.current_step_idx += 1
                self._sync_journal()
                self._execute_next_step()

    def on_fault_soc_telemetry(self, fault_soc: FaultSoCTelemetry) -> None:
        """Driven by incoming 0x3000 frames."""
        self._last_fault_soc = fault_soc
        stype = self.active_step.step_type.value if self.active_step else None
        v_cell = self._last_telemetry.voltage if self._last_telemetry else None
        is_trans = (self.state == EngineState.STEP_TRANSITION)
        if not self.safety_monitor.check_bms_faults(
            fault_soc,
            active_step_type=stype,
            cell_voltage=v_cell,
            is_transitioning=is_trans,
        ):
            fault_reason = self.safety_monitor.trip_reason

            # Suppress BMS fault trips in IDLE / PAUSED / COMPLETED / ABORTED states.
            # Comparator latches can persist after a test ends or before one starts;
            # tripping in idle would lock out the start gate unnecessarily.
            if self.state in (
                EngineState.IDLE,
                EngineState.PAUSED,
                EngineState.COMPLETED,
                EngineState.ABORTED,
            ):
                logger.warning(
                    f"[Engine] BMS fault flags in {self.state.value} (no test running) "
                    f"- suppressing safety trip: {fault_reason}"
                )
                self.safety_monitor.reset_safety()
                return

            if self.state == EngineState.RUNNING and self.active_step:
                self._handle_step_fault(fault_reason)
                return

            if self.state != EngineState.SAFETY_STOP:
                self._close_active_step(fault_reason)
                self.transition_controller.abort()
                self._safe_idle_hardware()
                self._set_state(EngineState.SAFETY_STOP, fault_reason)
                self.safety_tripped.emit(fault_reason)
            return

        # Check SoC cut-off conditions when new fault/SoC telemetry arrives during active run
        if self.state == EngineState.RUNNING and self.active_step and self._last_telemetry:
            step_m = self.metrics_tracker.current_step_metrics
            elapsed_s = step_m.duration_s if step_m else 0.0
            cap_mah = step_m.capacity_mah if step_m else 0.0

            result = self.cutoff_detector.evaluate(
                step=self.active_step,
                telemetry=self._last_telemetry,
                step_elapsed_time_s=elapsed_s,
                step_capacity_mah=cap_mah,
                current_soc=fault_soc.soc_main,
            )
            if result.is_triggered:
                logger.info(f"SoC Cut-off Triggered for {self.active_step.name}: {result.trigger_reason}")
                finished_step = self.metrics_tracker.complete_step(result.trigger_reason)
                self.step_completed.emit(finished_step)
                self.current_step_idx += 1
                self._sync_journal()
                self._execute_next_step()

    def _handle_step_fault(self, fault_reason: str) -> None:
        """Handle a fault raised while a step is running.

        Voltage faults (COV/CUV or the software voltage limits) end the step like a cut-off
        and the profile continues. Temperature, current and every other fault stop the test.
        """
        if not self.recipe or not self.active_step:
            return

        kind = self.safety_monitor.trip_kind
        step_name = self.active_step.name
        if kind == "voltage":
            logger.warning(
                f"[Fault Handling] Voltage fault during step '{step_name}': {fault_reason} "
                f"-> ending step like a cut-off"
            )
            self.safety_monitor.reset_safety()
            finished_step = self.metrics_tracker.complete_step(f"FAULT: {fault_reason}")
            self.step_completed.emit(finished_step)
            self.step_fault.emit(f"{step_name}: {fault_reason}")
            self.current_step_idx += 1
            self._sync_journal()
            self._execute_next_step()
            return

        logger.critical(
            f"[Fault Handling] {kind or 'unclassified'} fault during step '{step_name}': {fault_reason} "
            f"-> Safety Stop"
        )
        finished_step = self.metrics_tracker.complete_step(f"FAULT: {fault_reason}")
        self.step_completed.emit(finished_step)
        self.transition_controller.abort()
        self._safe_idle_hardware()
        self._set_state(EngineState.SAFETY_STOP, fault_reason)
        self.safety_tripped.emit(fault_reason)

    def _execute_next_step(self) -> None:
        """Step sequencer and loop dispatcher."""
        if not self.recipe:
            return

        if self.current_step_idx >= len(self.recipe.steps):
            # Finished all steps in recipe!
            cycle_sum = self.metrics_tracker.compute_cycle_summary(self.current_cycle)
            self._flag_partial_cycle(cycle_sum)
            self.cycle_completed.emit(cycle_sum)
            self.journal_manager.clear_journal()
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
                self._flag_partial_cycle(cycle_sum)
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

        # A charge is refused before any charge write if the cell is already below the hard floor
        floor = self.safety_monitor.limits.charge_floor_v
        if (
            step.step_type == StepType.CHARGE
            and self._last_telemetry is not None
            and self._last_telemetry.voltage < floor
        ):
            reason = (
                f"SAFETY TRIP: Charge refused: cell at {self._last_telemetry.voltage:.3f} V is below the "
                f"hard floor {floor:.3f} V (over-discharged: needs operator inspection)"
            )
            logger.critical(f"[Fault Handling] {reason}")
            self.active_step = None
            self.safety_monitor.latch_trip(reason, kind="voltage_hard")
            self.transition_controller.abort()
            self._safe_idle_hardware()
            self._set_state(EngineState.SAFETY_STOP, reason)
            self.safety_tripped.emit(reason)
            return

        # Regular step (Charge, Discharge, Rest)
        self.active_step = step
        self.log_position = (self.current_cycle, self.current_step_idx + 1, step.name, step.step_type.value, None)
        self._set_state(EngineState.STEP_TRANSITION, f"Configuring hardware for {step.name}...")
        self.transition_controller.start_transition(step=step, selected_cell=self.selected_cell)

    def _starts_with_charge(self) -> bool:
        if not self.recipe:
            return False
        first_active = next(
            (s for s in self.recipe.steps if s.step_type in (StepType.CHARGE, StepType.DISCHARGE)), None
        )
        return first_active is not None and first_active.step_type == StepType.CHARGE

    def _flag_partial_cycle(self, cycle_sum: CycleSummary) -> None:
        """Cycle 1 of a recipe whose first active step is a charge starts from an unknown charge
        level, so its charge capacity and efficiencies are partial."""
        if cycle_sum.cycle_index == 1 and self._starts_with_charge():
            cycle_sum.partial_initial_charge = True

    def _on_transition_status(self, msg: str) -> None:
        logger.info(f"Transition Status: {msg}")
        self.state_changed.emit(self.state.value, msg)

    def _on_transition_completed(self, step: TestStep) -> None:
        if self.state != EngineState.STEP_TRANSITION:
            return
        # Refresh watchdog baseline so the 8 s window is fresh for the new step.
        # This prevents accumulated transition delays from eating into the step's budget.
        self.safety_monitor.last_telemetry_time = time.time()
        self.safety_monitor.reset_safety()
        self.safety_monitor.active_step_type = step.step_type.value.lower()
        self._step_activated_time = time.time()
        self._set_state(EngineState.RUNNING, f"Executing: {step.name}")
        self.metrics_tracker.start_step(
            cycle_index=self.current_cycle,
            step_index=self.current_step_idx + 1,
            step_name=step.name,
            step_type=step.step_type,
            initial_telemetry=self._last_telemetry,
        )
        self.log_position = (
            self.current_cycle, self.current_step_idx + 1, step.name, step.step_type.value,
            self.metrics_tracker.current_step_metrics,
        )
        self.step_started.emit(self.current_cycle, self.current_step_idx + 1, step.name, step.step_type.value)

    def _on_transition_failed(self, error_msg: str) -> None:
        self._close_active_step(f"Step setup failed: {error_msg}")
        self._safe_idle_hardware()
        # Latch like every other trip: otherwise START skips the reset and the trip panel's
        # Reset button stays live into the next test
        self.safety_monitor.latch_trip(f"Hardware misaligned: {error_msg}", kind="transition")
        self._set_state(EngineState.SAFETY_STOP, f"Step Transition Error: {error_msg}")
        self.safety_tripped.emit(f"Hardware misaligned: {error_msg}")

    def reset_safety_interlock(self) -> bool:
        """Operator reset after a trip. Refused while a test owns the hardware.

        Returns True if the interlock was cleared. Forcing Idle mid-test would stop cut-off
        and safety evaluation while the hardware stays energized.
        """
        if self.test_active:
            logger.warning(
                f"[Engine] Safety interlock reset ignored: a test is {self.state.value}"
            )
            return False
        self.safety_monitor.reset_safety()
        self._set_state(EngineState.IDLE, "Safety Interlock Reset")
        return True

    def _apply_hardware_for_step(self, step: TestStep) -> None:
        """Translate step configuration into exact 0x6000 - 0x6004 TX commands via StepTransitionController."""
        self._set_state(EngineState.STEP_TRANSITION, f"Reconfiguring hardware for {step.name}...")
        self.transition_controller.start_transition(step=step, selected_cell=self.selected_cell)

    def _safe_idle_hardware(self, keep_select: bool = False) -> None:
        """Place hardware in safe non-energized state with readback-confirmed writes.

        Order: Charge/Discharge Control off -> Charge Select / Discharge Load cleared ->
        Cell Enable relay opened -> (unless keep_select, e.g. Pause) 0x6000 = 0.
        """
        logger.info(
            "[Engine] Safe Idle: de-energizing 0x6002/0x6003, clearing 0x6001/0x6004, opening Cell Enable relay"
            + (" (Cell Select kept)" if keep_select else ", 0x6000 -> 0")
        )
        self.transition_controller.safe_idle(self.selected_cell, priority=0, keep_select=keep_select)

    def _on_safe_idle_unconfirmed(self, detail: str) -> None:
        msg = f"SAFE IDLE NOT CONFIRMED by hardware readback: {detail}"
        logger.critical(f"[Engine] {msg}")
        self.state_changed.emit(self.state.value, msg)

    def _reset_execution_state(self) -> None:
        self.current_cycle = 1
        self.current_step_idx = 0
        self.active_step = None
        self.log_position = None
        self._loop_counters.clear()
        if self.recipe:
            for i, s in enumerate(self.recipe.steps):
                if s.step_type == StepType.LOOP:
                    self._loop_counters[i] = s.loop_count

    def _set_state(self, new_state: EngineState, msg: str = "") -> None:
        if self.state == new_state and new_state in (EngineState.SAFETY_STOP, EngineState.IDLE, EngineState.PAUSED):
            return
        self.state = new_state
        # The monitor may write hardware only while a step is running; otherwise registers
        # are zeroed or owned by a confirmed sequence (a burst there would undo it)
        self.safety_monitor.armed = new_state == EngineState.RUNNING
        if new_state not in (EngineState.RUNNING, EngineState.STEP_TRANSITION):
            self.safety_monitor.active_step_type = None
        logger.info(f"Engine State -> {new_state.value}: {msg}")
        self.state_changed.emit(new_state.value, msg)

    def _on_watchdog_tick(self) -> None:
        if self.state == EngineState.RUNNING:
            if not self.safety_monitor.check_watchdog():
                if self.state != EngineState.SAFETY_STOP:
                    trip_reason = self.safety_monitor.trip_reason
                    self._close_active_step(trip_reason)
                    self.transition_controller.abort()
                    self._safe_idle_hardware()
                    self._set_state(EngineState.SAFETY_STOP, trip_reason)
                    self.safety_tripped.emit(trip_reason)

    def _sync_journal(self) -> None:
        """Persist active engine and metrology snapshot to atomic journal (IMP-08)."""
        if not self.recipe:
            return
        step = self.recipe.steps[self.current_step_idx] if self.current_step_idx < len(self.recipe.steps) else None
        journal = TestJournalData(
            version="1.0",
            active=True,
            recipe_name=self.recipe.recipe_name,
            recipe_dict=self.recipe.to_dict(),
            selected_cell=self.selected_cell,
            current_cycle=self.current_cycle,
            current_step_idx=self.current_step_idx,
            step_name=step.name if step else "",
            step_type=step.step_type.value if step else "",
            loop_counters={str(k): v for k, v in self._loop_counters.items()},
            cumulative_charge_mah=self.metrics_tracker.cumulative_charge_mah,
            cumulative_discharge_mah=self.metrics_tracker.cumulative_discharge_mah,
            cumulative_charge_mwh=self.metrics_tracker.cumulative_charge_mwh,
            cumulative_discharge_mwh=self.metrics_tracker.cumulative_discharge_mwh,
            total_test_start_time=self.metrics_tracker.total_test_start_time,
            step_history=[step_metrics_to_dict(s) for s in self.metrics_tracker.step_history],
            cycle_summaries=[cycle_summary_to_dict(c) for c in self.metrics_tracker.cycle_summaries],
            csv_log_file=self.csv_log_file,
        )
        self.journal_manager.write_journal(journal)

    def resume_from_journal(self, journal: TestJournalData) -> None:
        """Seamlessly restore test execution from crash recovery journal (IMP-08)."""
        if not journal.recipe_dict:
            raise ValueError("Corrupt or empty recipe in recovery journal")

        self.recipe = TestRecipe.from_dict(journal.recipe_dict)
        self.selected_cell = journal.selected_cell
        self.current_cycle = journal.current_cycle
        self.current_step_idx = journal.current_step_idx
        self._loop_counters = {int(k): v for k, v in journal.loop_counters.items()}
        self.csv_log_file = journal.csv_log_file

        # Restore cumulative metrology and history
        steps = [step_metrics_from_dict(d) for d in journal.step_history]
        cycles = [cycle_summary_from_dict(d) for d in journal.cycle_summaries]
        self.metrics_tracker.restore_state(
            total_test_start_time=journal.total_test_start_time if journal.total_test_start_time > 0 else time.time(),
            cumulative_charge_mah=journal.cumulative_charge_mah,
            cumulative_discharge_mah=journal.cumulative_discharge_mah,
            cumulative_charge_mwh=journal.cumulative_charge_mwh,
            cumulative_discharge_mwh=journal.cumulative_discharge_mwh,
            current_cycle_index=journal.current_cycle,
            step_history=steps,
            cycle_summaries=cycles,
        )
        self.metrics_tracker.partial_first_cycle = self._starts_with_charge()

        self.safety_monitor.last_telemetry_time = time.time()
        self.safety_monitor.reset_safety()
        self.transition_controller.relay_owned_by_test = False
        self._set_state(EngineState.STEP_TRANSITION, f"Resuming Test Profile from Step {self.current_step_idx + 1}...")
        self._sync_journal()
        self._execute_next_step()
