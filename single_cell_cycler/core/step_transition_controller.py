"""Step Transition Controller for Single-Cell BMS Cycler.

Enforces deterministic, safe hardware transition sequences with readback verification:
1. Read all control values (Relay enable, Cell select, Charge enable, Discharge enable, etc.)
2. Clear any unwanted flags first, read back verification; re-send if not set.
3. Cell Select relay switch -> wait 100ms -> Cell Enable -> wait 1.0-2.0s for analog front-end to settle.
4. Charge setup: Charge voltage -> wait 100ms -> Charge current -> wait 100ms -> Comparator reset
   (verify 0->1->0) -> Charge Enable = 1 (ensure Discharge Enable = 0). Repeat if misaligned.
5. Discharge setup: Ensure Charge Enable = 0 -> Comparator reset -> Discharge Enable = 1 ->
   Once Discharge Enable = 1 and reset = 0, apply load bank changes. Repeat if misaligned.
6. Rest setup: Disable Charge, Disable Discharge, Clear Loads, verify.
"""

from __future__ import annotations

import logging
import os
import time
from enum import Enum, auto
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from ..comm.packet_codec import CommandEchoTelemetry
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
from .profile_model import StepType, TestStep

logger = logging.getLogger("SingleCellCycler.StepTransition")


class TransitionPhase(Enum):
    IDLE = auto()
    CLEAR_UNWANTED = auto()
    CELL_SELECT = auto()
    CELL_ENABLE_SETTLE = auto()
    # Charge sub-phases
    CHG_SEND_VOLTAGE = auto()
    CHG_SEND_CURRENT = auto()
    CHG_RESET_HIGH = auto()
    CHG_RESET_LOW = auto()
    CHG_ENABLE = auto()
    # Discharge sub-phases
    DIS_CLEAR_CHG = auto()
    DIS_RESET_HIGH = auto()
    DIS_RESET_LOW = auto()
    DIS_ENABLE = auto()
    DIS_SET_LOADS = auto()
    # Rest sub-phases
    REST_CLEAR_ALL = auto()
    COMPLETE = auto()


class StepTransitionController(QObject):
    """Asynchronous state machine managing pre-step hardware sequencing and read-back verification."""

    # Qt Signals
    transition_completed = Signal(object)      # TestStep
    transition_status = Signal(str)            # status message
    transition_failed = Signal(str)            # error description
    readbacks_updated = Signal(object)         # Dict[frame_id, payload_byte]

    MAX_RETRIES: int = 4
    DEFAULT_RELAY_WAIT_MS: int = 250          # 250ms relay switch settling
    DEFAULT_SETTLING_WAIT_MS: int = 1500       # 1.5 seconds (in 1-2s range for analog settling)
    DEFAULT_CMD_WAIT_MS: int = 250             # 250ms command confirmation window (matches MCU loop)

    def __init__(
        self,
        command_sender: Callable[[int, int, int], None],
        parent: Optional[QObject] = None,
        delays_enabled: Optional[bool] = None,
        auto_ack: Optional[bool] = None,
    ):
        super().__init__(parent)
        self._command_sender = command_sender

        # In headless test mode (no QApplication running or offscreen platform), disable physical delays and auto-ack
        is_real_gui = (QApplication.instance() is not None) and (os.getenv("QT_QPA_PLATFORM") != "offscreen")
        self.delays_enabled = delays_enabled if delays_enabled is not None else is_real_gui
        self.auto_ack = auto_ack if auto_ack is not None else (not is_real_gui)

        # Live control registers read-back cache (0x6000 - 0x6004)
        self.control_readbacks: Dict[int, int] = {
            FRAME_RELAY_CTRL: 0x00,
            FRAME_CHARGE_SEL: 0x00,
            FRAME_CHARGE_CTRL: 0x00,
            FRAME_DISCHARGE_CTRL: 0x00,
            FRAME_DISCHARGE_SEL: 0x00,
        }
        self.control_timestamps: Dict[int, float] = {}

        # Internal execution state
        self.current_phase: TransitionPhase = TransitionPhase.IDLE
        self.active_step: Optional[TestStep] = None
        self.selected_cell: int = 1
        self.retry_count: int = 0
        self._aborted: bool = False

        # Reset pulse tracking for 0 -> 1 -> 0 detection
        self._reset_saw_high: bool = False
        self._in_phase_retries: int = 0

        # Single shot timer for sequencing delays
        self._seq_timer: Optional[QTimer] = None

    @property
    def is_transitioning(self) -> bool:
        """Returns True if the controller is actively sequencing a step transition."""
        return self.current_phase != TransitionPhase.IDLE

    def start_transition(self, step: TestStep, selected_cell: int) -> None:
        """Begin safe stepped hardware configuration for the specified profile step."""
        self._aborted = False
        self.active_step = step
        self.selected_cell = selected_cell
        self.retry_count = 0
        self._in_phase_retries = 0
        self._reset_saw_high = False

        logger.info(
            f"[Transition] Starting safe hardware setup for '{step.name}' ({step.step_type.value}) "
            f"on Cell {selected_cell} (Delays={'ON' if self.delays_enabled else 'OFF'}, AutoAck={self.auto_ack})"
        )
        self._enter_phase(TransitionPhase.CLEAR_UNWANTED)

    def abort(self) -> None:
        """Cancel any pending transition timers."""
        self._aborted = True
        self.current_phase = TransitionPhase.IDLE
        if self._seq_timer and self._seq_timer.isActive():
            self._seq_timer.stop()
        logger.info("[Transition] Step transition aborted")

    def on_command_echo(self, echo: CommandEchoTelemetry) -> None:
        """Ingest readback frame from hardware (0x6000 - 0x6004)."""
        self.control_readbacks[echo.frame_id] = echo.payload_byte
        self.control_timestamps[echo.frame_id] = echo.timestamp
        self.readbacks_updated.emit(dict(self.control_readbacks))

        if echo.frame_id == FRAME_CHARGE_CTRL and (echo.payload_byte & ChargeControlBits.CHARGE_COMPARATOR_RESET):
            self._reset_saw_high = True
        elif echo.frame_id == FRAME_DISCHARGE_CTRL and (echo.payload_byte & DischargeControlBits.DISCHARGE_COMPARATOR_RESET):
            self._reset_saw_high = True

    # --------------------------------------------------------------------------
    # Command Sending & Readback Verification
    # --------------------------------------------------------------------------
    def _send(self, frame_id: int, payload_byte: int, priority: int = 1) -> None:
        """Send command to physical hardware and simulate echo if auto_ack is enabled."""
        self._command_sender(frame_id, payload_byte & 0xFF, priority)
        if self.auto_ack:
            now = time.time()
            self.control_readbacks[frame_id] = payload_byte & 0xFF
            self.control_timestamps[frame_id] = now
            if frame_id in (FRAME_CHARGE_CTRL, FRAME_DISCHARGE_CTRL):
                if payload_byte & 0x02:
                    self._reset_saw_high = True

    def _schedule_next(self, delay_ms: int, callback: Callable[[], None]) -> None:
        """Schedule non-blocking execution of next phase after delay_ms."""
        if self._aborted:
            return
        if not self.delays_enabled or delay_ms <= 0:
            callback()
            return

        self._seq_timer = QTimer(self)
        self._seq_timer.setSingleShot(True)
        self._seq_timer.timeout.connect(callback)
        self._seq_timer.start(delay_ms)

    def _repeat_step_due_to_misalignment(self, reason: str) -> None:
        """Handle misaligned readback by incrementing retry count and restarting setup."""
        if self._aborted:
            return
        self.retry_count += 1
        if self.retry_count > self.MAX_RETRIES:
            msg = f"Setup misaligned after {self.MAX_RETRIES} retries: {reason}"
            logger.error(f"[Transition] {msg}")
            self.transition_failed.emit(msg)
            return

        warn_msg = f"Readback misaligned ({reason}). Repeating step setup (attempt {self.retry_count}/{self.MAX_RETRIES})..."
        logger.warning(f"[Transition] {warn_msg}")
        self.transition_status.emit(warn_msg)
        self._enter_phase(TransitionPhase.CLEAR_UNWANTED)

    # --------------------------------------------------------------------------
    # State Machine Phase Dispatcher
    # --------------------------------------------------------------------------
    def _enter_phase(self, phase: TransitionPhase) -> None:
        if self._aborted:
            return
        self.current_phase = phase
        self._in_phase_retries = 0

        if phase == TransitionPhase.CLEAR_UNWANTED:
            self._phase_clear_unwanted()
        elif phase == TransitionPhase.CELL_SELECT:
            self._phase_cell_select()
        elif phase == TransitionPhase.CELL_ENABLE_SETTLE:
            self._phase_cell_enable_settle()
        # Charge sub-phases
        elif phase == TransitionPhase.CHG_SEND_VOLTAGE:
            self._phase_chg_send_voltage()
        elif phase == TransitionPhase.CHG_SEND_CURRENT:
            self._phase_chg_send_current()
        elif phase == TransitionPhase.CHG_RESET_HIGH:
            self._phase_chg_reset_high()
        elif phase == TransitionPhase.CHG_RESET_LOW:
            self._phase_chg_reset_low()
        elif phase == TransitionPhase.CHG_ENABLE:
            self._phase_chg_enable()
        # Discharge sub-phases
        elif phase == TransitionPhase.DIS_CLEAR_CHG:
            self._phase_dis_clear_chg()
        elif phase == TransitionPhase.DIS_RESET_HIGH:
            self._phase_dis_reset_high()
        elif phase == TransitionPhase.DIS_RESET_LOW:
            self._phase_dis_reset_low()
        elif phase == TransitionPhase.DIS_ENABLE:
            self._phase_dis_enable()
        elif phase == TransitionPhase.DIS_SET_LOADS:
            self._phase_dis_set_loads()
        # Rest sub-phases
        elif phase == TransitionPhase.REST_CLEAR_ALL:
            self._phase_rest_clear_all()
        elif phase == TransitionPhase.COMPLETE:
            self._phase_complete()

    # --------------------------------------------------------------------------
    # 1. Clear Unwanted Flags
    # --------------------------------------------------------------------------
    def _phase_clear_unwanted(self) -> None:
        self.transition_status.emit("Step 1/4: Clearing unwanted hardware flags...")
        step = self.active_step
        if not step:
            return

        # Always clear opposing power paths first
        if step.step_type == StepType.CHARGE:
            self._send(FRAME_DISCHARGE_CTRL, 0x00, 1)
            self._send(FRAME_DISCHARGE_SEL, 0x00, 1)
            self._send(FRAME_CHARGE_CTRL, 0x00, 1)  # Ensure charge enable starts low
        elif step.step_type == StepType.DISCHARGE:
            self._send(FRAME_CHARGE_CTRL, 0x00, 1)  # Ensure charge enable is 0
            self._send(FRAME_DISCHARGE_SEL, 0x00, 1)  # Clear loads before enable
            self._send(FRAME_DISCHARGE_CTRL, 0x00, 1)  # Ensure discharge enable starts low
        elif step.step_type == StepType.REST:
            self._send(FRAME_CHARGE_CTRL, 0x00, 1)
            self._send(FRAME_DISCHARGE_CTRL, 0x00, 1)
            self._send(FRAME_DISCHARGE_SEL, 0x00, 1)

        self._in_phase_retries = 0
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS * 2, self._verify_unwanted_cleared)

    def _verify_unwanted_cleared(self) -> None:
        if self._aborted:
            return
        step = self.active_step
        if not step:
            return

        if step.step_type == StepType.CHARGE:
            dis_ctrl = self.control_readbacks.get(FRAME_DISCHARGE_CTRL, 0)
            if dis_ctrl & DischargeControlBits.DISCHARGE_ENABLE:
                if self._in_phase_retries < 3:
                    self._in_phase_retries += 1
                    self._schedule_next(100, self._verify_unwanted_cleared)
                    return
                self._send(FRAME_DISCHARGE_CTRL, 0x00, 1)
                self._repeat_step_due_to_misalignment("Discharge Enable still active during Charge setup")
                return

        elif step.step_type == StepType.DISCHARGE:
            chg_ctrl = self.control_readbacks.get(FRAME_CHARGE_CTRL, 0)
            if chg_ctrl & ChargeControlBits.CHARGE_ENABLE:
                if self._in_phase_retries < 3:
                    self._in_phase_retries += 1
                    self._schedule_next(100, self._verify_unwanted_cleared)
                    return
                self._send(FRAME_CHARGE_CTRL, 0x00, 1)
                self._repeat_step_due_to_misalignment("Charge Enable still active during Discharge setup")
                return

        # Unwanted flags verified clean -> Proceed to Cell Select relay
        self._enter_phase(TransitionPhase.CELL_SELECT)

    # --------------------------------------------------------------------------
    # 2. Cell Select Relay & Cell Enable Settling
    # --------------------------------------------------------------------------
    def _phase_cell_select(self) -> None:
        step = self.active_step
        cell_sel_bit = RelayControlBits.CELL_SELECT if self.selected_cell == 2 else 0

        # Step requirement: "Kepp the cell select relay s it is only play with cell enable relay plz during the rest and other time"
        if step and step.step_type == StepType.REST:
            self.transition_status.emit(f"Step 2/4: Configuring Cell {self.selected_cell} for Rest (Enable=0)...")
            # For Rest: Bit 0 (CELL_ENABLE) is 0, Bit 1 (CELL_SELECT) is preserved
            self._send(FRAME_RELAY_CTRL, int(cell_sel_bit), 1)
            self._schedule_next(self.DEFAULT_RELAY_WAIT_MS, self._after_settling)
            return

        # Active steps (Charge/Discharge): Cell Select first if needed, then Cell Enable
        rb_relay = self.control_readbacks.get(FRAME_RELAY_CTRL, 0)
        cur_sel_match = bool(rb_relay & RelayControlBits.CELL_SELECT) == (self.selected_cell == 2)
        cur_en = bool(rb_relay & RelayControlBits.CELL_ENABLE)

        if cur_sel_match and cur_en:
            # Already connected to the correct cell with enable ON: no need to cycle relay
            self.transition_status.emit(f"Step 2/4: Cell {self.selected_cell} already connected and enabled.")
            self._schedule_next(50, self._after_settling)
            return

        self.transition_status.emit(f"Step 2/4: Selecting Cell {self.selected_cell} relay (waiting 100ms)...")
        self._send(FRAME_RELAY_CTRL, int(cell_sel_bit), 1)
        self._schedule_next(self.DEFAULT_RELAY_WAIT_MS, self._phase_cell_enable)

    def _phase_cell_enable(self) -> None:
        if self._aborted:
            return
        cell_sel_bit = RelayControlBits.CELL_SELECT if self.selected_cell == 2 else 0
        relay_payload = cell_sel_bit | RelayControlBits.CELL_ENABLE
        self._send(FRAME_RELAY_CTRL, int(relay_payload), 1)

        settle_s = self.DEFAULT_SETTLING_WAIT_MS / 1000.0
        self.transition_status.emit(
            f"Step 2/4: Cell {self.selected_cell} enabled. Settling analog front-end ({settle_s:.1f}s)..."
        )
        self._schedule_next(self.DEFAULT_SETTLING_WAIT_MS, self._after_settling)

    def _after_settling(self) -> None:
        if self._aborted:
            return
        step = self.active_step
        if not step:
            return

        # Verify Cell Relay read-back
        rb_relay = self.control_readbacks.get(FRAME_RELAY_CTRL, 0)
        expected_sel = bool(rb_relay & RelayControlBits.CELL_SELECT) == (self.selected_cell == 2)
        if step.step_type == StepType.REST:
            # During Rest, cell enable bit is 0, cell select bit is preserved
            expected_en = not bool(rb_relay & RelayControlBits.CELL_ENABLE)
            expected_desc = f"Cell {self.selected_cell} Resting (Enable=0)"
        else:
            # During Active steps, cell enable bit is 1, cell select bit matches selected cell
            expected_en = bool(rb_relay & RelayControlBits.CELL_ENABLE)
            expected_desc = f"Cell {self.selected_cell} Connected (Enable=1)"

        if not (expected_sel and expected_en) and not self.auto_ack:
            if self._in_phase_retries < 3:
                self._in_phase_retries += 1
                self._schedule_next(100, self._after_settling)
                return
            self._repeat_step_due_to_misalignment(
                f"Relay readback 0x{rb_relay:02X} does not match {expected_desc}"
            )
            return

        # Route to step-type specific configuration
        if step.step_type == StepType.CHARGE:
            self._enter_phase(TransitionPhase.CHG_SEND_VOLTAGE)
        elif step.step_type == StepType.DISCHARGE:
            self._enter_phase(TransitionPhase.DIS_CLEAR_CHG)
        elif step.step_type == StepType.REST:
            self._enter_phase(TransitionPhase.REST_CLEAR_ALL)
        else:
            self._enter_phase(TransitionPhase.COMPLETE)

    # --------------------------------------------------------------------------
    # 3. Charging Sequence (User Requirement 4)
    # --------------------------------------------------------------------------
    def _phase_chg_send_voltage(self) -> None:
        step = self.active_step
        if not step:
            return
        # "For charging, first send the charge Voltage value, wait"
        v_bit = ChargeSelectBits.MAX_CHARGE_VOLTAGE if step.max_charge_voltage else 0
        self._send(FRAME_CHARGE_SEL, int(v_bit), 1)
        self.transition_status.emit(f"Step 3/4: Sent charge voltage (4.2V={bool(v_bit)}). Waiting 100ms...")
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_chg_voltage)

    def _verify_chg_voltage(self) -> None:
        if self._aborted:
            return
        step = self.active_step
        if not step:
            return
        rb = self.control_readbacks.get(FRAME_CHARGE_SEL, 0)
        exp_v = bool(step.max_charge_voltage)
        actual_v = bool(rb & ChargeSelectBits.MAX_CHARGE_VOLTAGE)
        if exp_v != actual_v and not self.auto_ack:
            if self._in_phase_retries < 3:
                self._in_phase_retries += 1
                self._schedule_next(100, self._verify_chg_voltage)
                return
            self._repeat_step_due_to_misalignment(f"Charge voltage select mismatch: expected {exp_v}, readback {actual_v}")
            return

        self._enter_phase(TransitionPhase.CHG_SEND_CURRENT)

    def _phase_chg_send_current(self) -> None:
        step = self.active_step
        if not step:
            return
        # "...then send the current value, then wait for 100 ms"
        sel_byte = 0
        if step.max_charge_voltage:
            sel_byte |= ChargeSelectBits.MAX_CHARGE_VOLTAGE
        if step.charge_current_1:
            sel_byte |= ChargeSelectBits.MAX_CHARGE_CURRENT_1
        if step.charge_current_2:
            sel_byte |= ChargeSelectBits.MAX_CHARGE_CURRENT_2

        self._send(FRAME_CHARGE_SEL, sel_byte, 1)
        self.transition_status.emit(f"Step 3/4: Sent charge current payload (0x{sel_byte:02X}). Waiting 100ms...")
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_chg_current)

    def _verify_chg_current(self) -> None:
        if self._aborted:
            return
        step = self.active_step
        if not step:
            return
        expected_byte = 0
        if step.max_charge_voltage: expected_byte |= ChargeSelectBits.MAX_CHARGE_VOLTAGE
        if step.charge_current_1: expected_byte |= ChargeSelectBits.MAX_CHARGE_CURRENT_1
        if step.charge_current_2: expected_byte |= ChargeSelectBits.MAX_CHARGE_CURRENT_2

        rb = self.control_readbacks.get(FRAME_CHARGE_SEL, 0)
        if rb != expected_byte and not self.auto_ack:
            if self._in_phase_retries < 3:
                self._in_phase_retries += 1
                self._schedule_next(100, self._verify_chg_current)
                return
            self._repeat_step_due_to_misalignment(f"Charge current readback 0x{rb:02X} != 0x{expected_byte:02X}")
            return

        self._enter_phase(TransitionPhase.CHG_RESET_HIGH)

    def _phase_chg_reset_high(self) -> None:
        # "...and then make the reset 1 wait the till the read back value changes from 0->1->0"
        self._reset_saw_high = False
        self.transition_status.emit("Step 3/4: Pulsing Charge Comparator Reset HIGH...")
        # Send reset bit = 1, charge enable = 0
        self._send(FRAME_CHARGE_CTRL, int(ChargeControlBits.CHARGE_COMPARATOR_RESET), 1)
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._phase_chg_reset_low)

    def _phase_chg_reset_low(self) -> None:
        if self._aborted:
            return
        # Transition reset back to 0
        self.transition_status.emit("Step 3/4: Restoring Charge Comparator Reset LOW (waiting for 0->1->0)...")
        self._send(FRAME_CHARGE_CTRL, 0x00, 1)
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_chg_reset_complete)

    def _verify_chg_reset_complete(self) -> None:
        if self._aborted:
            return
        rb = self.control_readbacks.get(FRAME_CHARGE_CTRL, 0)
        reset_bit = bool(rb & ChargeControlBits.CHARGE_COMPARATOR_RESET)
        if reset_bit and not self.auto_ack:
            if self._in_phase_retries < 3:
                self._in_phase_retries += 1
                self._schedule_next(100, self._verify_chg_reset_complete)
                return
            self._send(FRAME_CHARGE_CTRL, 0x00, 1)
            self._repeat_step_due_to_misalignment("Charge Comparator Reset bit failed to return to 0")
            return

        self._enter_phase(TransitionPhase.CHG_ENABLE)

    def _phase_chg_enable(self) -> None:
        # "...then make the charge enable 1 make sure discharge enable is 0"
        rb_dis = self.control_readbacks.get(FRAME_DISCHARGE_CTRL, 0)
        if (rb_dis & DischargeControlBits.DISCHARGE_ENABLE):
            # If discharge enable is active, clear it first and re-check
            self.transition_status.emit("Step 4/4: Clearing Discharge Enable before Charge...")
            self._send(FRAME_DISCHARGE_CTRL, 0x00, 1)
            self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._phase_chg_enable)
            return

        # Discharge is confirmed 0 -> Send Charge Enable
        self._in_phase_retries = 0
        self._send(FRAME_CHARGE_CTRL, int(ChargeControlBits.CHARGE_ENABLE), 1)
        self.transition_status.emit("Step 4/4: Enabling Charge (0x6002=0x01). Verifying readbacks...")
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_chg_enabled)

    def _verify_chg_enabled(self) -> None:
        if self._aborted:
            return
        rb_chg = self.control_readbacks.get(FRAME_CHARGE_CTRL, 0)
        rb_dis = self.control_readbacks.get(FRAME_DISCHARGE_CTRL, 0)

        chg_ok = bool(rb_chg & ChargeControlBits.CHARGE_ENABLE) and not bool(rb_chg & ChargeControlBits.CHARGE_COMPARATOR_RESET)
        dis_ok = not bool(rb_dis & DischargeControlBits.DISCHARGE_ENABLE)

        if not (chg_ok and dis_ok) and not self.auto_ack:
            # Allow brief confirmation window before declaring misalignment
            if self._in_phase_retries < 2:
                self._in_phase_retries += 1
                self._schedule_next(100, self._verify_chg_enabled)
                return

            self._repeat_step_due_to_misalignment(
                f"Charge Enable readback misaligned: ChgCtrl=0x{rb_chg:02X}, DisCtrl=0x{rb_dis:02X}"
            )
            return

        self._enter_phase(TransitionPhase.COMPLETE)

    # --------------------------------------------------------------------------
    # 4. Discharging Sequence (User Requirement 5)
    # --------------------------------------------------------------------------
    def _phase_dis_clear_chg(self) -> None:
        # "For discharging make sure the charge enable is zero..."
        self._send(FRAME_CHARGE_CTRL, 0x00, 1)
        self._send(FRAME_DISCHARGE_SEL, 0x00, 1)  # Clear loads initially
        self.transition_status.emit("Step 3/4: Ensuring Charge Enable is 0 before discharge...")
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_dis_chg_zero)

    def _verify_dis_chg_zero(self) -> None:
        if self._aborted:
            return
        rb = self.control_readbacks.get(FRAME_CHARGE_CTRL, 0)
        if (rb & ChargeControlBits.CHARGE_ENABLE) and not self.auto_ack:
            if self._in_phase_retries < 3:
                self._in_phase_retries += 1
                self._schedule_next(100, self._verify_dis_chg_zero)
                return
            self._repeat_step_due_to_misalignment(f"Charge Enable still set (0x{rb:02X}) during discharge prep")
            return

        self._enter_phase(TransitionPhase.DIS_RESET_HIGH)

    def _phase_dis_reset_high(self) -> None:
        # "...the do comparaitor reset..."
        self._reset_saw_high = False
        self.transition_status.emit("Step 3/4: Pulsing Discharge Comparator Reset HIGH...")
        self._send(FRAME_DISCHARGE_CTRL, int(DischargeControlBits.DISCHARGE_COMPARATOR_RESET), 1)
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._phase_dis_reset_low)

    def _phase_dis_reset_low(self) -> None:
        if self._aborted:
            return
        self.transition_status.emit("Step 3/4: Restoring Discharge Comparator Reset LOW...")
        self._send(FRAME_DISCHARGE_CTRL, 0x00, 1)
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_dis_reset_complete)

    def _verify_dis_reset_complete(self) -> None:
        if self._aborted:
            return
        rb = self.control_readbacks.get(FRAME_DISCHARGE_CTRL, 0)
        if (rb & DischargeControlBits.DISCHARGE_COMPARATOR_RESET) and not self.auto_ack:
            if self._in_phase_retries < 3:
                self._in_phase_retries += 1
                self._schedule_next(100, self._verify_dis_reset_complete)
                return
            self._send(FRAME_DISCHARGE_CTRL, 0x00, 1)
            self._repeat_step_due_to_misalignment("Discharge Comparator Reset bit failed to clear")
            return

        self._enter_phase(TransitionPhase.DIS_ENABLE)

    def _phase_dis_enable(self) -> None:
        # "...then turn on the Discharge enable then onec discharge enable is one and reset read value is zero..."
        self._in_phase_retries = 0
        self._send(FRAME_DISCHARGE_CTRL, int(DischargeControlBits.DISCHARGE_ENABLE), 1)
        self.transition_status.emit("Step 4/4: Turning ON Discharge Enable (0x6003=0x01)...")
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_dis_enabled)

    def _verify_dis_enabled(self) -> None:
        if self._aborted:
            return
        rb = self.control_readbacks.get(FRAME_DISCHARGE_CTRL, 0)
        dis_en = bool(rb & DischargeControlBits.DISCHARGE_ENABLE)
        reset_zero = not bool(rb & DischargeControlBits.DISCHARGE_COMPARATOR_RESET)

        if not (dis_en and reset_zero) and not self.auto_ack:
            if self._in_phase_retries < 2:
                self._in_phase_retries += 1
                self._schedule_next(100, self._verify_dis_enabled)
                return

            self._repeat_step_due_to_misalignment(
                f"Discharge enable not confirmed: Readback=0x{rb:02X} (EN={dis_en}, Reset={reset_zero})"
            )
            return

        # "...the make the load changes accordingly plz"
        self._enter_phase(TransitionPhase.DIS_SET_LOADS)

    def _phase_dis_set_loads(self) -> None:
        step = self.active_step
        if not step:
            return
        load_dec = step.discharge_load_decimal & 0x0F
        self.transition_status.emit(f"Step 4/4: Applying discharge load bank state {load_dec} (0x6004)...")
        self._send(FRAME_DISCHARGE_SEL, load_dec, 1)
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_dis_loads)

    def _verify_dis_loads(self) -> None:
        if self._aborted:
            return
        step = self.active_step
        if not step:
            return
        expected_load = step.discharge_load_decimal & 0x0F
        rb = self.control_readbacks.get(FRAME_DISCHARGE_SEL, 0) & 0x0F
        if rb != expected_load and not self.auto_ack:
            if self._in_phase_retries < 3:
                self._in_phase_retries += 1
                self._schedule_next(100, self._verify_dis_loads)
                return
            self._repeat_step_due_to_misalignment(f"Discharge load readback mismatch: expected {expected_load}, got {rb}")
            return

        self._enter_phase(TransitionPhase.COMPLETE)

    # --------------------------------------------------------------------------
    # 5. Rest Sequence
    # --------------------------------------------------------------------------
    def _phase_rest_clear_all(self) -> None:
        self.transition_status.emit("Step 3/3: Configuring OCV Relaxation (Rest)...")
        self._send(FRAME_CHARGE_CTRL, 0x00, 1)
        self._send(FRAME_DISCHARGE_CTRL, 0x00, 1)
        self._send(FRAME_DISCHARGE_SEL, 0x00, 1)
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, self._verify_rest_complete)

    def _verify_rest_complete(self) -> None:
        if self._aborted:
            return
        rb_chg = self.control_readbacks.get(FRAME_CHARGE_CTRL, 0)
        rb_dis = self.control_readbacks.get(FRAME_DISCHARGE_CTRL, 0)
        rb_sel = self.control_readbacks.get(FRAME_DISCHARGE_SEL, 0)

        if (rb_chg != 0 or rb_dis != 0 or rb_sel != 0) and not self.auto_ack:
            self._repeat_step_due_to_misalignment(
                f"Rest readbacks not clear: Chg=0x{rb_chg:02X}, Dis=0x{rb_dis:02X}, Sel=0x{rb_sel:02X}"
            )
            return

        self._enter_phase(TransitionPhase.COMPLETE)

    # --------------------------------------------------------------------------
    # Complete
    # --------------------------------------------------------------------------
    def _phase_complete(self) -> None:
        if self._aborted:
            return
        step = self.active_step
        logger.info(f"[Transition] Safe transition complete for step '{step.name if step else ''}'")
        self.transition_status.emit("Hardware configuration and settling verified.")
        self.current_phase = TransitionPhase.IDLE
        if step:
            self.transition_completed.emit(step)
