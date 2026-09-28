"""Unit tests for the 16-state discharge load bank and charge select register mapping."""

import pytest
from single_cell_cycler.comm.protocol_defs import (
    DISCHARGE_TABLE,
    ChargeSelectBits,
    RelayControlBits,
    charge_specs_to_select_byte,
    discharge_current_to_decimal,
    discharge_decimal_to_current,
    select_byte_to_charge_specs,
)
from single_cell_cycler.core.profile_model import StepType, TestStep


# Exact user specification table for 0x6004
SPEC_DISCHARGE_ROWS = [
    # (Decimal, L1, L2, L3, L4, NumON, Current)
    (0, False, False, False, False, 0, 0.0),
    (1, True, False, False, False, 1, 0.2),
    (2, False, True, False, False, 1, 0.4),
    (3, True, True, False, False, 2, 0.6),
    (4, False, False, True, False, 1, 0.8),
    (5, True, False, True, False, 2, 1.0),
    (6, False, True, True, False, 2, 1.2),
    (7, True, True, True, False, 3, 1.4),
    (8, False, False, False, True, 1, 1.6),
    (9, True, False, False, True, 2, 1.8),
    (10, False, True, False, True, 2, 2.0),
    (11, True, True, False, True, 3, 2.2),
    (12, False, False, True, True, 2, 2.4),
    (13, True, False, True, True, 3, 2.6),
    (14, False, True, True, True, 3, 2.8),
    (15, True, True, True, True, 4, 3.0),
]


def test_discharge_load_table_all_16_states():
    """Verify all 16 discrete load states match the hardware specification table."""
    for dec, l1, l2, l3, l4, num_on, current in SPEC_DISCHARGE_ROWS:
        table_row = DISCHARGE_TABLE[dec]
        assert table_row[0] == l1, f"Dec {dec}: L1 mismatch"
        assert table_row[1] == l2, f"Dec {dec}: L2 mismatch"
        assert table_row[2] == l3, f"Dec {dec}: L3 mismatch"
        assert table_row[3] == l4, f"Dec {dec}: L4 mismatch"
        assert table_row[4] == num_on, f"Dec {dec}: num switches mismatch"
        assert table_row[5] == pytest.approx(current, abs=1e-3), f"Dec {dec}: current mismatch"

        # Check conversion functions
        assert discharge_decimal_to_current(dec) == pytest.approx(current, abs=1e-3)
        assert discharge_current_to_decimal(current) == dec


def test_teststep_discharge_setpoints():
    """Verify TestStep helper properties calculate decimal and current correctly."""
    step = TestStep(step_index=1, name="Discharge Test", step_type=StepType.DISCHARGE)

    # State 6: L2 + L3 ON -> 1.2 A
    step.set_discharge_current(1.2)
    assert step.discharge_load_1 is False
    assert step.discharge_load_2 is True
    assert step.discharge_load_3 is True
    assert step.discharge_load_4 is False
    assert step.discharge_load_decimal == 6
    assert step.discharge_current_target == 1.2

    # State 15: All ON -> 3.0 A
    step.set_discharge_current(3.0)
    assert step.discharge_load_decimal == 15
    assert step.discharge_current_target == 3.0

    # State 0: All OFF -> 0.0 A
    step.set_discharge_current(0.0)
    assert step.discharge_load_decimal == 0
    assert step.discharge_current_target == 0.0


def test_charge_select_encoding():
    """Verify 0x6001 Charge Select bitfield encoding and decoding."""
    # 3.6V, 0.0A -> 0x00
    assert charge_specs_to_select_byte(3.6, 0.0) == 0x00
    assert select_byte_to_charge_specs(0x00) == (3.6, 0.0)

    # 3.6V, 0.5A (Bit 1) -> 0x02
    assert charge_specs_to_select_byte(3.6, 0.5) == ChargeSelectBits.MAX_CHARGE_CURRENT_1
    assert select_byte_to_charge_specs(0x02) == (3.6, 0.5)

    # 4.2V, 0.5A (Bit 0 + Bit 1) -> 0x03
    val = charge_specs_to_select_byte(4.2, 0.5)
    assert val == (ChargeSelectBits.MAX_CHARGE_VOLTAGE | ChargeSelectBits.MAX_CHARGE_CURRENT_1)
    assert select_byte_to_charge_specs(0x03) == (4.2, 0.5)

    # 4.2V, 1.0A (Bit 0 + Bit 2) -> 0x05
    val = charge_specs_to_select_byte(4.2, 1.0)
    assert val == (ChargeSelectBits.MAX_CHARGE_VOLTAGE | ChargeSelectBits.MAX_CHARGE_CURRENT_2)
    assert select_byte_to_charge_specs(0x05) == (4.2, 1.0)

    # 4.2V, 1.5A (Bit 0 + Bit 1 + Bit 2) -> 0x07
    val = charge_specs_to_select_byte(4.2, 1.5)
    expected = (
        ChargeSelectBits.MAX_CHARGE_VOLTAGE
        | ChargeSelectBits.MAX_CHARGE_CURRENT_1
        | ChargeSelectBits.MAX_CHARGE_CURRENT_2
    )
    assert val == expected
    assert select_byte_to_charge_specs(0x07) == (4.2, 1.5)


def test_relay_control_bits():
    """Verify 0x6000 Relay Control bit semantics."""
    # Disabled
    assert int(RelayControlBits.CELL_ENABLE) == 1
    assert int(RelayControlBits.CELL_SELECT) == 2

    # Cell 1 Enabled: Bit 0 = 1, Bit 1 = 0 -> 0x01
    c1_en = RelayControlBits.CELL_ENABLE
    assert int(c1_en) == 0x01

    # Cell 2 Enabled: Bit 0 = 1, Bit 1 = 1 -> 0x03
    c2_en = RelayControlBits.CELL_ENABLE | RelayControlBits.CELL_SELECT
    assert int(c2_en) == 0x03
