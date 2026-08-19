"""Test Suite for User Configuration Mistakes, Bad Inputs, and Error Reporting.

Verifies that when users make mistakes in their Excel/CSV configuration files:
1. Bytehound catches them cleanly and raises a descriptive `ConfigError`.
2. Error messages specify the sheet name, row number, column, and did-you-mean hints.
3. The app NEVER crashes or throws unhandled tracebacks (ZeroDivisionError, KeyError, IndexError, ValueError).
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly as python test_xxx.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pandas as pd

from app.decoder.config_loader import ConfigError, load_config
from app.decoder.template_io import write_workbook_from_tables


@pytest.fixture
def make_workbook(tmp_path):
    """Helper fixture to create Excel config workbooks on the fly."""
    def _create(tables: dict, filename: str = "bad_user_config.xlsx") -> Path:
        target = tmp_path / filename
        return write_workbook_from_tables(tables, target)
    return _create


def valid_protocol_df():
    return pd.DataFrame([{
        "profile_name": "ValidProfile",
        "parser_type": "framed",
        "header_hex": "AA 55",
        "frame_id_size": 2,
        "frame_id_byte_order": "little",
        "length_size": 1,
        "length_meaning": "payload_only",
        "crc_type": "none",
        "enabled": True
    }])


def valid_frames_df():
    return pd.DataFrame([{
        "frame_id": "0x1000",
        "frame_name": "TestFrame",
        "payload_length": 8,
        "direction": "rxtx",
        "enabled": True
    }])


# ============================================================================
# 1. PROTOCOL SHEET ERRORS
# ============================================================================

def test_err_invalid_header_hex_characters(make_workbook):
    """User types non-hex characters in header_hex (e.g. 'ZZ' or 'AA GG')."""
    proto = valid_protocol_df()
    proto["header_hex"] = "AA ZZ"
    wb = make_workbook({"Protocol": proto, "Frames": valid_frames_df()})
    with pytest.raises(ConfigError, match="header_hex: invalid hex"):
        load_config(wb)


def test_err_odd_length_header_hex(make_workbook):
    """User types an odd number of hex digits (e.g. 'AA5')."""
    proto = valid_protocol_df()
    proto["header_hex"] = "AA5"
    wb = make_workbook({"Protocol": proto, "Frames": valid_frames_df()})
    with pytest.raises(ConfigError, match="hex string must have even length"):
        load_config(wb)


def test_err_unknown_crc_type(make_workbook):
    """User types a non-existent CRC algorithm (e.g. 'crc16_super')."""
    proto = valid_protocol_df()
    proto["crc_type"] = "crc16_super"
    wb = make_workbook({"Protocol": proto, "Frames": valid_frames_df()})
    with pytest.raises(ConfigError, match="crc_type"):
        load_config(wb)


def test_err_incompatible_crc_size(make_workbook):
    """User specifies CRC16 Modbus (2 bytes) but sets crc_size to 4."""
    proto = valid_protocol_df()
    proto["crc_type"] = "crc16_modbus"
    proto["crc_size"] = 4
    wb = make_workbook({"Protocol": proto, "Frames": valid_frames_df()})
    with pytest.raises(ConfigError, match="crc_size must be 2 when crc_type is 'crc16_modbus'"):
        load_config(wb)


def test_err_invalid_frame_id_size(make_workbook):
    """User sets frame_id_size to 0 or negative."""
    proto = valid_protocol_df()
    proto["frame_id_size"] = 0
    wb = make_workbook({"Protocol": proto, "Frames": valid_frames_df()})
    with pytest.raises(ConfigError, match="frame_id_size must be >= 1"):
        load_config(wb)


def test_err_no_enabled_protocol_profile(make_workbook):
    """User marks enabled = False on all protocol profiles."""
    proto = valid_protocol_df()
    proto["enabled"] = False
    wb = make_workbook({"Protocol": proto, "Frames": valid_frames_df()})
    with pytest.raises(ConfigError, match="no enabled protocol profile found"):
        load_config(wb)


def test_err_multiple_enabled_protocol_profiles(make_workbook):
    """User creates two enabled protocol profiles."""
    proto = pd.DataFrame([
        {"profile_name": "Profile1", "header_hex": "AA", "frame_id_size": 1, "length_size": 1, "crc_type": "none", "enabled": True},
        {"profile_name": "Profile2", "header_hex": "BB", "frame_id_size": 1, "length_size": 1, "crc_type": "none", "enabled": True},
    ])
    wb = make_workbook({"Protocol": proto, "Frames": valid_frames_df()})
    with pytest.raises(ConfigError, match="more than one enabled profile"):
        load_config(wb)


# ============================================================================
# 2. FRAMES SHEET ERRORS
# ============================================================================

def test_err_invalid_frame_id_format(make_workbook):
    """User types non-hex, non-numeric frame_id (e.g. 'FRAME_ALPHA')."""
    frames = pd.DataFrame([
        {"frame_id": "FRAME_ALPHA", "frame_name": "BadFrame", "payload_length": 4, "direction": "rx", "enabled": True}
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": frames})
    with pytest.raises(ConfigError, match="Invalid frame ID for frames row 2.frame_id"):
        load_config(wb)


def test_err_invalid_direction(make_workbook):
    """User types invalid direction (e.g. 'input_only')."""
    frames = pd.DataFrame([
        {"frame_id": "0x10", "frame_name": "BadDir", "payload_length": 4, "direction": "input_only", "enabled": True}
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": frames})
    with pytest.raises(ConfigError, match="direction must be 'rx', 'tx', 'rxtx'"):
        load_config(wb)


# ============================================================================
# 3. VARIABLES SHEET ERRORS
# ============================================================================

def test_err_unknown_data_type(make_workbook):
    """User specifies unknown data type (e.g. 'uint128' or 'str')."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "BadSignal", "data_type": "uint128"}
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df})
    with pytest.raises(ConfigError, match="data_type .* must be one of"):
        load_config(wb)


def test_err_duplicate_signal_name_in_same_frame(make_workbook):
    """User defines two signals with the exact same name in the same frame."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "Voltage", "data_type": "uint16"},
        {"id_or_address": "0x1000", "signal_name": "Voltage", "data_type": "uint16"},
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df})
    with pytest.raises(ConfigError, match="duplicate signal 'Voltage' in frame 0x1000"):
        load_config(wb)


def test_err_overlapping_signal_byte_ranges(make_workbook):
    """User defines two multi-byte signals that overlap in memory."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "SigA", "data_type": "uint32", "start_byte": 0},  # bytes 0..3
        {"id_or_address": "0x1000", "signal_name": "SigB", "data_type": "uint16", "start_byte": 2},  # bytes 2..3 (COLLISION!)
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df})
    with pytest.raises(ConfigError, match="signal 'SigB' overlaps 'SigA'"):
        load_config(wb)


def test_err_boolean_bit_offset_collision(make_workbook):
    """User defines two boolean signals on the exact same byte AND exact same bit index."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "Bool1", "data_type": "boolean", "start_byte": 0, "bit_index": 3},
        {"id_or_address": "0x1000", "signal_name": "Bool2", "data_type": "boolean", "start_byte": 0, "bit_index": 3},
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df})
    with pytest.raises(ConfigError, match="collides with another boolean on byte 0, bit_offset 3"):
        load_config(wb)


def test_err_invalid_array_count(make_workbook):
    """User sets array count to 0 or negative."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "Cell", "data_type": "uint16", "count": 0}
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df})
    with pytest.raises(ConfigError, match="count must be >= 1"):
        load_config(wb)


# ============================================================================
# 4. BITFIELDS & ENUMS SHEET ERRORS
# ============================================================================

def test_err_bitfield_references_unknown_variable(make_workbook):
    """User adds bitfield row pointing to a non-existent variable name."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "StatusWord", "data_type": "uint16"}
    ])
    bitfields_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "GhostVariable", "bit_index": 0, "label": "Alarm"}
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df, "Bitfields": bitfields_df})
    with pytest.raises(ConfigError, match="unknown variable 'GhostVariable'"):
        load_config(wb)


def test_err_duplicate_bitfield_index(make_workbook):
    """User defines bit_index 0 twice on the same register."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "StatusWord", "data_type": "uint16"}
    ])
    bitfields_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "StatusWord", "bit_index": 0, "label": "Alarm1"},
        {"id_or_address": "0x1000", "signal_name": "StatusWord", "bit_index": 0, "label": "Alarm2"},
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df, "Bitfields": bitfields_df})
    with pytest.raises(ConfigError, match="duplicate bit_index 0 for signal 'StatusWord'"):
        load_config(wb)


def test_err_enum_references_unknown_variable(make_workbook):
    """User adds enum row pointing to a non-existent variable name."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "State", "data_type": "uint8"}
    ])
    enums_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "GhostState", "value": 0, "label": "IDLE"}
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df, "Enums": enums_df})
    with pytest.raises(ConfigError, match="unknown variable 'GhostState'"):
        load_config(wb)


def test_err_duplicate_enum_value(make_workbook):
    """User defines value 1 twice for the same signal."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "State", "data_type": "uint8"}
    ])
    enums_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "State", "value": 1, "label": "RUNNING"},
        {"id_or_address": "0x1000", "signal_name": "State", "value": 1, "label": "EXECUTING"},
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df, "Enums": enums_df})
    with pytest.raises(ConfigError, match="duplicate enum value 1 for signal 'State'"):
        load_config(wb)


# ============================================================================
# 5. CALCGROUPS SHEET ERRORS
# ============================================================================

def test_err_calc_group_references_unknown_group(make_workbook):
    """User adds calc group for 'BatteryTemps' but no variable belongs to that group."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "Volt_1", "data_type": "uint16", "group": "Voltages"}
    ])
    calc_df = pd.DataFrame([
        {"group_name": "BatteryTemps", "operations": "min|max", "unit": "°C", "enabled": True}
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df, "CalcGroups": calc_df})
    with pytest.raises(ConfigError, match="unknown group 'BatteryTemps'"):
        load_config(wb)


def test_err_calc_group_unsupported_operation(make_workbook):
    """User asks for 'standard_deviation' or 'variance' which are not supported math stats."""
    vars_df = pd.DataFrame([
        {"id_or_address": "0x1000", "signal_name": "Volt_1", "data_type": "uint16", "group": "Voltages"}
    ])
    calc_df = pd.DataFrame([
        {"group_name": "Voltages", "operations": "min|variance", "unit": "V", "enabled": True}
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "Variables": vars_df, "CalcGroups": calc_df})
    with pytest.raises(ConfigError, match="unsupported stat 'variance'"):
        load_config(wb)


# ============================================================================
# 6. TX COMMANDS & POLLING SCHEDULE ERRORS
# ============================================================================

def test_err_duplicate_tx_command_name(make_workbook):
    """User defines two TX commands with the same command_name."""
    tx_df = pd.DataFrame([
        {"command_name": "Reset_Device", "id_or_address": "0x6000", "enabled": True},
        {"command_name": "Reset_Device", "id_or_address": "0x6001", "enabled": True},
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "TxCommands": tx_df})
    with pytest.raises(ConfigError, match="Duplicate tx_command defined with name 'Reset_Device'"):
        load_config(wb)


def test_err_duplicate_polling_schedule_for_same_id(make_workbook):
    """User defines two polling schedule rows for the exact same target frame ID."""
    poll_df = pd.DataFrame([
        {"id_or_address": "0x1000", "interval_ms": 100, "timeout_ms": 50, "enabled": True},
        {"id_or_address": "0x1000", "interval_ms": 500, "timeout_ms": 50, "enabled": True},
    ])
    wb = make_workbook({"Protocol": valid_protocol_df(), "Frames": valid_frames_df(), "PollingSchedule": poll_df})
    with pytest.raises(ConfigError, match="duplicate polling schedule for ID 0x1000"):
        load_config(wb)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
