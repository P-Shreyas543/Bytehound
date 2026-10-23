"""Unit tests for binary packet codec against Experiment_6_SC specification."""

import struct
from single_cell_cycler.comm.packet_codec import (
    BoardParamsTelemetry,
    CellDataTelemetry,
    FaultSoCTelemetry,
    decode_stream,
    encode_command_packet,
)
from single_cell_cycler.comm.protocol_defs import (
    BMSFaultFlags,
    ChargeControlBits,
    ChargeSelectBits,
    DischargeControlBits,
    DischargeSelectBits,
    FRAME_BOARD_PARAMS,
    FRAME_CELL_DATA,
    FRAME_CHARGE_CTRL,
    FRAME_CHARGE_SEL,
    FRAME_DISCHARGE_CTRL,
    FRAME_DISCHARGE_SEL,
    FRAME_FAULT_SOC,
    FRAME_RELAY_CTRL,
    RelayControlBits,
)


def test_encode_command_packet():
    # 1. Relay Control (0x6000): Cell Enable (bit 0) + Cell Select (bit 1) = 3
    pkt = encode_command_packet(FRAME_RELAY_CTRL, RelayControlBits.CELL_ENABLE | RelayControlBits.CELL_SELECT)
    assert pkt == b"\xAA\x55\x00\x60\x01\x03"

    # 2. Charge Select (0x6001): Rate 1 (bit 1) = 2
    pkt = encode_command_packet(FRAME_CHARGE_SEL, ChargeSelectBits.MAX_CHARGE_CURRENT_1)
    assert pkt == b"\xAA\x55\x01\x60\x01\x02"

    # 3. Charge Control (0x6002): Charge Enable (bit 0) = 1
    pkt = encode_command_packet(FRAME_CHARGE_CTRL, ChargeControlBits.CHARGE_ENABLE)
    assert pkt == b"\xAA\x55\x02\x60\x01\x01"

    # 4. Discharge Control (0x6003): Discharge Enable (bit 0) = 1
    pkt = encode_command_packet(FRAME_DISCHARGE_CTRL, DischargeControlBits.DISCHARGE_ENABLE)
    assert pkt == b"\xAA\x55\x03\x60\x01\x01"

    # 5. Discharge Select (0x6004): Load 1 (bit 0) + Load 3 (bit 2) = 1 | 4 = 5
    pkt = encode_command_packet(FRAME_DISCHARGE_SEL, DischargeSelectBits.LOAD_1 | DischargeSelectBits.LOAD_3)
    assert pkt == b"\xAA\x55\x04\x60\x01\x05"


def test_decode_cell_data():
    # Voltage: 3750 mV (3.750 V)
    # Current: -1500 mA (-1.500 A)
    # Term Temp: 285 (28.5 °C)
    # Body Temp: 290 (29.0 °C)
    payload = struct.pack("<HhHH", 3750, -1500, 285, 290)
    wire_frame = b"\xAA\x55\x00\x10\x08" + payload

    packets, rem = decode_stream(bytearray(wire_frame))
    assert len(packets) == 1
    assert len(rem) == 0

    pkt = packets[0]
    assert isinstance(pkt, CellDataTelemetry)
    assert pkt.voltage == 3.750
    assert pkt.current == -1.500
    assert pkt.terminal_temp == 28.5
    assert pkt.body_temp == 29.0


def test_decode_board_params():
    # Ambient Temp: 245 (24.5 °C)
    # Hardware word order: ambient, load_bus (3700 mV = 3.700 V), charge_bus (5200 mV = 5.200 V)
    payload = struct.pack("<HHH", 245, 3700, 5200)
    wire_frame = b"\xAA\x55\x00\x20\x06" + payload

    packets, rem = decode_stream(bytearray(wire_frame))
    assert len(packets) == 1
    assert len(rem) == 0

    pkt = packets[0]
    assert isinstance(pkt, BoardParamsTelemetry)
    assert pkt.ambient_temp == 24.5
    assert pkt.charge_voltage == 5.200
    assert pkt.load_voltage == 3.700


def test_decode_fault_soc():
    # Fault: COV (bit 0) + COT (bit 4) = 1 | 16 = 17 (0x11)
    # SoC OCV: 8550 (85.50 %)
    # SoC CC: 8520 (85.20 %)
    payload = struct.pack("<BHH", 0x11, 8550, 8520)
    wire_frame = b"\xAA\x55\x00\x30\x05" + payload

    packets, rem = decode_stream(bytearray(wire_frame))
    assert len(packets) == 1
    pkt = packets[0]
    assert isinstance(pkt, FaultSoCTelemetry)
    assert pkt.cov is True
    assert pkt.cuv is False
    assert pkt.cot is True
    assert pkt.soc_ocv == 85.50
    assert pkt.soc_cc == 85.20
    assert pkt.has_any_fault is True


def test_stream_framing_with_garbage_and_partial_chunks():
    # Test garbage prefix, complete packet, and incomplete trailing chunk
    payload = struct.pack("<HhHH", 4100, 2000, 300, 310)
    valid_frame = b"\xAA\x55\x00\x10\x08" + payload

    stream = bytearray(b"\xFF\x00\xAA" + valid_frame + b"\xAA\x55\x00\x20")
    packets, rem = decode_stream(stream)

    assert len(packets) == 1
    assert isinstance(packets[0], CellDataTelemetry)
    assert packets[0].voltage == 4.100
    assert packets[0].current == 2.000
    # Incomplete frame AA 55 00 20 remains in buffer for next read
    assert rem == b"\xAA\x55\x00\x20"
