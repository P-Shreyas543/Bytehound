"""Pre-built starter protocol templates for Bytehound."""

from __future__ import annotations

from typing import Dict, Any, List

PRESET_SINGLE_CELL_BMS: Dict[str, List[Dict[str, Any]]] = {
    "Protocol": [{
        "profile_name": "Single Cell BMS Protocol",
        "parser_type": "framed",
        "header_hex": "AA 55",
        "frame_id_size": 2,
        "frame_id_byte_order": "little",
        "length_size": 1,
        "length_meaning": "payload_only",
        "length_byte_order": "",
        "crc_type": "crc16_modbus",
        "crc_size": 2,
        "crc_byte_order": "little",
        "crc_coverage": "header_to_payload",
        "footer_hex": "",
        "escape_mode": "none",
        "raw_log_format": "hex",
        "inter_frame_delay_ms": 10,
        "tx_pad_length": 0,
        "modbus_node_address": 1,
        "enabled": True
    }],
    "Frames": [
        {"frame_id": "0x1000", "frame_name": "Cell Telemetry", "payload_length": 8, "direction": "rx", "enabled": True, "description": "Cell voltages and temperatures"},
        {"frame_id": "0x2000", "frame_name": "Board Parameters", "payload_length": 6, "direction": "rx", "enabled": True, "description": "System ambient & auxiliary voltages"},
        {"frame_id": "0x3000", "frame_name": "Algorithm Faults", "payload_length": 2, "direction": "rx", "enabled": True, "description": "System fault flags"},
        {"frame_id": "0x6000", "frame_name": "Cell Relay Control", "payload_length": 1, "direction": "rxtx", "enabled": True, "description": "Relay control flags"}
    ],
    "Variables": [
        {"id_or_address": "0x1000", "signal_name": "CellVoltage", "data_type": "uint16", "count": 1, "byte_order": "little", "scale": 0.001, "offset": 0, "unit": "V", "group": "Cell Data", "read_write": "R", "min_value": 2.5, "max_value": 4.2, "description": "Cell Terminal Voltage", "enabled": True},
        {"id_or_address": "0x1000", "signal_name": "CellCurrent", "data_type": "int16", "count": 1, "byte_order": "little", "scale": 0.001, "offset": 0, "unit": "A", "group": "Cell Data", "read_write": "R", "min_value": -50.0, "max_value": 50.0, "description": "Cell Current Flow", "enabled": True},
        {"id_or_address": "0x1000", "signal_name": "TerminalTemp", "data_type": "int16", "count": 1, "byte_order": "little", "scale": 0.1, "offset": 0, "unit": "C", "group": "Cell Data", "read_write": "R", "min_value": -20.0, "max_value": 80.0, "description": "Terminal Temperature", "enabled": True},
        {"id_or_address": "0x1000", "signal_name": "SurfaceTemp", "data_type": "int16", "count": 1, "byte_order": "little", "scale": 0.1, "offset": 0, "unit": "C", "group": "Cell Data", "read_write": "R", "min_value": -20.0, "max_value": 80.0, "description": "Surface Temperature", "enabled": True},
        {"id_or_address": "0x2000", "signal_name": "AmbientTemp", "data_type": "int16", "count": 1, "byte_order": "little", "scale": 0.1, "offset": 0, "unit": "C", "group": "Board", "read_write": "R", "min_value": -40.0, "max_value": 125.0, "description": "Ambient Temperature", "enabled": True},
        {"id_or_address": "0x2000", "signal_name": "ChargeVoltage", "data_type": "uint16", "count": 1, "byte_order": "little", "scale": 0.001, "offset": 0, "unit": "V", "group": "Board", "read_write": "R", "min_value": 0.0, "max_value": 60.0, "description": "Charger Input Voltage", "enabled": True},
        {"id_or_address": "0x2000", "signal_name": "LoadVoltage", "data_type": "uint16", "count": 1, "byte_order": "little", "scale": 0.001, "offset": 0, "unit": "V", "group": "Board", "read_write": "R", "min_value": 0.0, "max_value": 60.0, "description": "Output Load Voltage", "enabled": True},
        {"id_or_address": "0x3000", "signal_name": "Faults", "data_type": "uint16", "count": 1, "byte_order": "little", "scale": 1, "offset": 0, "unit": "bitfield", "group": "Faults", "read_write": "R", "min_value": 0, "max_value": 65535, "description": "System Fault Flags", "enabled": True},
        {"id_or_address": "0x6000", "signal_name": "Cell Enable", "data_type": "boolean", "count": 1, "byte_order": "little", "scale": 1, "offset": 0, "unit": "bool", "group": "Control", "read_write": "RW", "min_value": 0, "max_value": 1, "description": "Enable Cell Connections", "enabled": True},
        {"id_or_address": "0x6000", "signal_name": "Cell Select", "data_type": "boolean", "count": 1, "byte_order": "little", "scale": 1, "offset": 0, "unit": "bool", "group": "Control", "read_write": "RW", "min_value": 0, "max_value": 1, "description": "Select Active Cell", "enabled": True}
    ],
    "Bitfields": [
        {"id_or_address": "0x3000", "signal_name": "Faults", "bit_index": 0, "label": "Overvoltage Fault", "active_text": "FAULT", "inactive_text": "OK"},
        {"id_or_address": "0x3000", "signal_name": "Faults", "bit_index": 1, "label": "Undervoltage Fault", "active_text": "FAULT", "inactive_text": "OK"},
        {"id_or_address": "0x3000", "signal_name": "Faults", "bit_index": 2, "label": "Overtemperature Fault", "active_text": "FAULT", "inactive_text": "OK"}
    ],
    "Enums": [],
    "CalcGroups": [],
    "TxCommands": [
        {"command_name": "Cell Relay Control", "id_or_address": "0x6000", "payload_hex": "", "description": "Relay Enable and Select Control", "enabled": True}
    ],
    "TxCommandFields": [
        {"command_name": "Cell Relay Control", "signal_name": "Cell Enable", "data_type": "boolean", "byte_order": "little", "scale": 1, "offset": 0, "unit": "bool", "min_value": 0, "max_value": 1, "default": 0},
        {"command_name": "Cell Relay Control", "signal_name": "Cell Select", "data_type": "boolean", "byte_order": "little", "scale": 1, "offset": 0, "unit": "bool", "min_value": 0, "max_value": 1, "default": 0}
    ],
    "PollingSchedule": [],
    "SerialDefaults": [
        {"baud_rate": 115200, "data_bits": 8, "stop_bits": 1, "parity": "N", "timeout_ms": 100}
    ]
}

PRESET_SIMPLE_HEX_TELEMETRY: Dict[str, List[Dict[str, Any]]] = {
    "Protocol": [{
        "profile_name": "Simple Hex Telemetry",
        "parser_type": "framed",
        "header_hex": "AA",
        "frame_id_size": 1,
        "frame_id_byte_order": "little",
        "length_size": 1,
        "length_meaning": "payload_only",
        "length_byte_order": "",
        "crc_type": "crc16_modbus",
        "crc_size": 2,
        "crc_byte_order": "little",
        "crc_coverage": "header_to_payload",
        "footer_hex": "55",
        "escape_mode": "none",
        "raw_log_format": "hex",
        "inter_frame_delay_ms": 5,
        "tx_pad_length": 0,
        "modbus_node_address": 1,
        "enabled": True
    }],
    "Frames": [
        {"frame_id": "0x01", "frame_name": "Sensor Stream", "payload_length": 4, "direction": "rx", "enabled": True, "description": "Raw analog sensor values"}
    ],
    "Variables": [
        {"id_or_address": "0x01", "signal_name": "Sensor1", "data_type": "uint16", "count": 1, "byte_order": "little", "scale": 0.01, "offset": 0, "unit": "mV", "group": "Sensors", "read_write": "R", "min_value": 0, "max_value": 3300, "description": "Sensor 1 Input", "enabled": True},
        {"id_or_address": "0x01", "signal_name": "Sensor2", "data_type": "uint16", "count": 1, "byte_order": "little", "scale": 0.01, "offset": 0, "unit": "mV", "group": "Sensors", "read_write": "R", "min_value": 0, "max_value": 3300, "description": "Sensor 2 Input", "enabled": True}
    ],
    "Bitfields": [], "Enums": [], "CalcGroups": [], "TxCommands": [], "TxCommandFields": [], "PollingSchedule": [],
    "SerialDefaults": [{"baud_rate": 115200, "data_bits": 8, "stop_bits": 1, "parity": "N", "timeout_ms": 100}]
}

PRESET_MODBUS_RTU: Dict[str, List[Dict[str, Any]]] = {
    "Protocol": [{
        "profile_name": "Modbus RTU Standard",
        "parser_type": "modbus_rtu",
        "header_hex": "",
        "frame_id_size": 2,
        "frame_id_byte_order": "big",
        "length_size": 1,
        "length_meaning": "payload_only",
        "length_byte_order": "",
        "crc_type": "crc16_modbus",
        "crc_size": 2,
        "crc_byte_order": "little",
        "crc_coverage": "header_to_payload",
        "footer_hex": "",
        "escape_mode": "none",
        "raw_log_format": "hex",
        "inter_frame_delay_ms": 20,
        "tx_pad_length": 0,
        "modbus_node_address": 1,
        "enabled": True
    }],
    "Frames": [
        {"frame_id": "0x0001", "frame_name": "Input Registers", "payload_length": 4, "direction": "rx", "enabled": True, "description": "Analog Telemetry Registers"}
    ],
    "Variables": [
        {"id_or_address": "0x0001", "signal_name": "BusVoltage", "data_type": "uint16", "count": 1, "byte_order": "big", "scale": 0.1, "offset": 0, "unit": "V", "group": "Power", "read_write": "R", "min_value": 0, "max_value": 500, "description": "Main DC Bus Voltage", "enabled": True},
        {"id_or_address": "0x0001", "signal_name": "BusCurrent", "data_type": "int16", "count": 1, "byte_order": "big", "scale": 0.1, "offset": 0, "unit": "A", "group": "Power", "read_write": "R", "min_value": -100, "max_value": 100, "description": "Main DC Bus Current", "enabled": True}
    ],
    "Bitfields": [], "Enums": [], "CalcGroups": [], "TxCommands": [], "TxCommandFields": [], "PollingSchedule": [],
    "SerialDefaults": [{"baud_rate": 9600, "data_bits": 8, "stop_bits": 1, "parity": "N", "timeout_ms": 200}]
}

BUILTIN_PRESETS: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "Single Cell BMS (Default)": PRESET_SINGLE_CELL_BMS,
    "Simple Hex Telemetry": PRESET_SIMPLE_HEX_TELEMETRY,
    "Modbus RTU Standard": PRESET_MODBUS_RTU,
}
