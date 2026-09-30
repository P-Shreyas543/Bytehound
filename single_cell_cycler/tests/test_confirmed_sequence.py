"""Readback-confirmed relay and power sequencing (Cell Select -> Cell Enable -> drives).

A FakeBoard echoes every write back into the controller like the MCU's 0x6000-0x6004
readback frames, and can be told to ignore or override specific writes.
"""

import os

import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.comm.packet_codec import CellDataTelemetry, CommandEchoTelemetry
from single_cell_cycler.comm.protocol_defs import (
    FRAME_CHARGE_CTRL,
    FRAME_CHARGE_SEL,
    FRAME_DISCHARGE_CTRL,
    FRAME_DISCHARGE_SEL,
    FRAME_RELAY_CTRL,
)
from single_cell_cycler.core.cycler_engine import CyclerEngine, EngineState
from single_cell_cycler.core.profile_model import StepType, TestStep
from single_cell_cycler.core.step_transition_controller import StepTransitionController


class FakeBoard:
    """Register model that echoes each write, with optional per-write faults."""

    def __init__(self, relay=0x00):
        self.regs = {
            FRAME_RELAY_CTRL: relay,
            FRAME_CHARGE_SEL: 0x00,
            FRAME_CHARGE_CTRL: 0x00,
            FRAME_DISCHARGE_CTRL: 0x00,
            FRAME_DISCHARGE_SEL: 0x00,
        }
        self.writes = []
        self.ignore = {}      # (frame_id, value) -> number of writes to drop
        self.after = {}       # (frame_id, value) -> callable(board) run once after the write lands
        self.ctrl = None

    def sender(self, frame_id, value, priority):
        self.writes.append((frame_id, value))
        key = (frame_id, value)
        if self.ignore.get(key, 0) > 0:
            self.ignore[key] -= 1
            self.echo_all()
            return
        self.regs[frame_id] = value
        hook = self.after.pop(key, None)
        if hook:
            hook(self)
        self.echo_all()

    def echo_all(self):
        for fid, val in self.regs.items():
            self.ctrl.on_command_echo(CommandEchoTelemetry(frame_id=fid, payload_byte=val))


def make_ctrl(board):
    ctrl = StepTransitionController(command_sender=board.sender, delays_enabled=False, auto_ack=False)
    board.ctrl = ctrl
    board.echo_all()
    return ctrl


def charge_step():
    return TestStep(
        step_index=1,
        name="CC Charge",
        step_type=StepType.CHARGE,
        max_charge_voltage=True,
        charge_current_1=True,
        charge_current_2=True,
    )


def test_cell2_charge_follows_confirmed_sequence_exactly():
    board = FakeBoard(relay=0x02)  # Cell 2 selected before the test, Enable open
    ctrl = make_ctrl(board)
    done = []
    ctrl.transition_completed.connect(done.append)

    ctrl.start_transition(step=charge_step(), selected_cell=2)

    assert len(done) == 1
    assert board.writes == [
        (FRAME_CHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_SEL, 0x00),
        (FRAME_RELAY_CTRL, 0x03),       # Select already Cell 2 -> only Cell Enable closes
        (FRAME_CHARGE_SEL, 0x01),       # 4.2 V
        (FRAME_CHARGE_SEL, 0x07),       # 4.2 V + 1.5 A
        (FRAME_CHARGE_CTRL, 0x02),      # comparator reset set
        (FRAME_CHARGE_CTRL, 0x00),      # comparator reset cleared
        (FRAME_CHARGE_CTRL, 0x01),      # charge enable
    ]
    assert board.regs[FRAME_RELAY_CTRL] == 0x03
    assert ctrl.relay_owned_by_test is True


def test_cell_select_set_before_cell_enable_closes():
    board = FakeBoard(relay=0x00)  # Select still on Cell 1
    ctrl = make_ctrl(board)
    ctrl.start_transition(step=charge_step(), selected_cell=2)

    relay_writes = [v for f, v in board.writes if f == FRAME_RELAY_CTRL]
    assert relay_writes == [0x02, 0x03]


def test_cell_select_never_moves_while_cell_enable_closed():
    board = FakeBoard(relay=0x01)  # Cell 1 connected (Enable closed)
    ctrl = make_ctrl(board)
    ctrl.start_transition(step=charge_step(), selected_cell=2)

    relay_writes = [v for f, v in board.writes if f == FRAME_RELAY_CTRL]
    # Open Enable on Cell 1, move Select to Cell 2, then close Enable
    assert relay_writes == [0x00, 0x02, 0x03]


def test_each_write_waits_for_its_readback_and_is_resent_on_mismatch():
    board = FakeBoard(relay=0x02)
    board.ignore[(FRAME_CHARGE_SEL, 0x07)] = 2  # MCU drops the current-select write twice
    ctrl = make_ctrl(board)
    done = []
    ctrl.transition_completed.connect(done.append)

    ctrl.start_transition(step=charge_step(), selected_cell=2)

    assert len(done) == 1
    assert board.writes.count((FRAME_CHARGE_SEL, 0x07)) == 3
    # Comparator reset is not touched until 0x6001 is confirmed
    first_reset = board.writes.index((FRAME_CHARGE_CTRL, 0x02))
    last_sel = len(board.writes) - 1 - board.writes[::-1].index((FRAME_CHARGE_SEL, 0x07))
    assert first_reset > last_sel


def test_comparator_reset_confirmed_when_mcu_self_clears():
    board = FakeBoard(relay=0x02)
    # The MCU clears the reset bit on its own right after it is set (seen on COM15 hardware)
    board.after[(FRAME_CHARGE_CTRL, 0x02)] = lambda b: (
        b.ctrl.on_command_echo(CommandEchoTelemetry(frame_id=FRAME_CHARGE_CTRL, payload_byte=0x02)),
        b.regs.__setitem__(FRAME_CHARGE_CTRL, 0x00),
    )
    ctrl = make_ctrl(board)
    done = []
    ctrl.transition_completed.connect(done.append)

    ctrl.start_transition(step=charge_step(), selected_cell=2)

    assert len(done) == 1
    assert board.writes.count((FRAME_CHARGE_CTRL, 0x02)) == 1


def test_relay_opened_mid_setup_restarts_setup_instead_of_running_open():
    """Regression for the COM15 Cell 2 failure: relay opened after it was confirmed closed."""
    board = FakeBoard(relay=0x02)
    board.after[(FRAME_CHARGE_SEL, 0x07)] = lambda b: b.regs.__setitem__(FRAME_RELAY_CTRL, 0x02)
    ctrl = make_ctrl(board)
    done = []
    ctrl.transition_completed.connect(done.append)

    ctrl.start_transition(step=charge_step(), selected_cell=2)

    assert len(done) == 1
    assert ctrl.retry_count == 1
    # Charge enable was only ever sent with the relay closed, and the relay ends closed
    relay_writes = [v for f, v in board.writes if f == FRAME_RELAY_CTRL]
    assert relay_writes == [0x03, 0x03]
    assert board.regs[FRAME_RELAY_CTRL] == 0x03
    assert board.regs[FRAME_CHARGE_CTRL] == 0x01


def test_relay_that_never_stays_closed_fails_transition():
    board = FakeBoard(relay=0x02)
    ctrl = make_ctrl(board)
    orig = board.sender

    def sender(fid, val, prio):
        orig(fid, val, prio)
        if (fid, val) == (FRAME_CHARGE_CTRL, 0x00) and board.regs[FRAME_RELAY_CTRL] == 0x03:
            board.regs[FRAME_RELAY_CTRL] = 0x02
            board.echo_all()

    ctrl._command_sender = sender
    failures = []
    ctrl.transition_failed.connect(failures.append)

    ctrl.start_transition(step=charge_step(), selected_cell=2)

    assert len(failures) == 1
    assert (FRAME_CHARGE_CTRL, 0x01) not in board.writes


def test_second_active_step_keeps_relay_closed_by_the_test():
    board = FakeBoard(relay=0x02)
    ctrl = make_ctrl(board)
    ctrl.start_transition(step=charge_step(), selected_cell=2)
    board.writes.clear()

    dis = TestStep(step_index=2, name="Discharge", step_type=StepType.DISCHARGE,
                   discharge_load_1=True, discharge_load_3=True)
    done = []
    ctrl.transition_completed.connect(done.append)
    ctrl.start_transition(step=dis, selected_cell=2)

    assert len(done) == 1
    assert all(f != FRAME_RELAY_CTRL for f, _ in board.writes)
    assert board.writes[-3:] == [
        (FRAME_DISCHARGE_CTRL, 0x02),
        (FRAME_DISCHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_CTRL, 0x01),
    ] or board.writes[-4:-1] == [
        (FRAME_DISCHARGE_CTRL, 0x02),
        (FRAME_DISCHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_CTRL, 0x01),
    ]
    assert board.writes[-1] == (FRAME_DISCHARGE_SEL, 5)


def test_rest_turns_drives_off_before_opening_cell_enable():
    board = FakeBoard(relay=0x03)
    board.regs[FRAME_CHARGE_CTRL] = 0x01
    ctrl = make_ctrl(board)
    ctrl.start_transition(step=TestStep(step_index=3, name="Rest", step_type=StepType.REST), selected_cell=2)

    assert board.writes == [
        (FRAME_CHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_SEL, 0x00),
        (FRAME_RELAY_CTRL, 0x02),
    ]
    assert ctrl.relay_owned_by_test is False


def test_safe_idle_order_and_unconfirmed_report():
    board = FakeBoard(relay=0x03)
    board.regs.update({FRAME_CHARGE_SEL: 0x07, FRAME_CHARGE_CTRL: 0x01, FRAME_DISCHARGE_SEL: 0x05})
    board.ignore[(FRAME_DISCHARGE_SEL, 0x00)] = 99  # load bank readback never confirms
    ctrl = make_ctrl(board)
    unconfirmed = []
    ctrl.safe_idle_unconfirmed.connect(unconfirmed.append)

    ctrl.safe_idle(selected_cell=2)

    assert board.writes[:5] == [
        (FRAME_CHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_CTRL, 0x00),
        (FRAME_CHARGE_SEL, 0x00),
        (FRAME_DISCHARGE_SEL, 0x00),
        # 0x6004 not confirmed -> the remaining write (Enable open) is sent at once, not after retries
        (FRAME_RELAY_CTRL, 0x02),
    ]
    # ...the burst never moves Select; the confirmed sequence sees Enable open, then writes 0
    assert [v for f, v in board.writes if f == FRAME_RELAY_CTRL] == [0x02, 0x00]
    assert board.writes[-1] == (FRAME_RELAY_CTRL, 0x00)
    assert board.regs[FRAME_RELAY_CTRL] == 0x00
    assert len(unconfirmed) == 1 and "0x6004" in unconfirmed[0]


def test_safe_idle_from_cell2_connected_opens_enable_before_select_moves():
    """STOP with Cell 2 connected ends at 0x6000 = 0 via 3 -> 2 -> 0, never 3 -> 0 in one write."""
    for chosen in (1, 2):  # also when the cell combo was changed mid-test
        board = FakeBoard(relay=0x03)
        ctrl = make_ctrl(board)

        ctrl.safe_idle(selected_cell=chosen)

        relay_writes = [v for f, v in board.writes if f == FRAME_RELAY_CTRL]
        assert relay_writes == [0x02, 0x00]
        assert board.regs == {fid: 0 for fid in board.regs}


def test_safe_idle_from_cell1_connected_goes_straight_to_zero():
    board = FakeBoard(relay=0x01)
    ctrl = make_ctrl(board)
    ctrl.safe_idle(selected_cell=1)
    assert [v for f, v in board.writes if f == FRAME_RELAY_CTRL] == [0x00]


def test_cell_select_while_shutdown_running_is_queued_not_cut_short():
    board = FakeBoard(relay=0x03)
    ctrl = StepTransitionController(command_sender=board.sender, delays_enabled=True, auto_ack=False)
    board.ctrl = ctrl
    board.echo_all()

    ctrl.safe_idle(selected_cell=2)     # first write sent, rest waits on timers
    ctrl.select_cell_idle(1)
    assert ctrl._mode == "safe_idle"
    assert ctrl._ops[-1].kind == "expand"
    assert ctrl._ops[0].frame_id == FRAME_CHARGE_CTRL


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


def test_preflight_check_never_writes_the_relay(qapp):
    """Regression: pre-flight used to close/open the Cell 2 relay and race the step transition."""
    from single_cell_cycler.ui.main_window import MainWindow

    win = MainWindow()
    sent = []
    win._on_command_dispatch = lambda fid, val, prio=1: sent.append((fid, val))
    win.transceiver.isRunning = lambda: True
    win.combo_active_cell.blockSignals(True)
    win.combo_active_cell.setCurrentIndex(1)  # Cell 2
    win.combo_active_cell.blockSignals(False)
    win.engine.transition_controller.control_readbacks[FRAME_RELAY_CTRL] = 0x02
    win._last_cell_data = CellDataTelemetry(voltage=4.064, current=-0.006, terminal_temp=26.9, body_temp=26.3)

    win.run_preflight_check()

    assert sent == []
    win.close()


def test_engine_stop_runs_confirmed_safe_idle_to_all_zero():
    board = FakeBoard(relay=0x02)
    engine = CyclerEngine(command_sender=board.sender)
    engine.transition_controller.auto_ack = False
    engine.transition_controller.delays_enabled = False
    board.ctrl = engine.transition_controller
    board.echo_all()
    engine.selected_cell = 2

    from single_cell_cycler.core.profile_model import TestRecipe
    engine.load_recipe(TestRecipe(recipe_name="r", steps=[charge_step()]))
    engine.start_test()
    assert engine.state == EngineState.RUNNING
    assert board.regs[FRAME_RELAY_CTRL] == 0x03

    board.writes.clear()
    engine.stop_test()
    assert board.writes == [
        (FRAME_CHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_CTRL, 0x00),
        (FRAME_CHARGE_SEL, 0x00),
        (FRAME_DISCHARGE_SEL, 0x00),
        (FRAME_RELAY_CTRL, 0x02),
        (FRAME_RELAY_CTRL, 0x00),
    ]
    assert board.regs == {fid: 0 for fid in board.regs}
    assert engine.transition_controller.relay_owned_by_test is False


def test_stale_cached_readback_does_not_confirm_without_a_new_echo():
    """Cache already shows the target but the board never echoes after the write: not confirmed."""
    board = FakeBoard(relay=0x02)
    ctrl = make_ctrl(board)
    board.sender = lambda fid, val, prio: board.writes.append((fid, val))  # silent board
    ctrl._command_sender = board.sender
    failures = []
    ctrl.transition_failed.connect(failures.append)

    ctrl.start_transition(step=charge_step(), selected_cell=2)

    # 0x6002 already reads 0x00 in the cache, yet it is resent because no fresh echo arrived
    assert board.writes.count((FRAME_CHARGE_CTRL, 0x00)) == 1 + ctrl.MAX_RETRIES
    assert len(failures) == 1


def test_silent_board_during_shutdown_sends_remaining_writes_immediately():
    board = FakeBoard(relay=0x03)
    board.regs.update({FRAME_CHARGE_CTRL: 0x01, FRAME_CHARGE_SEL: 0x07})
    ctrl = make_ctrl(board)
    board.sender = lambda fid, val, prio: board.writes.append((fid, val))  # board stops echoing
    ctrl._command_sender = board.sender

    ctrl.safe_idle(selected_cell=2)

    # First unconfirmed write triggers the burst of every later shutdown write, in order,
    # before any resend of the first write
    assert board.writes[:5] == [
        (FRAME_CHARGE_CTRL, 0x00),
        (FRAME_DISCHARGE_CTRL, 0x00),
        (FRAME_CHARGE_SEL, 0x00),
        (FRAME_DISCHARGE_SEL, 0x00),
        (FRAME_RELAY_CTRL, 0x02),  # Enable open, Cell 2 Select kept from readback
    ]


def test_emergency_stop_when_already_stopped_still_sends_immediate_zeros():
    sent = []
    engine = CyclerEngine(command_sender=lambda f, v, p: sent.append((f, v, p)))
    engine.selected_cell = 2
    engine.emergency_stop()
    sent.clear()

    engine.emergency_stop()  # second press while in SAFETY_STOP

    assert engine.state == EngineState.SAFETY_STOP
    assert (FRAME_CHARGE_CTRL, 0x00, 0) in sent[:5]
    assert (FRAME_RELAY_CTRL, 0x02, 0) in sent[:5]


def test_safety_burst_keeps_readback_select_when_enable_closed():
    """Cell combo moved to Cell 1 mid-test while Cell 2 is connected: trip must write 0x02, not 0x00."""
    sent = []
    engine = CyclerEngine(command_sender=lambda f, v, p: sent.append((f, v)))
    engine.transition_controller.control_readbacks[FRAME_RELAY_CTRL] = 0x03
    engine.selected_cell = 1

    engine.safety_monitor.emergency_stop()

    assert (FRAME_RELAY_CTRL, 0x02) in sent
    assert (FRAME_RELAY_CTRL, 0x00) not in sent


def test_out_of_range_reading_after_stop_sends_no_hardware_writes():
    """After STOP (0x6000 = 0, Cell 1 selected, ~0 V) the monitor must not write 0x6000 = 2 back."""
    sent = []
    engine = CyclerEngine(command_sender=lambda f, v, p: sent.append((f, v)))
    engine.selected_cell = 2
    engine.stop_test()
    sent.clear()

    engine.on_cell_telemetry(CellDataTelemetry(voltage=0.001, current=0.0, terminal_temp=27.0, body_temp=27.0))

    assert sent == []
    assert engine.state == EngineState.ABORTED


def test_pause_is_not_turned_into_safety_stop_by_zeroed_hardware_reading():
    sent = []
    engine = CyclerEngine(command_sender=lambda f, v, p: sent.append((f, v)))
    engine.selected_cell = 2
    from single_cell_cycler.core.profile_model import TestRecipe
    engine.load_recipe(TestRecipe(recipe_name="r", steps=[charge_step()]))
    engine.on_cell_telemetry(CellDataTelemetry(voltage=4.09, current=0.0, terminal_temp=27.0, body_temp=27.0))
    engine.start_test()
    engine.pause_test()
    sent.clear()

    engine.on_cell_telemetry(CellDataTelemetry(voltage=0.001, current=0.0, terminal_temp=27.0, body_temp=27.0))

    assert engine.state == EngineState.PAUSED
    assert sent == []


def test_manual_estop_always_writes_even_when_idle():
    sent = []
    engine = CyclerEngine(command_sender=lambda f, v, p: sent.append((f, v)))
    engine.emergency_stop()
    assert (FRAME_CHARGE_CTRL, 0x00) in sent and (FRAME_DISCHARGE_CTRL, 0x00) in sent


# --- Cell lock, Pause and fault policy -------------------------------------------------

def _running_engine(board, steps):
    from single_cell_cycler.core.profile_model import TestRecipe
    engine = CyclerEngine(command_sender=board.sender)
    engine.transition_controller.auto_ack = False
    engine.transition_controller.delays_enabled = False
    board.ctrl = engine.transition_controller
    board.echo_all()
    engine.selected_cell = 2
    engine.load_recipe(TestRecipe(recipe_name="r", steps=steps))
    engine.on_cell_telemetry(CellDataTelemetry(voltage=4.09, current=0.0, terminal_temp=27.0, body_temp=27.0))
    engine.start_test()
    assert engine.state == EngineState.RUNNING
    return engine


def test_cell_is_locked_for_the_whole_test_including_pause():
    board = FakeBoard(relay=0x02)
    engine = _running_engine(board, [charge_step()])

    engine.selected_cell = 1                  # e.g. dropdown change mid-test
    assert engine.selected_cell == 2
    engine.pause_test()
    engine.selected_cell = 1                  # change while paused
    assert engine.selected_cell == 2
    engine.stop_test()
    engine.selected_cell = 1                  # allowed once the test is over
    assert engine.selected_cell == 1


def test_pause_only_opens_cell_enable_and_resume_keeps_cell():
    board = FakeBoard(relay=0x02)
    engine = _running_engine(board, [charge_step()])
    board.writes.clear()

    engine.pause_test()
    assert [v for f, v in board.writes if f == FRAME_RELAY_CTRL] == [0x02]   # Select stays Cell 2
    assert board.regs[FRAME_RELAY_CTRL] == 0x02
    assert board.regs[FRAME_CHARGE_CTRL] == 0x00

    board.writes.clear()
    engine.resume_test()
    assert engine.state == EngineState.RUNNING
    relay = [v for f, v in board.writes if f == FRAME_RELAY_CTRL]
    assert relay == [0x03]                     # only Cell Enable closes again
    assert 0x00 not in relay and 0x01 not in relay


def _fault(**flags):
    from single_cell_cycler.comm.packet_codec import FaultSoCTelemetry
    from single_cell_cycler.comm.protocol_defs import BMSFaultFlags
    byte = 0
    for name, on in flags.items():
        if on:
            byte |= int(getattr(BMSFaultFlags, name.upper()))
    base = dict(cov=False, cuv=False, occ=False, ocd=False, cot=False, cut=False)
    base.update(flags)
    return FaultSoCTelemetry(fault_byte=byte, soc_ocv=50.0, soc_cc=50.0, **base)


@pytest.mark.parametrize("flag", ["cot", "cut", "occ", "ocd"])
def test_thermal_and_current_bms_faults_safety_stop(flag):
    board = FakeBoard(relay=0x02)
    steps = [charge_step(), TestStep(step_index=2, name="Rest", step_type=StepType.REST)]
    if flag == "ocd":
        steps[0] = TestStep(step_index=1, name="Dis", step_type=StepType.DISCHARGE, discharge_load_1=True)
    engine = _running_engine(board, steps)
    tripped = []
    engine.safety_tripped.connect(tripped.append)

    engine.on_fault_soc_telemetry(_fault(**{flag: True}))

    assert engine.state == EngineState.SAFETY_STOP
    assert len(tripped) == 1
    assert board.regs == {fid: 0 for fid in board.regs}


def test_voltage_fault_ends_step_and_continues_with_warning():
    board = FakeBoard(relay=0x02)
    rest = TestStep(step_index=2, name="Rest", step_type=StepType.REST)
    engine = _running_engine(board, [charge_step(), rest])
    step_faults, tripped = [], []
    engine.step_fault.connect(step_faults.append)
    engine.safety_tripped.connect(tripped.append)

    engine.on_fault_soc_telemetry(_fault(cov=True))   # COV while charging

    assert engine.state == EngineState.RUNNING
    assert engine.active_step.name == "Rest"
    assert len(step_faults) == 1 and tripped == []
    assert "FAULT:" in engine.metrics_tracker.step_history[0].cutoff_reason


def test_voltage_fault_on_last_step_completes_test():
    board = FakeBoard(relay=0x02)
    engine = _running_engine(board, [charge_step()])
    engine.on_fault_soc_telemetry(_fault(cov=True))
    assert engine.state == EngineState.COMPLETED


def test_software_overtemperature_limit_safety_stops():
    board = FakeBoard(relay=0x02)
    engine = _running_engine(board, [charge_step(), TestStep(step_index=2, name="Rest", step_type=StepType.REST)])
    engine.on_cell_telemetry(CellDataTelemetry(voltage=4.1, current=1.2, terminal_temp=75.0, body_temp=74.0))
    assert engine.state == EngineState.SAFETY_STOP


def test_stop_while_running_records_stopped_by_operator():
    board = FakeBoard(relay=0x02)
    engine = _running_engine(board, [charge_step()])
    completed = []
    engine.step_completed.connect(completed.append)

    engine.stop_test()

    assert engine.state == EngineState.ABORTED
    assert len(engine.metrics_tracker.step_history) == 1
    assert engine.metrics_tracker.step_history[-1].cutoff_reason == "Stopped by operator"
    assert len(completed) == 1


def test_estop_while_running_records_emergency_stop():
    board = FakeBoard(relay=0x02)
    engine = _running_engine(board, [charge_step()])
    completed = []
    engine.step_completed.connect(completed.append)

    engine.emergency_stop()

    assert engine.state == EngineState.SAFETY_STOP
    assert len(engine.metrics_tracker.step_history) == 1
    assert engine.metrics_tracker.step_history[-1].cutoff_reason == "EMERGENCY STOP"
    assert len(completed) == 1


def test_stop_while_idle_records_nothing():
    board = FakeBoard(relay=0x02)
    engine = CyclerEngine(command_sender=board.sender)
    engine.transition_controller.auto_ack = False
    engine.transition_controller.delays_enabled = False
    board.ctrl = engine.transition_controller
    completed = []
    engine.step_completed.connect(completed.append)

    engine.stop_test()

    assert len(engine.metrics_tracker.step_history) == 0
    assert len(completed) == 0


def test_voltage_fault_then_stop_does_not_duplicate_step():
    board = FakeBoard(relay=0x02)
    engine = _running_engine(board, [charge_step()])
    completed = []
    engine.step_completed.connect(completed.append)

    # Voltage fault triggers step completion (and since it's the last step, completes the test)
    engine.on_fault_soc_telemetry(_fault(cov=True))
    assert len(engine.metrics_tracker.step_history) == 1
    assert "FAULT:" in engine.metrics_tracker.step_history[0].cutoff_reason
    assert len(completed) == 1

    # Now call stop_test()
    engine.stop_test()
    assert len(engine.metrics_tracker.step_history) == 1
    assert len(completed) == 1


# --- Plot buffers -------------------------------------------------------------------------

def test_series_buffer_is_a_bounded_contiguous_window():
    from single_cell_cycler.ui.widgets.live_plots import _SeriesBuffer
    buf = _SeriesBuffer(5)
    for k in range(23):
        buf.append(k)
        expect = list(range(max(0, k - 4), k + 1))
        assert list(buf.view()) == expect and len(buf) == len(expect)
    buf.extend(range(100, 108))
    assert list(buf.view()) == [103, 104, 105, 106, 107]
    assert buf[-1] == 107
    buf.clear()
    assert not buf


def test_plot_range_slice_is_bounded_and_keeps_extremes(qapp):
    import numpy as np
    from single_cell_cycler.ui.widgets import live_plots as lp_mod
    w = lp_mod.LivePlotWidget(max_buffer_points=400_000)
    n = 300_000
    for k in range(n):
        v = 5.5 if k == 123_457 else 3.7   # one spike must survive decimation
        w._push_sample(k * 0.1, v, 1.0, 27.0, 26.0)

    t, (v, i, _, _) = w._series_for_range(0.0, n * 0.1)
    assert len(t) <= lp_mod._MAX_DRAW_POINTS + 1024
    assert np.nanmax(v) == 5.5
    assert t[-1] == (n - 1) * 0.1               # newest sample always drawn

    t2, (v2, _, _, _) = w._series_for_range(1000.0, 1100.0)   # zoomed in: raw samples
    assert np.all(np.diff(t2) > 0) and len(t2) >= 1000
