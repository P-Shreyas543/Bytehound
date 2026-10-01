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


def test_decode_fault_soc_extended_17byte():
    # 17-byte layout: fault byte + 8 x 16-bit words
    # Fault: CUV (bit 1) = 0x02
    # EKF SoC: 8250 (82.50 * 100 -> 82.5%)
    # VR1: 15 (15 * 0.001 -> 0.015 V)
    # VR2: 25 (25 * 0.001 -> 0.025 V)
    # P_diag: 10, 20, 30 (x 0.001 -> 0.010, 0.020, 0.030)
    # SOC CC: 8100 (81.00 * 100 -> 81.0%)
    # SOC OCV: 8300 (83.00 * 100 -> 83.0%)
    payload = struct.pack("<B8H", 0x02, 8250, 15, 25, 10, 20, 30, 8100, 8300)
    wire_frame = b"\xAA\x55\x00\x30\x11" + payload

    packets, rem = decode_stream(bytearray(wire_frame))
    assert len(packets) == 1
    assert len(rem) == 0

    pkt = packets[0]
    assert isinstance(pkt, FaultSoCTelemetry)
    assert pkt.cuv is True
    assert pkt.cov is False
    assert pkt.soc_ekf == 82.5
    assert pkt.soc_main == 82.5
    assert pkt.vr1 == 0.015
    assert pkt.vr2 == 0.025
    assert pkt.p_diag == (0.01, 0.02, 0.03)
    assert pkt.soc_cc == 81.0
    assert pkt.soc_ocv == 83.0


def test_decode_fault_soc_extended_negative_polarization_voltages():
    """VR1 / VR2 are signed: on discharge the board sends e.g. -1 mV and -8 mV (0xFFFF, 0xFFF8),
    which must not decode as 65.535 V / 65.528 V."""
    payload = struct.pack("<BHhh5H", 0x00, 350, -1, -8, 0, 0, 0, 276, 285)
    packets, rem = decode_stream(bytearray(b"\xAA\x55\x00\x30\x11" + payload))
    assert len(packets) == 1 and len(rem) == 0
    pkt = packets[0]
    assert pkt.vr1 == -0.001
    assert pkt.vr2 == -0.008
    assert (pkt.soc_ekf, pkt.soc_cc, pkt.soc_ocv) == (35.0, 27.6, 28.5)


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


def test_decode_fault_soc_mcu_tenths_scale():
    # MCU sends SoC fraction * 1000 (0.1% resolution, e.g. 994 for 99.4%)
    # Test 17-byte frame
    payload_17 = struct.pack("<B8H", 0x00, 994, 0, 0, 0, 0, 0, 994, 994)
    wire_17 = b"\xAA\x55\x00\x30\x11" + payload_17
    pkts_17, _ = decode_stream(bytearray(wire_17))
    assert len(pkts_17) == 1
    assert pkts_17[0].soc_ekf == 99.4
    assert pkts_17[0].soc_cc == 99.4
    assert pkts_17[0].soc_ocv == 99.4
    assert pkts_17[0].soc_main == 99.4

    # Test 5-byte frame
    payload_5 = struct.pack("<BHH", 0x00, 994, 994)
    wire_5 = b"\xAA\x55\x00\x30\x05" + payload_5
    pkts_5, _ = decode_stream(bytearray(wire_5))
    assert len(pkts_5) == 1
    assert pkts_5[0].soc_ocv == 99.4
    assert pkts_5[0].soc_cc == 99.4
    assert pkts_5[0].soc_main == 99.4

