"""System tests: the complete cycler app against a simulated cell.

The real cycler MainWindow, SerialTransceiver thread, engine, step-transition
handshake, safety monitor and loggers run against ``SimulatedCell`` over a
pseudo-terminal. Safety tests assert on what the *board* ends up driving —
the register values it actually received — not on the app's own idea of it.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.core.cycler_engine import EngineState
from single_cell_cycler.core.profile_model import StepType
from single_cell_cycler.tests.system.conftest import posix_only, wait_until
from single_cell_cycler.tests.system.sim_cell import CHG_CTRL, RELAY

pytestmark = posix_only
COV = 1 << 0   # 0x3000 fault byte: Cell Over Voltage


def settle(seconds: float) -> None:
    """Keep the event loop running while queued commands reach the board."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def start_charging(cycler, cell) -> None:
    cycler._start_test()
    wait_until(lambda: cycler.engine.state == EngineState.RUNNING, 10, "recipe to start running")
    wait_until(lambda: cell.current > 0.5, 3, "charge current to flow")


def test_dashboard_shows_live_cell_and_preflight_passes(cycler, cell):
    assert cycler.dashboard.card_voltage.lbl_value.text() == "3.700"
    assert cycler.dashboard.card_temp.lbl_value.text() == "25.0"
    report = cycler.run_preflight_check()
    assert report.passed and not report.has_warnings, report.to_formatted_text()


def test_recipe_energizes_the_charger_through_the_handshake(cycler, cell):
    start_charging(cycler, cell)
    assert cell.registers[RELAY] & 0x01, "cell relay not closed"
    assert cell.registers[CHG_CTRL] & 0x01, "charge not enabled"
    v0 = cell.voltage
    settle(1.0)
    assert cell.voltage > v0, "cell voltage not rising while charging"
    assert cycler.engine.metrics_tracker.current_step_metrics is not None


def test_emergency_stop_while_charging_de_energizes_the_board(cycler, cell):
    start_charging(cycler, cell)
    cycler._emergency_stop()
    settle(1.5)
    assert cycler.engine.state == EngineState.SAFETY_STOP
    assert cell.energized() == []
    assert cell.current == 0.0


def test_bms_overvoltage_fault_ends_the_charge_immediately(cycler, cell):
    # During a running step any fault ends that step (engine._handle_step_fault);
    # COV is suppressed in discharge, so in practice it acts as a charge cut-off.
    start_charging(cycler, cell)
    cell.fault_byte = COV
    wait_until(lambda: not cell.registers[CHG_CTRL] & 0x01, 1.5, "charger to be disabled on COV")
    assert cell.current == 0.0
    assert cycler.engine.active_step.step_type != StepType.CHARGE


def test_overtemperature_cuts_the_current_immediately_and_keeps_it_off(cycler, cell):
    start_charging(cycler, cell)
    cell.temp_c = 80.0                     # SafetyLimits.max_temp_c is 60 °C
    wait_until(lambda: cell.current == 0.0, 1.5, "current to stop at 80 °C")
    end = time.monotonic() + 10
    while time.monotonic() < end:
        QApplication.processEvents()
        assert cell.current == 0.0, f"current flowing on an 80 °C cell: {cell.current} A"
        time.sleep(0.02)


@pytest.mark.xfail(strict=True, reason=(
    "Open finding: on any fault during a running step the engine advances to the next "
    "recipe step (_handle_step_fault) instead of stopping, so at 80 °C it re-closes the "
    "cell relay to set up the discharge step and only latches SAFETY_STOP ~13 s later. "
    "Needs a decision on which faults must end the test outright."))
def test_overtemperature_latches_a_safety_stop_with_the_cell_isolated(cycler, cell):
    start_charging(cycler, cell)
    cell.temp_c = 80.0
    relay_reclosed = False
    end = time.monotonic() + 3
    while time.monotonic() < end:
        QApplication.processEvents()
        relay_reclosed |= bool(cell.registers[RELAY] & 0x01) and cell.current == 0.0 \
            and cycler.engine.state != EngineState.RUNNING
        time.sleep(0.01)
    assert cycler.engine.state == EngineState.SAFETY_STOP
    assert not relay_reclosed, "cell relay re-closed after the over-temperature fault"


def test_disconnect_mid_test_leaves_the_board_safe(cycler, cell):
    start_charging(cycler, cell)
    cycler._toggle_connection()          # operator presses Disconnect
    settle(0.5)
    assert not cycler.transceiver.isRunning()
    assert cell.energized() == []


@pytest.mark.parametrize("stop_after_s", [0.3, 1.0, 2.0])
def test_emergency_stop_during_the_step_transition_leaves_the_board_safe(cycler, cell, stop_after_s):
    """E-STOP while the transition handshake still has commands queued.

    Safe-idle zeros are queued at priority 0 and overtake the handshake's
    priority-1 commands, which used to go out *after* them and re-close the
    relay / re-enable the charger once the stop had already been reported.
    """
    cycler._start_test()
    settle(stop_after_s)
    assert cycler.engine.state == EngineState.STEP_TRANSITION
    cycler._emergency_stop()
    settle(3.0)                            # longer than the remaining handshake
    assert cycler.engine.state == EngineState.SAFETY_STOP
    assert cell.energized() == [], f"board left {cell.energized()} after E-STOP"
