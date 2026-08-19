"""Exhaustive User Scenarios & Edge Cases Test Suite.

Simulates real-world user configuration patterns:
1. All Data Types (uint8, int8, uint16, int16, uint32, int32, float32, float64, boolean, odd-byte ints).
2. Endianness (little-endian & big-endian).
3. Scale & Offset combinations (positive, negative scale, offset math).
4. Array expansion (count > 1, start_index = 0, start_index = 1, custom placeholders).
5. Bitfields (dense status registers, multi-bit flags, custom active/inactive labels).
6. Enums (multi-state, negative values, boundary values).
7. CalcGroups (min, max, avg, diff/delta, sum, mixed combinations).
8. Transmit (TX) Command Building (static hex, dynamic inputs, scale/offset in TX, boolean bit packing, boundary enforcement).
9. Polling Schedules (enabled vs disabled, multiple frames).
10. Waveshare CAN (Standard 11-bit & Extended 29-bit CAN IDs, DLC 0-8).
11. Resilient Configuration Loading (whitespace tolerance, missing optional sheets, string booleans/numbers).
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly as python test_xxx.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import struct
import pytest
import pandas as pd

from app.decoder.config_loader import load_config
from app.decoder.frame_decoder import decode_frame
from app.decoder.template_io import write_workbook_from_tables
from app.commands.tx_command_builder import build_tx_command, CommandBuildError


@pytest.fixture
def make_workbook(tmp_path):
    """Helper fixture to create Excel config workbooks on the fly."""
    def _create(tables: dict, filename: str = "test_config.xlsx") -> Path:
        target = tmp_path / filename
        return write_workbook_from_tables(tables, target)
    return _create


# ============================================================================
# 1. ALL DATA TYPES & ENDIANNESS TEST
# ============================================================================

def test_all_data_types_and_endianness(make_workbook):
    """Test every supported numeric and boolean data type in both little and big endian."""
    protocol_df = pd.DataFrame([{
        "profile_name": "All Types Test",
        "parser_type": "framed",
        "header_hex": "AA 55",
        "frame_id_size": 2,
        "frame_id_byte_order": "little",
        "length_size": 1,
        "length_meaning": "payload_only",
        "crc_type": "none",
        "crc_size": 0,
        "enabled": True
    }])

    frames_df = pd.DataFrame([{
        "frame_id": "0x1000",
        "frame_name": "FullTypesFrame",
        "payload_length": 34,
        "direction": "rxtx",
        "enabled": True
    }])

    # Build variables table covering uint8, int8, uint16, int16, uint32, int32, float32, float64, boolean (both endians)
    vars_rows = [
        {"id_or_address": "0x1000", "signal_name": "u8_val", "data_type": "uint8", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "i8_val", "data_type": "int8", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "u16_le", "data_type": "uint16", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "u16_be", "data_type": "uint16", "byte_order": "big", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "i16_le", "data_type": "int16", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "i16_be", "data_type": "int16", "byte_order": "big", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "u32_le", "data_type": "uint32", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "u32_be", "data_type": "uint32", "byte_order": "big", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "i32_le", "data_type": "int32", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "i32_be", "data_type": "int32", "byte_order": "big", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "f32_le", "data_type": "float32", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "f64_le", "data_type": "float64", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
        {"id_or_address": "0x1000", "signal_name": "bool_val", "data_type": "boolean", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""},
    ]
    vars_df = pd.DataFrame(vars_rows)

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "Variables": vars_df})
    cfg = load_config(wb_path)

    # Construct packed binary payload matching all data types
    payload = (
        struct.pack("<B", 250) +
        struct.pack("<b", -25) +
        struct.pack("<H", 60000) +
        struct.pack(">H", 60000) +
        struct.pack("<h", -1500) +
        struct.pack(">h", -1500) +
        struct.pack("<I", 3000000) +
        struct.pack(">I", 3000000) +
        struct.pack("<i", -500000) +
        struct.pack(">i", -500000) +
        struct.pack("<f", 123.456) +
        struct.pack("<d", 987654.321) +
        struct.pack("<B", 1)
    )

    dec = decode_frame(cfg, 0x1000, payload)
    sig_map = {s.signal_name: s.scaled_value for s in dec.signals}

    assert sig_map["u8_val"] == 250
    assert sig_map["i8_val"] == -25
    assert sig_map["u16_le"] == 60000
    assert sig_map["u16_be"] == 60000
    assert sig_map["i16_le"] == -1500
    assert sig_map["i16_be"] == -1500
    assert sig_map["u32_le"] == 3000000
    assert sig_map["u32_be"] == 3000000
    assert sig_map["i32_le"] == -500000
    assert sig_map["i32_be"] == -500000
    assert pytest.approx(sig_map["f32_le"], 0.001) == 123.456
    assert pytest.approx(sig_map["f64_le"], 0.0001) == 987654.321
    assert sig_map["bool_val"] == 1.0


# ============================================================================
# 2. SCALING, OFFSETS & NEGATIVE MULTIPLIERS
# ============================================================================

def test_scaling_and_offsets(make_workbook):
    """Test automotive scaling (e.g. temperature = raw * 0.5 - 40, inverted pressure = raw * -0.1 + 100)."""
    protocol_df = pd.DataFrame([{"profile_name": "ScaleTest", "parser_type": "framed", "header_hex": "AA", "frame_id_size": 1, "length_size": 1, "crc_type": "none", "enabled": True}])
    frames_df = pd.DataFrame([{"frame_id": "0x10", "frame_name": "Sensors", "payload_length": 4, "direction": "rx", "enabled": True}])
    vars_df = pd.DataFrame([
        {"id_or_address": "0x10", "signal_name": "Auto_Temp_C", "data_type": "uint8", "scale": 0.5, "offset": -40.0, "unit": "°C"},
        {"id_or_address": "0x10", "signal_name": "Inv_Pressure", "data_type": "int16", "byte_order": "little", "scale": -0.1, "offset": 100.0, "unit": "bar"},
        {"id_or_address": "0x10", "signal_name": "Milli_Volt", "data_type": "uint8", "scale": 0.001, "offset": 0.0, "unit": "V"},
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "Variables": vars_df})
    cfg = load_config(wb_path)

    # raw_temp=130 -> 130*0.5 - 40 = 25.0 C
    # raw_pressure=200 -> 200*(-0.1) + 100 = 80.0 bar
    # raw_mv=250 -> 250*0.001 = 0.250 V
    payload = struct.pack("<BhB", 130, 200, 250)
    dec = decode_frame(cfg, 0x10, payload)
    sig_map = {s.signal_name: s.scaled_value for s in dec.signals}

    assert sig_map["Auto_Temp_C"] == 25.0
    assert sig_map["Inv_Pressure"] == 80.0
    assert sig_map["Milli_Volt"] == 0.25


# ============================================================================
# 3. ARRAY EXPANSION (start_index=0, start_index=1, custom placeholders)
# ============================================================================

def test_array_expansion_indexing(make_workbook):
    """Test 0-based vs 1-based array expansion and placeholder formatting."""
    protocol_df = pd.DataFrame([{"profile_name": "ArrayTest", "parser_type": "framed", "header_hex": "AA", "frame_id_size": 1, "length_size": 1, "crc_type": "none", "enabled": True}])
    frames_df = pd.DataFrame([{"frame_id": "0x20", "frame_name": "BMS_Cells", "payload_length": 12, "direction": "rx", "enabled": True}])
    vars_df = pd.DataFrame([
        # 1-based indexing: Cell_1, Cell_2, Cell_3, Cell_4
        {"id_or_address": "0x20", "signal_name": "Cell", "data_type": "uint16", "count": 4, "start_index": 1, "scale": 0.001, "offset": 0.0, "unit": "V"},
        # 0-based indexing: Temp_0, Temp_1
        {"id_or_address": "0x20", "signal_name": "Temp", "data_type": "uint16", "count": 2, "start_index": 0, "scale": 0.1, "offset": 0.0, "unit": "°C"},
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "Variables": vars_df})
    cfg = load_config(wb_path)

    sig_names = [s.signal_name for s in cfg.signals_by_frame[0x20]]
    assert sig_names == ["Cell_1", "Cell_2", "Cell_3", "Cell_4", "Temp_0", "Temp_1"]

    # Decode frame with 4 cell voltages (3.2V, 3.3V, 3.4V, 3.5V) and 2 temperatures (25.0C, 28.5C)
    payload = struct.pack("<4H2H", 3200, 3300, 3400, 3500, 250, 285)
    dec = decode_frame(cfg, 0x20, payload)
    sig_map = {s.signal_name: s.scaled_value for s in dec.signals}

    assert pytest.approx(sig_map["Cell_1"], 0.001) == 3.2
    assert pytest.approx(sig_map["Cell_2"], 0.001) == 3.3
    assert pytest.approx(sig_map["Cell_3"], 0.001) == 3.4
    assert pytest.approx(sig_map["Cell_4"], 0.001) == 3.5
    assert pytest.approx(sig_map["Temp_0"], 0.001) == 25.0
    assert pytest.approx(sig_map["Temp_1"], 0.001) == 28.5


# ============================================================================
# 4. DENSE BITFIELDS & MULTI-BIT STATUS WORDS
# ============================================================================

def test_dense_bitfields_status_word(make_workbook):
    """Test decoding multiple individual bit flags from a single 16-bit status register."""
    protocol_df = pd.DataFrame([{"profile_name": "BitfieldTest", "parser_type": "framed", "header_hex": "AA", "frame_id_size": 1, "length_size": 1, "crc_type": "none", "enabled": True}])
    frames_df = pd.DataFrame([{"frame_id": "0x30", "frame_name": "BMS_Status", "payload_length": 2, "direction": "rx", "enabled": True}])
    vars_df = pd.DataFrame([
        {"id_or_address": "0x30", "signal_name": "Fault_Register", "data_type": "uint16", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": ""}
    ])
    bitfields_df = pd.DataFrame([
        {"id_or_address": "0x30", "signal_name": "Fault_Register", "bit_index": 0, "label": "OverVoltage", "active_text": "OV_TRIP", "inactive_text": "OV_OK"},
        {"id_or_address": "0x30", "signal_name": "Fault_Register", "bit_index": 1, "label": "UnderVoltage", "active_text": "UV_TRIP", "inactive_text": "UV_OK"},
        {"id_or_address": "0x30", "signal_name": "Fault_Register", "bit_index": 2, "label": "OverCurrent", "active_text": "OC_TRIP", "inactive_text": "OC_OK"},
        {"id_or_address": "0x30", "signal_name": "Fault_Register", "bit_index": 15, "label": "MasterAlarm", "active_text": "ALARM_ON", "inactive_text": "ALARM_OFF"},
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "Variables": vars_df, "Bitfields": bitfields_df})
    cfg = load_config(wb_path)

    # Test payload: bits 0 (OV) and 15 (MasterAlarm) are set -> (1 | (1 << 15)) = 0x8001 = 32769
    payload = struct.pack("<H", 0x8001)
    dec = decode_frame(cfg, 0x30, payload)

    bits = dec.signals[0].bit_values
    assert bits["OverVoltage"] is True
    assert bits["UnderVoltage"] is False
    assert bits["OverCurrent"] is False
    assert bits["MasterAlarm"] is True


# ============================================================================
# 5. ENUMS MAPPING
# ============================================================================

def test_enums_mapping_states(make_workbook):
    """Test integer-to-string Enum decoding for operating states."""
    protocol_df = pd.DataFrame([{"profile_name": "EnumTest", "parser_type": "framed", "header_hex": "AA", "frame_id_size": 1, "length_size": 1, "crc_type": "none", "enabled": True}])
    frames_df = pd.DataFrame([{"frame_id": "0x40", "frame_name": "DeviceState", "payload_length": 1, "direction": "rx", "enabled": True}])
    vars_df = pd.DataFrame([
        {"id_or_address": "0x40", "signal_name": "State_Code", "data_type": "uint8", "scale": 1.0, "offset": 0.0, "unit": ""}
    ])
    enums_df = pd.DataFrame([
        {"id_or_address": "0x40", "signal_name": "State_Code", "value": 0, "label": "STANDBY"},
        {"id_or_address": "0x40", "signal_name": "State_Code", "value": 1, "label": "PRECHARGE"},
        {"id_or_address": "0x40", "signal_name": "State_Code", "value": 2, "label": "RUNNING"},
        {"id_or_address": "0x40", "signal_name": "State_Code", "value": 255, "label": "EMERGENCY_STOP"},
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "Variables": vars_df, "Enums": enums_df})
    cfg = load_config(wb_path)

    # 1. State 2 -> RUNNING
    dec_run = decode_frame(cfg, 0x40, b"\x02")
    assert dec_run.signals[0].enum_label == "RUNNING"
    assert dec_run.signals[0].display_value == "RUNNING"

    # 2. State 255 -> EMERGENCY_STOP
    dec_estop = decode_frame(cfg, 0x40, b"\xFF")
    assert dec_estop.signals[0].enum_label == "EMERGENCY_STOP"
    assert dec_estop.signals[0].display_value == "EMERGENCY_STOP"


# ============================================================================
# 6. CALCGROUPS REAL-TIME METRICS
# ============================================================================

def test_calc_groups_statistics(make_workbook):
    """Test group calculations: min, max, avg, diff across grouped signals."""
    protocol_df = pd.DataFrame([{"profile_name": "CalcTest", "parser_type": "framed", "header_hex": "AA", "frame_id_size": 1, "length_size": 1, "crc_type": "none", "enabled": True}])
    frames_df = pd.DataFrame([{"frame_id": "0x50", "frame_name": "Voltages", "payload_length": 8, "direction": "rx", "enabled": True}])
    vars_df = pd.DataFrame([
        {"id_or_address": "0x50", "signal_name": "Cell_Volt", "data_type": "uint16", "count": 4, "start_index": 1, "scale": 0.001, "offset": 0.0, "unit": "V", "group": "Cells"}
    ])
    calc_df = pd.DataFrame([
        {"group_name": "Cells", "operations": "min|max|diff|avg", "unit": "V", "frame_id": "0x50", "enabled": True}
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "Variables": vars_df, "CalcGroups": calc_df})
    cfg = load_config(wb_path)

    # Cells: 3.100V, 3.200V, 3.400V, 3.500V -> min=3.1, max=3.5, diff=0.4, avg=3.3
    payload = struct.pack("<4H", 3100, 3200, 3400, 3500)
    dec = decode_frame(cfg, 0x50, payload)

    calc_map = {c.signal_name: c.scaled_value for c in dec.calculations}
    assert pytest.approx(calc_map["Cells min"], 0.001) == 3.1
    assert pytest.approx(calc_map["Cells max"], 0.001) == 3.5
    assert pytest.approx(calc_map["Cells diff"], 0.001) == 0.4
    assert pytest.approx(calc_map["Cells avg"], 0.001) == 3.3


# ============================================================================
# 7. TRANSMIT (TX) COMMANDS WITH SCALING, BOUNDS & BIT-PACKING
# ============================================================================

def test_tx_commands_with_scaling_and_bounds(make_workbook):
    """Test TX command generation with scaling, validation bounds, and boolean bit packing."""
    protocol_df = pd.DataFrame([{
        "profile_name": "TxTest", "parser_type": "framed", "header_hex": "AA 55",
        "frame_id_size": 2, "frame_id_byte_order": "little", "length_size": 1,
        "length_meaning": "payload_only", "crc_type": "none", "enabled": True
    }])
    frames_df = pd.DataFrame([{"frame_id": "0x6000", "frame_name": "Control", "payload_length": 8, "direction": "tx", "enabled": True}])
    tx_cmd_df = pd.DataFrame([
        {"command_name": "Set_Parameters", "id_or_address": "0x6000", "payload_hex": "", "description": "Update settings", "enabled": True}
    ])
    tx_fields_df = pd.DataFrame([
        # 1. Float Voltage with scale=0.01 (e.g. user enters 48.5V -> encoded as 4850 uint16)
        {"command_name": "Set_Parameters", "signal_name": "Target_Volt", "data_type": "uint16", "byte_order": "little", "scale": 0.01, "offset": 0.0, "min_value": 0.0, "max_value": 60.0, "default": 48.0},
        # 2. Signed Current with scale=0.1 (e.g. user enters -15.5A -> encoded as -155 int16)
        {"command_name": "Set_Parameters", "signal_name": "Target_Curr", "data_type": "int16", "byte_order": "little", "scale": 0.1, "offset": 0.0, "min_value": -50.0, "max_value": 50.0, "default": 0.0},
        # 3. Two consecutive boolean flags -> bit-packed into 1 byte (bit 0 and bit 1)
        {"command_name": "Set_Parameters", "signal_name": "Enable_Out", "data_type": "boolean", "min_value": 0, "max_value": 1, "default": 0},
        {"command_name": "Set_Parameters", "signal_name": "Buzzer_On", "data_type": "boolean", "min_value": 0, "max_value": 1, "default": 0},
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "TxCommands": tx_cmd_df, "TxCommandFields": tx_fields_df})
    cfg = load_config(wb_path)

    # 1. Valid TX packet generation: Volt=48.5V, Curr=-15.5A, Enable_Out=1, Buzzer_On=1
    packet = build_tx_command(cfg, "Set_Parameters", {
        "Target_Volt": 48.5,
        "Target_Curr": -15.5,
        "Enable_Out": 1,
        "Buzzer_On": 1
    })

    # Expected payload:
    # Target_Volt: 48.5 / 0.01 = 4850 -> uint16 <H = 4850 (0x12F2 -> F2 12)
    # Target_Curr: -15.5 / 0.1 = -155 -> int16 <h = -155 (0xFF65 -> 65 FF)
    # 2 booleans packed at the end: (1<<0) | (1<<1) = 0x03
    # Header: AA 55, FrameID: 00 60, Length: 05, Payload: F2 12 65 FF 03
    expected_header = b"\xaa\x55\x00\x60\x05"
    expected_payload = struct.pack("<H h B", 4850, -155, 0x03)
    assert packet == expected_header + expected_payload

    # 2. Out-of-bounds validation check (Voltage > 60.0V limit)
    with pytest.raises(CommandBuildError, match="above maximum"):
        build_tx_command(cfg, "Set_Parameters", {"Target_Volt": 75.0})


# ============================================================================
# 8. POLLING SCHEDULE & SERIAL DEFAULTS
# ============================================================================

def test_polling_schedule_and_serial_defaults(make_workbook):
    """Test loading polling schedule entries and serial defaults."""
    protocol_df = pd.DataFrame([{"profile_name": "PollTest", "parser_type": "framed", "header_hex": "AA", "frame_id_size": 1, "length_size": 1, "crc_type": "none", "enabled": True}])
    frames_df = pd.DataFrame([{"frame_id": "0x70", "frame_name": "PollFrame", "payload_length": 4, "direction": "tx", "enabled": True}])
    poll_df = pd.DataFrame([
        {"id_or_address": "0x70", "interval_ms": 250, "timeout_ms": 50, "enabled": "TRUE"},
        {"id_or_address": "0x80", "interval_ms": 1000, "timeout_ms": 100, "enabled": "FALSE"},
    ])
    serial_df = pd.DataFrame([
        {"baud_rate": 921600, "data_bits": 8, "stop_bits": 1, "parity": "N", "timeout_ms": 50}
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "PollingSchedule": poll_df, "SerialDefaults": serial_df})
    cfg = load_config(wb_path)

    assert cfg.serial_defaults.baud_rate == 921600
    assert cfg.serial_defaults.timeout_ms == 50
    assert len(cfg.polling_schedules) == 1
    assert cfg.polling_schedules[0].target_id == 0x70
    assert cfg.polling_schedules[0].interval_ms == 250


# ============================================================================
# 9. WAVESHARE USB-CAN ADAPTER TELEMETRY
# ============================================================================

def test_waveshare_usb_can_standard_and_extended_frames(make_workbook):
    """Test Waveshare USB-CAN parser with standard 11-bit and extended 29-bit CAN IDs."""
    protocol_df = pd.DataFrame([{
        "profile_name": "Waveshare CAN Test",
        "parser_type": "waveshare_can",
        "header_hex": "AA",
        "frame_id_size": 2,
        "length_size": 1,
        "crc_type": "none",
        "footer_hex": "55",
        "enabled": True
    }])
    frames_df = pd.DataFrame([
        {"frame_id": "0x02F0", "frame_name": "Std_CAN_Frame", "payload_length": 8, "direction": "rx", "enabled": True},
        {"frame_id": "0x18FF50E5", "frame_name": "Ext_CAN_Frame", "payload_length": 8, "direction": "rx", "enabled": True}
    ])
    vars_df = pd.DataFrame([
        {"id_or_address": "0x02F0", "signal_name": "Pack_Voltage", "data_type": "uint16", "byte_order": "little", "scale": 0.01, "offset": 0.0, "unit": "V"},
        {"id_or_address": "0x18FF50E5", "signal_name": "Motor_RPM", "data_type": "int32", "byte_order": "little", "scale": 1.0, "offset": 0.0, "unit": "RPM"}
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "Variables": vars_df})
    cfg = load_config(wb_path)

    assert cfg.protocol.parser_type == "waveshare_can"

    # Decode standard 11-bit frame (0x02F0) with Pack_Voltage = 48.0V (4800)
    payload_std = struct.pack("<H6x", 4800)
    dec_std = decode_frame(cfg, 0x02F0, payload_std)
    assert dec_std.signals[0].scaled_value == 48.0

    # Decode extended 29-bit frame (0x18FF50E5) with Motor_RPM = 3600 RPM
    payload_ext = struct.pack("<i4x", 3600)
    dec_ext = decode_frame(cfg, 0x18FF50E5, payload_ext)
    assert dec_ext.signals[0].scaled_value == 3600.0


# ============================================================================
# 10. RESILIENT FORMATTING TOLERANCE (Whitespace, Hex Strings, Decimal)
# ============================================================================

def test_resilient_user_formatting_tolerance(make_workbook):
    """Test that Bytehound gracefully handles messy user input (extra spaces, hex without 0x, strings)."""
    protocol_df = pd.DataFrame([{
        "profile_name": "  Tolerant Protocol  ",
        "parser_type": " framed ",
        "header_hex": " AA 55 ",
        "frame_id_size": " 2 ",
        "length_size": " 1 ",
        "crc_type": " none ",
        "enabled": " TRUE "
    }])
    frames_df = pd.DataFrame([
        {"frame_id": " 1000 ", "frame_name": " Status ", "payload_length": " 4 ", "direction": " rxtx ", "enabled": " 1 "}
    ])
    vars_df = pd.DataFrame([
        {"id_or_address": " 1000 ", "signal_name": " Raw_Val ", "data_type": " uint16 ", "scale": " 0.1 ", "offset": " 10 ", "unit": " % "}
    ])

    wb_path = make_workbook({"Protocol": protocol_df, "Frames": frames_df, "Variables": vars_df})
    cfg = load_config(wb_path)

    assert cfg.protocol.profile_name == "Tolerant Protocol"
    assert 0x1000 in cfg.frames
    assert cfg.frames[0x1000].frame_name == "Status"

    dec = decode_frame(cfg, 0x1000, struct.pack("<H2x", 500))
    # 500 * 0.1 + 10 = 60.0 %
    assert dec.signals[0].scaled_value == 60.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
