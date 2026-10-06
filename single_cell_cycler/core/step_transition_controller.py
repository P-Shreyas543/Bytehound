"""Step Transition Controller for Single-Cell BMS Cycler.

Every register write is confirmed by its 0x6000-0x6004 readback before the next write is
issued: the readback is polled every 100 ms, the write is resent on mismatch, and the
sequence fails after MAX_RETRIES resends.

0x6000 carries two relays: Bit 1 = Cell Select relay (0 = Cell 1, 1 = Cell 2) and
Bit 0 = Cell Enable relay (1 = cell connected). The Cell Select relay is never moved while
the Cell Enable relay is closed.

Charge / Discharge step on Cell N:
  1. Drives off: 0x6002=0, 0x6003=0, 0x6004=0 (each confirmed); Discharge and Rest also 0x6001=0
  2. Cell Select relay confirmed on Cell N (rewritten with Enable open if not)
  3. Cell Enable relay closed (0x6000 = Select|Enable) confirmed, then analog settling.
     Skipped only when this test already closed it in an earlier step and it still reads closed.
  Charge:
  4. 0x6001 = voltage bit            5. 0x6001 = voltage | current bits
  6. 0x6002 = reset (seen set)       7. 0x6002 = 0 (reset cleared)
  8. Relay still closed -> 0x6002 = Charge Enable -> relay still closed
  Discharge:
  4. 0x6003 = reset (seen set)       5. 0x6003 = 0 (reset cleared)
  6. Relay still closed -> 0x6003 = Discharge Enable -> relay still closed
  7. 0x6004 = load bank
Rest step on Cell N:
  1. Drives off (0x6002, 0x6003, 0x6004, 0x6001)   2. Cell Enable relay opened, Cell Select kept
Every step ends with a final audit of all five readbacks before the step is reported complete.

Safe idle (stop / pause / safety stop): 0x6002=0, 0x6003=0, then 0x6001=0, 0x6004=0, then
0x6000=0, each confirmed. From Cell 2 connected (3) the relay goes 3 -> 2 -> 0 so the Cell Enable
relay is confirmed open before Cell Select moves back to Cell 1. A write that cannot be
confirmed does not block the rest of the shutdown; it is reported via safe_idle_unconfirmed.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional

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
    RelayControlBits,
)
from .profile_model import StepType, TestStep

logger = logging.getLogger("SingleCellCycler.StepTransition")

_RELAY_MASK = int(RelayControlBits.CELL_SELECT | RelayControlBits.CELL_ENABLE)

_REGISTER_NAMES = {
    FRAME_RELAY_CTRL: "Relay",
    FRAME_CHARGE_SEL: "Charge Select",
    FRAME_CHARGE_CTRL: "Charge Control",
    FRAME_DISCHARGE_CTRL: "Discharge Control",
    FRAME_DISCHARGE_SEL: "Discharge Load",
}


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
    # Stop / pause / safety stop
    SAFE_IDLE = auto()


@dataclass
class _Op:
    """One entry of a sequence plan.

    kind "write":  send value to frame_id and wait for the readback to confirm it.
    kind "wait":   send nothing; wait for the board to bring frame_id's readback to value by
                   itself (self-clearing comparator reset). If it does not, write it.
    kind "check":  run check(); a returned reason restarts the whole step setup.
    kind "expand": replaced at execution time by the ops returned from expand(), so the
                   plan can depend on readbacks confirmed by earlier ops.
    """

    kind: str
    phase: TransitionPhase
    desc: str = ""
    frame_id: int = 0
    value: int = 0
    confirm: Optional[Callable[[int], bool]] = None  # default: readback == value
    settle_ms: int = 0
    pulse: bool = False  # comparator reset: confirmed if the set bit was seen at any point
    on_confirmed: Optional[Callable[[], None]] = None
    check: Optional[Callable[[], Optional[str]]] = None
    on_check_fail: List[tuple] = field(default_factory=list)  # (frame_id, value) sent before restart
    expand: Optional[Callable[[], List["_Op"]]] = None
    in_burst: bool = True  # False: never sent unconfirmed by the silent-board shutdown burst


class StepTransitionController(QObject):
    """Asynchronous state machine managing pre-step hardware sequencing and read-back verification."""

    # Qt Signals
    transition_completed = Signal(object)      # TestStep
    transition_status = Signal(str)            # status message
    transition_failed = Signal(str)            # error description
    readbacks_updated = Signal(object)         # Dict[frame_id, payload_byte]
    safe_idle_unconfirmed = Signal(str)        # safe-idle writes whose readback never confirmed

    MAX_RETRIES: int = 4
    DEFAULT_RELAY_WAIT_MS: int = 250          # 250ms relay switch settling
    DEFAULT_SETTLING_WAIT_MS: int = 1500       # 1.5 seconds (in 1-2s range for analog settling)
    DEFAULT_CMD_WAIT_MS: int = 250             # 250ms command confirmation window (matches MCU loop)
    CONFIRM_POLL_MS: int = 100                 # readback re-check interval after the first window
    CONFIRM_POLLS: int = 3                     # re-checks before the write is resent
    DISCHARGE_STAGE_WAIT_MS: int = 500         # pause after Discharge Enable and after its reset pulse
    SELF_CLEAR_TIMEOUT_MS: int = 3000          # board clears the reset bit in ~0.3 s; then clear it ourselves

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
        self.retry_count: int = 0          # whole-sequence restarts after a failed check
        self._aborted: bool = False

        # True once this test closed the Cell Enable relay; cleared by safe idle, rest, or a new test
        self.relay_owned_by_test: bool = False

        # Reset pulse tracking for 0 -> 1 -> 0 detection
        self._reset_saw_high: bool = False

        # Sequence executor
        self._mode: str = "idle"           # "transition" | "safe_idle" | "idle"
        self._ops: List[_Op] = []
        self._op_idx: int = 0
        self._write_attempts: int = 0
        self._polls: int = 0
        self._unconfirmed: List[str] = []
        self._idle_priority: int = 0       # TX priority for safe-idle / idle cell-select writes
        self._burst_sent: bool = False     # safe idle already fell back to an immediate burst
        # Echo freshness: a write is confirmed only by an echo received after it was issued
        self._echo_seq: int = 0
        self._echo_seq_by_frame: Dict[int, int] = {}
        self._issue_seq: int = 0
        self._gen: int = 0                 # bumped on abort/restart; stale timer callbacks are dropped

        # Single shot timer for sequencing delays
        self._seq_timer: Optional[QTimer] = None

    @property
    def is_transitioning(self) -> bool:
        """Returns True if the controller is actively sequencing a step transition."""
        return self._mode == "transition" and self.current_phase != TransitionPhase.IDLE

    @property
    def is_safe_idling(self) -> bool:
        """True while a confirmed safe-idle / idle cell-select sequence still has writes pending."""
        return self._mode == "safe_idle"

    # --------------------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------------------
    def start_transition(self, step: TestStep, selected_cell: int) -> None:
        """Begin safe stepped hardware configuration for the specified profile step."""
        self._cancel_pending()
        self._aborted = False
        self.active_step = step
        self.selected_cell = selected_cell
        self.retry_count = 0
        self._reset_saw_high = False

        logger.info(
            f"[Transition] Starting safe hardware setup for '{step.name}' ({step.step_type.value}) "
            f"on Cell {selected_cell} (Delays={'ON' if self.delays_enabled else 'OFF'}, AutoAck={self.auto_ack})"
        )
        self._mode = "transition"
        self._run_ops(self._plan_step(step))

    def abort(self) -> None:
        """Cancel any pending transition timers."""
        self._aborted = True
        self._cancel_pending()
        self._mode = "idle"
        self.current_phase = TransitionPhase.IDLE
        logger.info("[Transition] Step transition aborted")

    def safe_idle(self, selected_cell: int, priority: int = 0, keep_select: bool = False) -> None:
        """De-energize hardware with confirmed writes: charge off, discharge load off then
        discharge off, charge select cleared, then Cell Enable opened.

        keep_select=True (Pause): only the Cell Enable relay opens; Cell Select is left as the
        board reports it. Otherwise (Stop / Safety Stop) 0x6000 ends at 0.

        Cancels any in-progress transition. Unconfirmed writes do not block the remaining
        shutdown writes; they are logged and emitted via safe_idle_unconfirmed.
        """
        self._cancel_pending()
        self._aborted = False
        self.selected_cell = selected_cell
        self.relay_owned_by_test = False
        self._unconfirmed = []
        self._burst_sent = False
        self._mode = "safe_idle"
        self._idle_priority = priority

        ph = TransitionPhase.SAFE_IDLE

        def _relay_to_zero() -> List[_Op]:
            # End state is 0x6000 = 0. With Cell 2 connected (3) the Cell Enable relay opens
            # first (2, confirmed) and only then Cell Select returns to Cell 1 (0), so Select
            # never moves while Enable is closed.
            rb = self.control_readbacks.get(FRAME_RELAY_CTRL, 0) & _RELAY_MASK
            ops = []
            if (rb & RelayControlBits.CELL_ENABLE) and (rb & RelayControlBits.CELL_SELECT):
                ops.append(self._write(ph, FRAME_RELAY_CTRL, int(RelayControlBits.CELL_SELECT),
                                       "Cell Enable relay open (Cell 2 Select kept)"))
            ops.append(self._write(ph, FRAME_RELAY_CTRL, 0x00,
                                   "Relay register zero (Cell Enable off, Cell Select -> Cell 1)",
                                   in_burst=not ops))
            return ops

        def _enable_off_keep_select() -> List[_Op]:
            sel = self.control_readbacks.get(FRAME_RELAY_CTRL, 0) & int(RelayControlBits.CELL_SELECT)
            return [self._write(ph, FRAME_RELAY_CTRL, sel,
                                f"Cell Enable relay open (Cell {2 if sel else 1} Select kept)")]

        # Discharge: load off first, pause, then Discharge Enable off (see _plan_drives_off)
        ops = [
            self._write(ph, FRAME_CHARGE_CTRL, 0x00, "Charge Control off"),
            self._write(ph, FRAME_DISCHARGE_SEL, 0x00, "Discharge Load cleared",
                        settle_ms=self._load_off_wait_ms()),
            self._write(ph, FRAME_DISCHARGE_CTRL, 0x00, "Discharge Control off"),
            self._write(ph, FRAME_CHARGE_SEL, 0x00, "Charge Select cleared"),
            _Op(kind="expand", phase=ph, expand=_enable_off_keep_select if keep_select else _relay_to_zero),
        ]
        self._run_ops(ops)

    def select_cell_idle(self, selected_cell: int) -> None:
        """Move the Cell Select relay to the chosen cell while no test is running (Enable stays open)."""
        if self._mode == "safe_idle" and self._op_idx < len(self._ops):
            # Never cut a running shutdown short: queue the relay move behind it
            self.selected_cell = selected_cell
            self._ops.append(_Op(kind="expand", phase=TransitionPhase.CELL_SELECT,
                                 expand=lambda: self._plan_relay_open(TransitionPhase.CELL_SELECT)))
            return
        self._cancel_pending()
        self._aborted = False
        self.selected_cell = selected_cell
        self.relay_owned_by_test = False
        self._unconfirmed = []
        self._burst_sent = False
        self._mode = "safe_idle"
        self._idle_priority = 1
        self._run_ops(self._plan_relay_open(TransitionPhase.CELL_SELECT))

    def on_command_echo(self, echo: CommandEchoTelemetry) -> None:
        """Ingest readback frame from hardware (0x6000 - 0x6004)."""
        self.control_readbacks[echo.frame_id] = echo.payload_byte
        self.control_timestamps[echo.frame_id] = echo.timestamp
        self._echo_seq += 1
        self._echo_seq_by_frame[echo.frame_id] = self._echo_seq
        self.readbacks_updated.emit(dict(self.control_readbacks))

        if echo.frame_id == FRAME_CHARGE_CTRL and (echo.payload_byte & ChargeControlBits.CHARGE_COMPARATOR_RESET):
            self._reset_saw_high = True
        elif echo.frame_id == FRAME_DISCHARGE_CTRL and (echo.payload_byte & DischargeControlBits.DISCHARGE_COMPARATOR_RESET):
            self._reset_saw_high = True

    # --------------------------------------------------------------------------
    # Sequence plans
    # --------------------------------------------------------------------------
    @staticmethod
    def _select_bit(cell: int) -> int:
        return int(RelayControlBits.CELL_SELECT) if cell == 2 else 0

    def _write(self, phase: TransitionPhase, frame_id: int, value: int, desc: str, **kw) -> _Op:
        return _Op(kind="write", phase=phase, desc=desc, frame_id=frame_id, value=value & 0xFF, **kw)

    def _plan_step(self, step: TestStep) -> List[_Op]:
        ops = self._plan_drives_off()
        if step.step_type in (StepType.DISCHARGE, StepType.REST):
            # Charge Select used to stay at the last charge's setting (0x07) through rest and
            # discharge: one wrong 0x6002 bit would then have charged at 1.5 A
            ops.append(self._write(TransitionPhase.CLEAR_UNWANTED, FRAME_CHARGE_SEL, 0x00,
                                   "Step 1/4: Charge Select cleared"))
        if step.step_type == StepType.CHARGE:
            ops += [_Op(kind="expand", phase=TransitionPhase.CELL_SELECT, expand=self._plan_relay_connect)]
            ops += self._plan_charge(step)
        elif step.step_type == StepType.DISCHARGE:
            ops += [_Op(kind="expand", phase=TransitionPhase.CELL_SELECT, expand=self._plan_relay_connect)]
            ops += self._plan_discharge(step)
        elif step.step_type == StepType.REST:
            ops += [_Op(kind="expand", phase=TransitionPhase.CELL_SELECT,
                        expand=lambda: self._plan_relay_open(TransitionPhase.CELL_SELECT))]
        ops.append(_Op(kind="check", phase=TransitionPhase.COMPLETE, desc="Final readback audit",
                       check=lambda: self._final_audit(step), on_check_fail=self._drives_off_pairs()))
        return ops

    def _plan_drives_off(self) -> List[_Op]:
        # Discharge is switched off load first: the load is removed (current falls to zero),
        # then, after a pause, Discharge Enable is turned off with nothing flowing.
        ph = TransitionPhase.CLEAR_UNWANTED
        return [
            self._write(ph, FRAME_CHARGE_CTRL, 0x00, "Step 1/4: Charge Control cleared"),
            self._write(ph, FRAME_DISCHARGE_SEL, 0x00, "Step 1/4: Discharge Load cleared",
                        settle_ms=self._load_off_wait_ms()),
            self._write(ph, FRAME_DISCHARGE_CTRL, 0x00, "Step 1/4: Discharge Control cleared"),
        ]

    def _load_off_wait_ms(self) -> int:
        """Pause between removing the load and turning Discharge Enable off (only if a load was on)."""
        return self.DISCHARGE_STAGE_WAIT_MS if self.control_readbacks.get(FRAME_DISCHARGE_SEL, 0) & 0x0F else 0

    @staticmethod
    def _drives_off_pairs() -> List[tuple]:
        return [(FRAME_CHARGE_CTRL, 0x00), (FRAME_DISCHARGE_SEL, 0x00), (FRAME_DISCHARGE_CTRL, 0x00)]

    def _plan_select(self, phase: TransitionPhase) -> List[_Op]:
        """Ops that put the Cell Select relay on the chosen cell without moving it under a closed Enable."""
        target_sel = self._select_bit(self.selected_cell)
        rb = self.control_readbacks.get(FRAME_RELAY_CTRL, 0) & _RELAY_MASK
        if (rb & RelayControlBits.CELL_SELECT) == target_sel:
            return []
        ops = []
        if rb & RelayControlBits.CELL_ENABLE:
            ops.append(self._write(phase, FRAME_RELAY_CTRL, rb & RelayControlBits.CELL_SELECT,
                                   "Step 2/4: Opening Cell Enable relay before moving Cell Select"))
        ops.append(self._write(phase, FRAME_RELAY_CTRL, target_sel,
                               f"Step 2/4: Cell Select relay -> Cell {self.selected_cell}",
                               settle_ms=self.DEFAULT_RELAY_WAIT_MS))
        return ops

    def _plan_relay_connect(self) -> List[_Op]:
        closed = self._select_bit(self.selected_cell) | int(RelayControlBits.CELL_ENABLE)
        rb = self.control_readbacks.get(FRAME_RELAY_CTRL, 0) & _RELAY_MASK
        if self.relay_owned_by_test and rb == closed:
            self.transition_status.emit(
                f"Step 2/4: Cell {self.selected_cell} relay already closed by this test (readback 0x{rb:02X})."
            )
            return []

        ops = self._plan_select(TransitionPhase.CELL_SELECT)
        if not ops:
            self.transition_status.emit(
                f"Step 2/4: Cell Select relay confirmed on Cell {self.selected_cell} (readback 0x{rb:02X})."
            )

        def _owned() -> None:
            self.relay_owned_by_test = True

        ops.append(self._write(
            TransitionPhase.CELL_ENABLE_SETTLE, FRAME_RELAY_CTRL, closed,
            f"Step 2/4: Closing Cell Enable relay (Cell {self.selected_cell}), then settling "
            f"{self.DEFAULT_SETTLING_WAIT_MS / 1000.0:.1f}s",
            settle_ms=self.DEFAULT_SETTLING_WAIT_MS, on_confirmed=_owned,
        ))
        return ops

    def _plan_relay_open(self, phase: TransitionPhase) -> List[_Op]:
        """Ops that leave Cell Select on the chosen cell with the Cell Enable relay open."""
        target_sel = self._select_bit(self.selected_cell)
        ops = self._plan_select(phase)
        if not ops:

            def _released() -> None:
                self.relay_owned_by_test = False

            ops.append(self._write(phase, FRAME_RELAY_CTRL, target_sel,
                                   f"Step 2/4: Cell {self.selected_cell} Cell Enable relay open",
                                   on_confirmed=_released))
        else:
            self.relay_owned_by_test = False
        return ops

    def _plan_charge(self, step: TestStep) -> List[_Op]:
        v_bit = int(ChargeSelectBits.MAX_CHARGE_VOLTAGE) if step.max_charge_voltage else 0
        sel_byte = v_bit
        if step.charge_current_1:
            sel_byte |= ChargeSelectBits.MAX_CHARGE_CURRENT_1
        if step.charge_current_2:
            sel_byte |= ChargeSelectBits.MAX_CHARGE_CURRENT_2
        reset = int(ChargeControlBits.CHARGE_COMPARATOR_RESET)
        enable = int(ChargeControlBits.CHARGE_ENABLE)
        return [
            self._write(TransitionPhase.CHG_SEND_VOLTAGE, FRAME_CHARGE_SEL, v_bit,
                        f"Step 3/4: Charge voltage (4.2V={bool(v_bit)})"),
            self._write(TransitionPhase.CHG_SEND_CURRENT, FRAME_CHARGE_SEL, int(sel_byte),
                        f"Step 3/4: Charge current payload (0x{int(sel_byte):02X})"),
            self._write(TransitionPhase.CHG_RESET_HIGH, FRAME_CHARGE_CTRL, reset,
                        "Step 3/4: Charge Comparator Reset set", pulse=True),
            self._write(TransitionPhase.CHG_RESET_LOW, FRAME_CHARGE_CTRL, 0x00,
                        "Step 3/4: Charge Comparator Reset cleared"),
            self._relay_check(TransitionPhase.CHG_ENABLE, []),
            self._write(TransitionPhase.CHG_ENABLE, FRAME_CHARGE_CTRL, enable,
                        "Step 4/4: Charge Enable (0x6002=0x01)"),
            self._relay_check(TransitionPhase.CHG_ENABLE, [(FRAME_CHARGE_CTRL, 0x00)]),
        ]

    def _plan_discharge(self, step: TestStep) -> List[_Op]:
        """Enable first, then pulse the comparator reset with Enable kept on, then select the load.

        The discharge comparator can be left latched by an earlier discharge. Bench-tested on
        the board: a reset pulsed before Enable (0x02 -> 0x00 -> 0x01) does not release the
        latch (0x6003 reads 0x01 but the load bus stays at 0 V and no current flows); a reset
        pulsed while Enable is already on (0x01 -> 0x03) does. The board clears the reset bit
        by itself after ~0.3 s.
        """
        reset = int(DischargeControlBits.DISCHARGE_COMPARATOR_RESET)
        enable = int(DischargeControlBits.DISCHARGE_ENABLE)
        load_dec = step.discharge_load_decimal & 0x0F
        off = [(FRAME_DISCHARGE_CTRL, 0x00)]
        return [
            self._relay_check(TransitionPhase.DIS_ENABLE, []),
            self._write(TransitionPhase.DIS_ENABLE, FRAME_DISCHARGE_CTRL, enable,
                        "Step 3/4: Discharge Enable (0x6003=0x01)",
                        settle_ms=self.DISCHARGE_STAGE_WAIT_MS),
            self._write(TransitionPhase.DIS_RESET_HIGH, FRAME_DISCHARGE_CTRL, enable | reset,
                        "Step 3/4: Discharge Comparator Reset set with Enable on (0x6003=0x03)", pulse=True),
            _Op(kind="wait", phase=TransitionPhase.DIS_RESET_LOW, frame_id=FRAME_DISCHARGE_CTRL, value=enable,
                desc="Step 3/4: Discharge Comparator Reset cleared by the board (0x6003=0x01)",
                settle_ms=self.DISCHARGE_STAGE_WAIT_MS),
            self._relay_check(TransitionPhase.DIS_SET_LOADS, off),
            self._write(TransitionPhase.DIS_SET_LOADS, FRAME_DISCHARGE_SEL, load_dec,
                        f"Step 4/4: Discharge load bank state {load_dec} (0x6004)"),
        ]

    def _relay_check(self, phase: TransitionPhase, on_fail: List[tuple]) -> _Op:
        return _Op(kind="check", phase=phase, desc="Cell Enable relay still closed",
                   check=self._relay_misalignment, on_check_fail=on_fail)

    def _relay_misalignment(self) -> Optional[str]:
        """Return a reason if the relay readback is not the selected cell with Enable=1, else None."""
        if self.auto_ack:
            return None
        rb_relay = self.control_readbacks.get(FRAME_RELAY_CTRL, 0) & _RELAY_MASK
        closed = self._select_bit(self.selected_cell) | int(RelayControlBits.CELL_ENABLE)
        if rb_relay == closed:
            return None
        self.relay_owned_by_test = False
        return f"Relay readback 0x{rb_relay:02X} lost Cell {self.selected_cell} Connected (expected 0x{closed:02X})"

    def _expected_final(self, step: TestStep) -> Dict[int, int]:
        sel_bit = self._select_bit(self.selected_cell)
        if step.step_type == StepType.CHARGE:
            chg_sel = int(ChargeSelectBits.MAX_CHARGE_VOLTAGE) if step.max_charge_voltage else 0
            if step.charge_current_1:
                chg_sel |= ChargeSelectBits.MAX_CHARGE_CURRENT_1
            if step.charge_current_2:
                chg_sel |= ChargeSelectBits.MAX_CHARGE_CURRENT_2
            return {
                FRAME_RELAY_CTRL: sel_bit | int(RelayControlBits.CELL_ENABLE),
                FRAME_CHARGE_SEL: int(chg_sel),
                FRAME_CHARGE_CTRL: int(ChargeControlBits.CHARGE_ENABLE),
                FRAME_DISCHARGE_CTRL: 0x00,
                FRAME_DISCHARGE_SEL: 0x00,
            }
        if step.step_type == StepType.DISCHARGE:
            return {
                FRAME_RELAY_CTRL: sel_bit | int(RelayControlBits.CELL_ENABLE),
                FRAME_CHARGE_SEL: 0x00,
                FRAME_CHARGE_CTRL: 0x00,
                FRAME_DISCHARGE_CTRL: int(DischargeControlBits.DISCHARGE_ENABLE),
                FRAME_DISCHARGE_SEL: step.discharge_load_decimal & 0x0F,
            }
        if step.step_type == StepType.REST:
            return {
                FRAME_RELAY_CTRL: sel_bit,
                FRAME_CHARGE_SEL: 0x00,
                FRAME_CHARGE_CTRL: 0x00,
                FRAME_DISCHARGE_CTRL: 0x00,
                FRAME_DISCHARGE_SEL: 0x00,
            }
        return {}

    def _final_audit(self, step: TestStep) -> Optional[str]:
        """Every register the step depends on must still read its configured value."""
        if self.auto_ack:
            return None
        bad = []
        for fid, exp in self._expected_final(step).items():
            mask = _RELAY_MASK if fid == FRAME_RELAY_CTRL else 0xFF
            rb = self.control_readbacks.get(fid, 0) & mask
            if rb != exp:
                bad.append(f"0x{fid:04X} read 0x{rb:02X} expected 0x{exp:02X}")
        if not bad:
            return None
        if self._expected_final(step).get(FRAME_RELAY_CTRL, 0) & RelayControlBits.CELL_ENABLE:
            rb_relay = self.control_readbacks.get(FRAME_RELAY_CTRL, 0) & _RELAY_MASK
            if not rb_relay & RelayControlBits.CELL_ENABLE:
                self.relay_owned_by_test = False
        return "Final readback audit failed: " + "; ".join(bad)

    # --------------------------------------------------------------------------
    # Sequence executor
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

    def _cancel_pending(self) -> None:
        self._gen += 1
        if self._seq_timer and self._seq_timer.isActive():
            self._seq_timer.stop()

    def _schedule_next(self, delay_ms: int, callback: Callable[[], None]) -> None:
        """Schedule non-blocking execution of next phase after delay_ms."""
        if self._aborted:
            return
        gen = self._gen

        def _guarded() -> None:
            if gen == self._gen and not self._aborted:
                callback()

        if not self.delays_enabled or delay_ms <= 0:
            _guarded()
            return

        self._seq_timer = QTimer(self)
        self._seq_timer.setSingleShot(True)
        self._seq_timer.timeout.connect(_guarded)
        self._seq_timer.start(delay_ms)

    def _run_ops(self, ops: List[_Op]) -> None:
        self._ops = list(ops)
        self._op_idx = 0
        self._next_op()

    def _next_op(self) -> None:
        if self._aborted:
            return
        if self._op_idx >= len(self._ops):
            self._on_sequence_done()
            return

        op = self._ops[self._op_idx]
        self.current_phase = op.phase

        if op.kind == "expand":
            self._ops[self._op_idx:self._op_idx + 1] = op.expand() if op.expand else []
            self._next_op()
            return

        if op.kind == "check":
            reason = op.check() if op.check else None
            if reason:
                for fid, val in op.on_check_fail:
                    self._send(fid, val, 0)
                self._repeat_step_due_to_misalignment(reason)
                return
            self._op_idx += 1
            self._next_op()
            return

        self._write_attempts = 0
        if self._mode == "transition":
            self.transition_status.emit(f"{op.desc}...")
        if op.kind == "wait":
            self._polls = 0
            self._poll_wait(op)
            return
        self._issue_write(op)

    def _poll_wait(self, op: _Op) -> None:
        """Wait for the board to bring a register to op.value by itself; write it if it does not."""
        if self.auto_ack:
            self.control_readbacks[op.frame_id] = op.value   # simulated board clears the bit too
        if self.control_readbacks.get(op.frame_id, 0) == op.value:
            logger.info(f"[Transition] Confirmed {op.desc}: 0x{op.frame_id:04X} = 0x{op.value:02X}")
            self._op_idx += 1
            self._schedule_next(op.settle_ms, self._next_op)
            return
        self._polls += 1
        if self._polls * self.CONFIRM_POLL_MS < self.SELF_CLEAR_TIMEOUT_MS:
            self._schedule_next(self.CONFIRM_POLL_MS, lambda: self._poll_wait(op))
            return
        logger.warning(
            f"[Transition] 0x{op.frame_id:04X} did not return to 0x{op.value:02X} by itself "
            f"(readback 0x{self.control_readbacks.get(op.frame_id, 0):02X}); writing it"
        )
        self._ops[self._op_idx] = self._write(op.phase, op.frame_id, op.value, op.desc, settle_ms=op.settle_ms)
        self._next_op()

    def _issue_write(self, op: _Op) -> None:
        self._write_attempts += 1
        self._polls = 0
        if op.pulse:
            self._reset_saw_high = False
        self._issue_seq = self._echo_seq
        priority = self._idle_priority if self._mode == "safe_idle" else 1
        self._send(op.frame_id, op.value, priority)
        self._schedule_next(self.DEFAULT_CMD_WAIT_MS, lambda: self._confirm_write(op))

    def _write_confirmed(self, op: _Op) -> bool:
        if self.auto_ack:
            return True
        if self._echo_seq_by_frame.get(op.frame_id, -1) <= self._issue_seq:
            return False  # no echo of this register since the write: the cache may be stale
        mask = _RELAY_MASK if op.frame_id == FRAME_RELAY_CTRL else 0xFF
        rb = self.control_readbacks.get(op.frame_id, 0) & mask
        if op.pulse:
            # Bit 1 is the comparator reset in both 0x6002 and 0x6003; the value may also carry Enable
            return self._reset_saw_high or bool(rb & op.value & 0x02)
        if op.confirm:
            return op.confirm(rb)
        return rb == (op.value & mask)

    def _confirm_write(self, op: _Op) -> None:
        if self._write_confirmed(op):
            logger.info(
                f"[Transition] Confirmed {op.desc}: 0x{op.frame_id:04X} = 0x{op.value:02X}"
                + (f" (settling {op.settle_ms} ms)" if op.settle_ms else "")
            )
            if op.on_confirmed:
                op.on_confirmed()
            self._op_idx += 1
            self._schedule_next(op.settle_ms, self._next_op)
            return

        if self._polls < self.CONFIRM_POLLS:
            self._polls += 1
            self._schedule_next(self.CONFIRM_POLL_MS, lambda: self._confirm_write(op))
            return

        rb = self.control_readbacks.get(op.frame_id, 0)
        reg = _REGISTER_NAMES.get(op.frame_id, f"0x{op.frame_id:04X}")
        mismatch = f"{reg} 0x{op.frame_id:04X} expected 0x{op.value:02X}, readback 0x{rb:02X} ({op.desc})"

        if self._mode == "safe_idle" and not self._burst_sent:
            self._send_remaining_shutdown_burst(mismatch)

        if self._write_attempts <= self.MAX_RETRIES:
            warn_msg = f"Readback misaligned: {mismatch}. Resending (attempt {self._write_attempts}/{self.MAX_RETRIES})..."
            logger.warning(f"[Transition] {warn_msg}")
            if self._mode == "transition":
                self.transition_status.emit(warn_msg)
            self._issue_write(op)
            return

        if self._mode == "safe_idle":
            # Keep de-energizing; report what could not be confirmed at the end
            logger.critical(f"[Safe Idle] Unconfirmed after {self.MAX_RETRIES} resends: {mismatch}")
            self._unconfirmed.append(mismatch)
            self._op_idx += 1
            self._next_op()
            return

        msg = f"Setup misaligned after {self.MAX_RETRIES} resends: {mismatch}"
        logger.error(f"[Transition] {msg}")
        self._mode = "idle"
        self.current_phase = TransitionPhase.IDLE
        self.transition_failed.emit(msg)

    def _send_remaining_shutdown_burst(self, reason: str) -> None:
        """Board is not confirming a shutdown write: send every remaining shutdown write now.

        Keeps the de-energize order but stops a silent or lossy board from delaying the
        Cell Enable relay open by several seconds; confirmation continues afterwards.
        """
        self._burst_sent = True
        logger.critical(
            f"[Safe Idle] {reason} not confirmed; sending remaining de-energize writes immediately"
        )
        for op in self._ops[self._op_idx + 1:]:
            writes = op.expand() if op.kind == "expand" and op.expand else [op]
            for w in writes:
                if w.kind == "write" and w.in_burst:
                    self._send(w.frame_id, w.value, self._idle_priority)

    def _repeat_step_due_to_misalignment(self, reason: str) -> None:
        """A check failed after its writes were confirmed: restart the whole step setup."""
        if self._aborted:
            return
        self.retry_count += 1
        if self.retry_count > self.MAX_RETRIES:
            msg = f"Setup misaligned after {self.MAX_RETRIES} retries: {reason}"
            logger.error(f"[Transition] {msg}")
            self._mode = "idle"
            self.current_phase = TransitionPhase.IDLE
            self.transition_failed.emit(msg)
            return

        warn_msg = f"Readback misaligned ({reason}). Repeating step setup (attempt {self.retry_count}/{self.MAX_RETRIES})..."
        logger.warning(f"[Transition] {warn_msg}")
        self.transition_status.emit(warn_msg)
        self._cancel_pending()
        if self.active_step:
            self._run_ops(self._plan_step(self.active_step))

    def _on_sequence_done(self) -> None:
        mode = self._mode
        self._mode = "idle"
        self.current_phase = TransitionPhase.IDLE

        if mode == "safe_idle":
            if self._unconfirmed:
                self.safe_idle_unconfirmed.emit("; ".join(self._unconfirmed))
            else:
                logger.info("[Safe Idle] All control registers confirmed de-energized.")
            return

        if mode == "transition":
            step = self.active_step
            logger.info(f"[Transition] Safe transition complete for step '{step.name if step else ''}'")
            self.transition_status.emit("Hardware configuration and settling verified.")
            if step:
                self.transition_completed.emit(step)
