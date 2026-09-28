"""Protocol definitions and constants for Experiment 6 Single Cell BMS."""

from enum import IntEnum, IntFlag

# Framing Constants
HEADER_BYTES = b"\xAA\x55"
HEADER_LEN = 2
FRAME_ID_LEN = 2
LENGTH_LEN = 1
PAYLOAD_OVERHEAD = HEADER_LEN + FRAME_ID_LEN + LENGTH_LEN  # 5 bytes

# Frame IDs
FRAME_CELL_DATA = 0x1000       # Cell Voltages & Temperatures (8 bytes rx)
FRAME_BOARD_PARAMS = 0x2000    # Ambient & System Voltages (6 bytes rx)
FRAME_FAULT_SOC = 0x3000       # Fault Status & SoC Estimation (5 bytes rx)

FRAME_RELAY_CTRL = 0x6000      # Cell Relay Control (1 byte tx/rx)
FRAME_CHARGE_SEL = 0x6001      # Cell Charge Select (1 byte tx/rx)
FRAME_CHARGE_CTRL = 0x6002     # Cell Charge Control (1 byte tx/rx)
FRAME_DISCHARGE_CTRL = 0x6003  # Cell Discharge Control (1 byte tx/rx)
FRAME_DISCHARGE_SEL = 0x6004   # Cell Discharge Select (1 byte tx/rx)

# Payload Lengths
PAYLOAD_LEN_CELL_DATA = 8
PAYLOAD_LEN_BOARD_PARAMS = 6
PAYLOAD_LEN_FAULT_SOC = 5
PAYLOAD_LEN_CMD = 1

# Fault Bitfield Flags (Frame 0x3000 Fault byte)
class BMSFaultFlags(IntFlag):
    NONE = 0
    COV = 1 << 0  # Cell Over Voltage
    CUV = 1 << 1  # Cell Under Voltage
    OCC = 1 << 2  # Over Current Charge
    OCD = 1 << 3  # Over Current Discharge
    COT = 1 << 4  # Cell Over Temperature
    CUT = 1 << 5  # Cell Under Temperature

FAULT_LABELS = {
    BMSFaultFlags.COV: "Cell Over Voltage (COV)",
    BMSFaultFlags.CUV: "Cell Under Voltage (CUV)",
    BMSFaultFlags.OCC: "Over Current Charge (OCC)",
    BMSFaultFlags.OCD: "Over Current Discharge (OCD)",
    BMSFaultFlags.COT: "Cell Over Temperature (COT)",
    BMSFaultFlags.CUT: "Cell Under Temperature (CUT)",
}

# Bit positions for 0x6000 (Relay Control)
class RelayControlBits(IntFlag):
    CELL_ENABLE = 1 << 0
    CELL_SELECT = 1 << 1

# Bit positions for 0x6001 (Charge Select)
class ChargeSelectBits(IntFlag):
    MAX_CHARGE_VOLTAGE = 1 << 0
    MAX_CHARGE_CURRENT_1 = 1 << 1
    MAX_CHARGE_CURRENT_2 = 1 << 2

# Bit positions for 0x6002 (Charge Control)
class ChargeControlBits(IntFlag):
    CHARGE_ENABLE = 1 << 0
    CHARGE_COMPARATOR_RESET = 1 << 1

# Bit positions for 0x6003 (Discharge Control)
class DischargeControlBits(IntFlag):
    DISCHARGE_ENABLE = 1 << 0
    DISCHARGE_COMPARATOR_RESET = 1 << 1

# Bit positions for 0x6004 (Discharge Select)
class DischargeSelectBits(IntFlag):
    LOAD_1 = 1 << 0
    LOAD_2 = 1 << 1
    LOAD_3 = 1 << 2
    LOAD_4 = 1 << 3

# Engineering Scales
SCALE_CELL_VOLTAGE = 0.001        # uint16 (V)
SCALE_CELL_CURRENT = 0.001        # int16 (A)
SCALE_TEMPERATURE = 0.1           # uint16 (°C)
SCALE_BOARD_VOLTAGE = 0.001       # uint16 (V)
SCALE_SOC = 0.01                  # uint16 (%)

# Serial Defaults
DEFAULT_BAUD_RATE = 115200
DEFAULT_TIMEOUT_S = 0.1
DEFAULT_DATA_BITS = 8
DEFAULT_STOP_BITS = 1
DEFAULT_PARITY = "N"

# ==============================================================================
# Discharge Load Bank Specification (0x6004)
# 4 binary-weighted loads: L1=0.2A, L2=0.4A, L3=0.8A, L4=1.6A
# Decimal Value = L1*(1) + L2*(2) + L3*(4) + L4*(8) (range 0..15 -> 0.0A..3.0A)
# ==============================================================================
DISCHARGE_LOAD_WEIGHTS = {
    1: 0.2,  # L1: 0.2 A
    2: 0.4,  # L2: 0.4 A
    3: 0.8,  # L3: 0.8 A
    4: 1.6,  # L4: 1.6 A
}

DISCHARGE_CURRENT_STEP_A = 0.2
MAX_DISCHARGE_CURRENT_A = 3.0

# 16-State Lookup Table: decimal -> (L1, L2, L3, L4, num_switches, total_current_a)
DISCHARGE_TABLE: dict[int, tuple[bool, bool, bool, bool, int, float]] = {
    dec: (
        bool(dec & 1),
        bool(dec & 2),
        bool(dec & 4),
        bool(dec & 8),
        bin(dec).count("1"),
        round(dec * DISCHARGE_CURRENT_STEP_A, 1),
    )
    for dec in range(16)
}


def discharge_decimal_to_current(decimal_val: int) -> float:
    """Calculate total discharge current in Amperes from 4-bit load register (0x6004)."""
    return round((decimal_val & 0x0F) * DISCHARGE_CURRENT_STEP_A, 1)


def discharge_current_to_decimal(current_a: float) -> int:
    """Find the nearest 4-bit load decimal (0..15) for a target discharge current."""
    val = round(max(0.0, min(MAX_DISCHARGE_CURRENT_A, current_a)) / DISCHARGE_CURRENT_STEP_A)
    return int(val)


# ==============================================================================
# Charge Select Specification (0x6001)
# Bit 0: Max Charge Voltage (0 = 3.6V, 1 = 4.2V)
# Bit 1: Charge Current 1 (0 = 0A, 1 = 0.5A)
# Bit 2: Charge Current 2 (0 = 0A, 1 = 1.0A)
# Bit 1+2: Total 1.5A
# ==============================================================================
def charge_specs_to_select_byte(max_voltage: float, target_current: float) -> int:
    """Encode max voltage and target current into 0x6001 Charge Select byte."""
    payload = 0
    # Bit 0: Max Charge Voltage (0 = 3.6V, 1 = 4.2V)
    if max_voltage >= 4.0:
        payload |= ChargeSelectBits.MAX_CHARGE_VOLTAGE

    # Bits 1 & 2: Current selection
    if target_current > 1.25:
        payload |= ChargeSelectBits.MAX_CHARGE_CURRENT_1 | ChargeSelectBits.MAX_CHARGE_CURRENT_2  # 1.5 A
    elif target_current > 0.75:
        payload |= ChargeSelectBits.MAX_CHARGE_CURRENT_2  # 1.0 A
    elif target_current > 0.25:
        payload |= ChargeSelectBits.MAX_CHARGE_CURRENT_1  # 0.5 A
    # Else 0.0 A
    return payload


def select_byte_to_charge_specs(select_byte: int) -> tuple[float, float]:
    """Decode 0x6001 Charge Select byte into (max_voltage, target_current_a)."""
    voltage = 4.2 if (select_byte & ChargeSelectBits.MAX_CHARGE_VOLTAGE) else 3.6
    current = 0.0
    if select_byte & ChargeSelectBits.MAX_CHARGE_CURRENT_1:
        current += 0.5
    if select_byte & ChargeSelectBits.MAX_CHARGE_CURRENT_2:
        current += 1.0
    return (voltage, round(current, 1))

