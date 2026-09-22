"""Generator script for Ather_v1_0_1.xlsx configuration workbook.

Builds an Excel configuration file directly and strictly from Ather_v1_0_1.dbc:
- Exactly the 14 CAN messages and signals defined in the DBC
- Bit-accurate start_byte, bit_index, bit_length, scale, offset, and units
- Automatic calculations for Cell Voltages and Battery Temperatures
- Clean Waveshare CAN 20-byte framing at 2,000,000 baud
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import cantools
from app.decoder.config_loader import load_config

ROOT = Path(__file__).resolve().parent
DBC_PATH = ROOT / "Ather_v1_0_1.dbc"
EXCEL_PATH = ROOT / "Ather_v1_0_1.xlsx"


def generate_excel():
    print(f"Loading DBC: {DBC_PATH.resolve()}")
    db = cantools.database.load_file(str(DBC_PATH))

    # 1. Protocol Sheet (Waveshare CAN 20-byte fixed framing)
    protocol = pd.DataFrame([{
        'profile_name': 'Ather Energy CAN (Fixed 20-Byte)',
        'parser_type': 'waveshare_can_20_bytes',
        'header_hex': 'AA 55',
        'frame_id_size': 4,
        'frame_id_byte_order': 'little',
        'length_size': 1,
        'length_meaning': 'payload_only',
        'crc_type': 'none',
        'crc_size': 0,
        'crc_byte_order': 'little',
        'crc_coverage': 'header_to_payload',
        'footer_hex': '',
        'escape_mode': 'none',
        'raw_log_format': 'hex',
        'inter_frame_delay_ms': 10,
        'tx_pad_length': 0,
        'enabled': True,
    }])

    # 2. Frames Sheet (Exactly the 14 real CAN messages from DBC)
    frame_rows = []
    variables_rows = []

    descriptions_map = {
        'BC': 'Battery Current Flow (-0.001 A resolution)',
        'VS': 'Vehicle Speed Telemetry (0.1 km/h resolution)',
        'MR': 'Motor Speed Telemetry (1 RPM resolution)',
        'VT': 'Vehicle Throttle Position (0.006 scale)',
        'Series_Vol_1_4': 'Individual Cell Voltages 1-4 (0.1 mV resolution)',
        'Series_Vol_5_8': 'Individual Cell Voltages 5-8 (0.1 mV resolution)',
        'Series_Vol_9_12': 'Individual Cell Voltages 9-12 (0.1 mV resolution)',
        'Series_Vol_13_14': 'Individual Cell Voltages 13-14 (0.1 mV resolution)',
        'BT1_3': 'Battery Pack Thermal Sensors 1 & 2 (0.01 °C resolution)',
        'BT4_6': 'Battery Pack Thermal Sensors 3 & 4 (0.01 °C resolution)',
        'DM': 'Vehicle Drive Mode & Key Switch State (0x101)',
        'CS': 'EV Charger Connection Status (0x102)',
        'PCL': 'EV Charge Power Upper Limit (0x148)',
        'SOC': 'Battery State of Charge (%) (0x209)',
    }

    # Iterate messages in DBC order
    for msg in db.messages:
        if msg.frame_id >= 0x80000000:
            # Skip Vector independent unassigned signal container
            continue

        fid_hex = f"0x{msg.frame_id:03X}"
        frame_desc = descriptions_map.get(msg.name, f"{msg.name} Frame")
        frame_rows.append({
            'frame_id': fid_hex,
            'frame_name': msg.name,
            'payload_length': msg.length,
            'direction': 'rx',
            'enabled': True,
            'description': frame_desc,
        })

        for sig in msg.signals:
            # Determine data type
            if sig.length == 1:
                dtype = 'boolean'
            elif sig.length <= 8:
                dtype = 'int8' if sig.is_signed else 'uint8'
            elif sig.length <= 16:
                dtype = 'int16' if sig.is_signed else 'uint16'
            elif sig.length <= 32:
                dtype = 'int32' if sig.is_signed else 'uint32'
            else:
                dtype = 'uint64'

            # Byte and bit positioning
            start_byte = sig.start // 8
            bit_idx = sig.start % 8 if (sig.length == 1 or sig.length not in (8, 16, 32, 64)) else None
            bit_len = sig.length if (sig.length not in (8, 16, 32, 64) and sig.length > 1) else None

            # Clean units
            unit = ""
            if sig.unit:
                u_str = sig.unit.strip()
                if u_str.lower() in ("deg c", "degc", "deg_c"):
                    unit = "°C"
                elif u_str.lower() == "kmph":
                    unit = "km/h"
                else:
                    unit = u_str

            # Group assignment
            if sig.name.startswith("Vol"):
                group = "Cell Voltages"
            elif sig.name.startswith("Battery_Temp"):
                group = "Battery Temperatures"
            elif sig.name in ("Battery_Current", "Battery_SOC"):
                group = "Pack Parameters"
            elif sig.name in ("Vehicle_Speed", "Motor_RPM", "Throttle_2", "Key_Switch", "Drive_Mode", "Side_Stand"):
                group = "Vehicle Parameters"
            elif sig.name.startswith("Charger") or sig.name.startswith("Charge"):
                group = "Charger"
            else:
                group = "General"

            # Min/Max sanity ranges
            min_val = None
            max_val = None
            if group == "Cell Voltages":
                min_val, max_val = 2.0, 4.5
            elif group == "Battery Temperatures":
                min_val, max_val = -20.0, 80.0
            elif sig.name == "Battery_Current":
                min_val, max_val = -200.0, 200.0
            elif sig.name == "Vehicle_Speed":
                min_val, max_val = 0.0, 150.0
            elif sig.name == "Motor_RPM":
                min_val, max_val = 0.0, 12000.0
            elif sig.name == "Throttle_2":
                min_val, max_val = 0.0, 100.0
            elif sig.name == "Battery_SOC":
                min_val, max_val = 0.0, 100.0
            elif sig.name in ("Charge_Power_Limit", "Discharge_Power_Limit"):
                min_val, max_val = 0.0, 10000.0
            elif dtype == "boolean":
                min_val, max_val = 0, 1

            signal_desc_map = {
                'Vehicle_Speed': 'Vehicle Speed Telemetry (km/h)',
                'Motor_RPM': 'Electric Motor Rotational Speed (RPM)',
                'Throttle_2': 'Vehicle Throttle Position (%)',
                'Key_Switch': 'Ignition Key Switch State (1=ON, 0=OFF)',
                'Drive_Mode': 'Vehicle Drive Mode State (1=DRIVE, 0=STANDBY)',
                'Side_Stand': 'Vehicle Side Stand State (1=DOWN / Deployed, 0=UP / Retracted)',
                'Battery_SOC': 'Battery State of Charge (%)',
                'Battery_Current': 'Battery Pack Current Flow (-Discharge / +Charge)',
                'Charger_Status': 'EV Charger Connection Status (1=Charging, 0=Disconnected)',
                'Charge_Power_Limit': 'EV Charge Power Upper Limit (W)',
                'Discharge_Power_Limit': 'EV Discharge Power Upper Limit (W)',
                'Battery_Temp_1': 'Battery Pack Temperature Sensor 1 (°C)',
                'Battery_Temp_2': 'Battery Pack Temperature Sensor 2 (°C)',
                'Battery_Temp_3': 'Battery Pack Temperature Sensor 3 (°C)',
                'Battery_Temp_4': 'Battery Pack Temperature Sensor 4 (°C)',
                'Battery_Temp_5': 'Battery Pack Temperature Sensor 5 (°C)',
                'Battery_Temp_6': 'Battery Pack Temperature Sensor 6 (°C)',
            }
            for i in range(1, 15):
                signal_desc_map[f'Vol{i}'] = f'Series Cell {i} Voltage (0.1 mV resolution)'

            desc = sig.comment or signal_desc_map.get(sig.name, f"{sig.name.replace('_', ' ')}")

            variables_rows.append({
                'id_or_address': fid_hex,
                'signal_name': sig.name,
                'data_type': dtype,
                'count': 1,
                'start_byte': start_byte,
                'byte_order': 'little' if sig.byte_order == 'little_endian' else 'big',
                'scale': sig.scale,
                'offset': sig.offset,
                'unit': unit,
                'group': group,
                'read_write': 'R',
                'min_value': min_val,
                'max_value': max_val,
                'description': desc,
                'enabled': True,
                'bit_index': bit_idx,
                'bit_length': bit_len,
            })

    frames = pd.DataFrame(frame_rows)
    variables = pd.DataFrame(variables_rows)

    # 3. Calculation Groups (Cell Voltages & Temperatures)
    calc_groups = pd.DataFrame([
        {'group_name': 'Cell Voltages', 'operations': 'min|max|diff|avg|sum', 'unit': 'V', 'frame_id': None, 'enabled': True},
        {'group_name': 'Battery Temperatures', 'operations': 'min|max|diff|avg', 'unit': '°C', 'frame_id': None, 'enabled': True},
    ])

    # 4. Serial Defaults (2,000,000 baud default)
    serial_defaults = pd.DataFrame([{
        'baud_rate': 2000000,
        'data_bits': 8,
        'stop_bits': 1,
        'parity': 'N',
        'timeout_ms': 100,
    }])

    # 5. Bitfields
    bitfields = pd.DataFrame([
        {'id_or_address': '0x101', 'signal_name': 'Key_Switch', 'bit_index': 1, 'label': 'Key Switch ON', 'active_text': 'ON', 'inactive_text': 'OFF'},
        {'id_or_address': '0x101', 'signal_name': 'Drive_Mode', 'bit_index': 0, 'label': 'Drive Mode Active', 'active_text': 'DRIVE', 'inactive_text': 'STANDBY'},
        {'id_or_address': '0x102', 'signal_name': 'Side_Stand', 'bit_index': 0, 'label': 'Side Stand Down', 'active_text': 'DOWN', 'inactive_text': 'UP'},
    ])

    # 6. Additional Schema Sheets
    enums = pd.DataFrame([
        {'id_or_address': '0x102', 'signal_name': 'Charger_Status', 'value': 1, 'label': 'Charging'},
        {'id_or_address': '0x102', 'signal_name': 'Charger_Status', 'value': 0, 'label': 'Disconnected'},
        {'id_or_address': '0x102', 'signal_name': 'Side_Stand', 'value': 1, 'label': 'DOWN (Deployed)'},
        {'id_or_address': '0x102', 'signal_name': 'Side_Stand', 'value': 0, 'label': 'UP (Retracted)'},
    ])
    tx_commands = pd.DataFrame(columns=['command_name', 'id_or_address', 'payload_hex', 'description', 'enabled'])
    tx_command_fields = pd.DataFrame(columns=['command_name', 'signal_name', 'data_type', 'byte_order', 'scale', 'offset', 'unit', 'min_value', 'max_value', 'default'])
    polling_schedule = pd.DataFrame(columns=['id_or_address', 'interval_ms', 'timeout_ms', 'enabled'])

    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        protocol.to_excel(writer, sheet_name="protocol", index=False)
        frames.to_excel(writer, sheet_name="frames", index=False)
        variables.to_excel(writer, sheet_name="variables", index=False)
        calc_groups.to_excel(writer, sheet_name="calc_groups", index=False)
        serial_defaults.to_excel(writer, sheet_name="serial_defaults", index=False)
        bitfields.to_excel(writer, sheet_name="bitfields", index=False)
        enums.to_excel(writer, sheet_name="enums", index=False)
        tx_commands.to_excel(writer, sheet_name="tx_commands", index=False)
        tx_command_fields.to_excel(writer, sheet_name="tx_command_fields", index=False)
        polling_schedule.to_excel(writer, sheet_name="polling_schedule", index=False)

    print(f"Generated {EXCEL_PATH.name} successfully from {DBC_PATH.name}.")
    cfg = load_config(EXCEL_PATH)
    print(f"Validation successful: Loaded {len(cfg.frames)} DBC frames and {len(cfg.all_signals)} signals.")
    for fid, name in sorted(cfg.frame_names.items()):
        sigs = [s.signal_name for s in cfg.signals_by_frame.get(fid, [])]
        print(f"  0x{fid:03X} ({name:<16}): {', '.join(sigs)}")


if __name__ == "__main__":
    generate_excel()
