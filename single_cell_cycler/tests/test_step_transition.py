"""Unit tests for StepTransitionController hardware sequencing and readback verification."""

import pytest
from single_cell_cycler.comm.packet_codec import CommandEchoTelemetry
from single_cell_cycler.comm.protocol_defs import (
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
from single_cell_cycler.core.profile_model import StepType, TestStep
from single_cell_cycler.core.step_transition_controller import (
    StepTransitionController,
    TransitionPhase,
)


def test_charge_transition_sequence():
    """Verify charge step hardware sequence:
    1. Clear unwanted flags
    2. Cell select relay (100ms) -> Cell enable -> analog settling
    3. Charge voltage -> Charge current (100ms) -> Comparator reset (0->1->0) -> Charge enable 1 (Discharge enable 0)
    """
    commands_sent = []

    def mock_sender(frame_id, payload, priority):
        commands_sent.append((frame_id, payload))

    ctrl = StepTransitionController(
        command_sender=mock_sender,
        delays_enabled=False,
        auto_ack=True,
    )

    completed_steps = []
    ctrl.transition_completed.connect(lambda s: completed_steps.append(s))

    step = TestStep(
        step_index=1,
        name="CC Charge 1.5A to 4.2V",
        step_type=StepType.CHARGE,
        max_charge_voltage=True,       # 4.2V (bit 0 = 1)
        charge_current_1=True,         # +0.5A (bit 1 = 1)
        charge_current_2=True,         # +1.0A (bit 2 = 1) -> Total 1.5A
    )

    ctrl.start_transition(step=step, selected_cell=1)

    assert len(completed_steps) == 1
    assert completed_steps[0].name == "CC Charge 1.5A to 4.2V"

    # Verify command sequence sent:
    # 1. Clear opposing power paths: Discharge Ctrl=0, Discharge Sel=0, Charge Ctrl=0
    assert (FRAME_DISCHARGE_CTRL, 0x00) in commands_sent
    assert (FRAME_DISCHARGE_SEL, 0x00) in commands_sent

    # 2. Cell Select relay for Cell 1 (bit 1=0, bit 0=0)
    assert (FRAME_RELAY_CTRL, 0x00) in commands_sent

    # 3. Cell Enable relay (bit 0=1)
    assert (FRAME_RELAY_CTRL, int(RelayControlBits.CELL_ENABLE)) in commands_sent

    # 4. Charge Voltage first (bit 0 = 1, current bits = 0)
    assert (FRAME_CHARGE_SEL, int(ChargeSelectBits.MAX_CHARGE_VOLTAGE)) in commands_sent

    # 5. Charge Current (Voltage + Current 1 + Current 2 = 0x07)
    expected_chg_sel = (
        ChargeSelectBits.MAX_CHARGE_VOLTAGE
        | ChargeSelectBits.MAX_CHARGE_CURRENT_1
        | ChargeSelectBits.MAX_CHARGE_CURRENT_2
    )
    assert (FRAME_CHARGE_SEL, int(expected_chg_sel)) in commands_sent

    # 6. Comparator reset pulse high (0x02) then low (0x00)
    assert (FRAME_CHARGE_CTRL, int(ChargeControlBits.CHARGE_COMPARATOR_RESET)) in commands_sent
    assert (FRAME_CHARGE_CTRL, 0x00) in commands_sent

    # 7. Make Charge Enable 1 (0x01) and ensure Discharge Enable is 0
    assert (FRAME_CHARGE_CTRL, int(ChargeControlBits.CHARGE_ENABLE)) in commands_sent
    assert (FRAME_DISCHARGE_CTRL, 0x00) in commands_sent


def test_discharge_transition_sequence():
    """Verify discharge step hardware sequence:
    1. Ensure charge enable is 0
    2. Cell select -> Cell enable
    3. Comparator reset -> Discharge enable 1
    4. Once discharge enable is 1 and reset is 0, apply load changes
    """
    commands_sent = []

    def mock_sender(frame_id, payload, priority):
        commands_sent.append((frame_id, payload))

    ctrl = StepTransitionController(
        command_sender=mock_sender,
        delays_enabled=False,
        auto_ack=True,
    )

    completed_steps = []
    ctrl.transition_completed.connect(lambda s: completed_steps.append(s))

    step = TestStep(
        step_index=2,
        name="Discharge 1.0A",
        step_type=StepType.DISCHARGE,
        discharge_load_1=True,   # 0.2A
        discharge_load_3=True,   # 0.8A -> Total 1.0A (decimal 5)
    )

    ctrl.start_transition(step=step, selected_cell=2)

    assert len(completed_steps) == 1
    assert completed_steps[0].name == "Discharge 1.0A"

    # 1. Charge enable is zero
    assert (FRAME_CHARGE_CTRL, 0x00) in commands_sent

    # 2. Cell 2 select (bit 1=1, bit 0=0)
    assert (FRAME_RELAY_CTRL, int(RelayControlBits.CELL_SELECT)) in commands_sent

    # 3. Cell 2 enable (bit 1=1, bit 0=1 -> 0x03)
    assert (FRAME_RELAY_CTRL, int(RelayControlBits.CELL_SELECT | RelayControlBits.CELL_ENABLE)) in commands_sent

    # 4. Discharge comparator reset pulse (0x02 then 0x00)
    assert (FRAME_DISCHARGE_CTRL, int(DischargeControlBits.DISCHARGE_COMPARATOR_RESET)) in commands_sent
    assert (FRAME_DISCHARGE_CTRL, 0x00) in commands_sent

    # 5. Turn on Discharge enable (0x01)
    assert (FRAME_DISCHARGE_CTRL, int(DischargeControlBits.DISCHARGE_ENABLE)) in commands_sent

    # 6. Apply load changes (decimal 5: L1 + L3 = 1.0A)
    assert (FRAME_DISCHARGE_SEL, 5) in commands_sent


def test_misalignment_retry_mechanism():
    """Verify that when a hardware readback does not match, the controller retries setup."""
    commands_sent = []

    def mock_sender(frame_id, payload, priority):
        commands_sent.append((frame_id, payload))

    ctrl = StepTransitionController(
        command_sender=mock_sender,
        delays_enabled=False,
        auto_ack=False,
    )

    status_messages = []
    ctrl.transition_status.connect(lambda msg: status_messages.append(msg))

    step = TestStep(
        step_index=1,
        name="Charge Test",
        step_type=StepType.CHARGE,
        max_charge_voltage=True,
    )

    # Inject an initial dirty state (Discharge Enable is ON)
    ctrl.control_readbacks[FRAME_DISCHARGE_CTRL] = int(DischargeControlBits.DISCHARGE_ENABLE)

    # Start transition - it will attempt to clear unwanted flags
    ctrl.start_transition(step=step, selected_cell=1)

    # Because auto_ack is False and readback still shows Discharge Enable ON,
    # it detects misalignment and retries
    assert ctrl.retry_count >= 1
    assert any("misaligned" in m for m in status_messages)
