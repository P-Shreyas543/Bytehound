"""Generator script for Ather_v1_0_1.xlsx configuration workbook.

Builds an Excel configuration file from Ather_v1_0_1.dbc and live bus telemetry
with 100% 8-byte payload coverage, user-understandable descriptions, and 2,000,000 baud default.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
from app.decoder.config_loader import load_config

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
    'enabled': True
}])

# 2. Frames defined in Ather DBC + Live Active Bus Telemetry
frames = pd.DataFrame([
    # Standard 14S Cell Voltage Frames (DBC: Series_Vol_*)
    {'frame_id': '0x132', 'frame_name': 'Series_Vol_1_4', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Individual Cell Voltages 1-4 (0.1 mV resolution)'},
    {'frame_id': '0x133', 'frame_name': 'Series_Vol_5_8', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Individual Cell Voltages 5-8 (0.1 mV resolution)'},
    {'frame_id': '0x134', 'frame_name': 'Series_Vol_9_12', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Individual Cell Voltages 9-12 (0.1 mV resolution)'},
    {'frame_id': '0x135', 'frame_name': 'Series_Vol_13_14', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Individual Cell Voltages 13-14 and Auxiliary Sensors'},
    # Thermal Frames (DBC: BT1_3, BT4_6)
    {'frame_id': '0x136', 'frame_name': 'BT1_3', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Battery Pack Thermal Sensors 1, 2, 3'},
    {'frame_id': '0x137', 'frame_name': 'BT4_6', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Battery Pack Thermal Sensors 4, 5, 6'},
    {'frame_id': '0x170', 'frame_name': 'Module_Temperatures', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Internal BMS Module & Power Stage Temperatures'},
    # Pack Telemetry & State (DBC: BC, SOC, Pack_Telemetry)
    {'frame_id': '0x141', 'frame_name': 'Pack_Telemetry', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Live Battery Pack Voltage & Standby Current'},
    {'frame_id': '0x209', 'frame_name': 'SOC', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Battery State of Charge (SOC %)'},
    {'frame_id': '0x147', 'frame_name': 'Pack_Limits', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Live Pack Voltage & Discharge Power Limits'},
    {'frame_id': '0x148', 'frame_name': 'Pack_Charge_Limits', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Live Pack Charge Power & Current Limits'},
    {'frame_id': '0x601', 'frame_name': 'BC', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Battery Current Flow (-0.001 A resolution)'},
    # Vehicle & Auxiliary (DBC: VS, VT, DM, KS)
    {'frame_id': '0x153', 'frame_name': 'Auxiliary_Power', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Auxiliary 12V DC-DC System Rail'},
    {'frame_id': '0x18C', 'frame_name': 'VS', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Vehicle Speed Telemetry (0.1 Kmph)'},
    {'frame_id': '0x28C', 'frame_name': 'VT', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Vehicle Throttle Position (0.006 scale)'},
    {'frame_id': '0x101', 'frame_name': 'DM', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Vehicle Drive Mode State'},
    {'frame_id': '0x205', 'frame_name': 'KS', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Key Switch Ignition State'},
    # Charger (DBC: CS, CC)
    {'frame_id': '0x002', 'frame_name': 'CS', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'EV Charger Connection Status'},
    {'frame_id': '0x003', 'frame_name': 'CC', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'EV Charger Output Current & Voltage'},
    # Advanced Cell Diagnostics (Live Ather Bus Channels)
    {'frame_id': '0x13A', 'frame_name': 'Cell_Resistances_1_4', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Cell Internal Resistances 1-4 (0.1 mOhm)'},
    {'frame_id': '0x13B', 'frame_name': 'Cell_Resistances_5_8', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Cell Internal Resistances 5-8 (0.1 mOhm)'},
    {'frame_id': '0x13C', 'frame_name': 'Cell_Resistances_9_12', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Cell Internal Resistances 9-12 (0.1 mOhm)'},
    {'frame_id': '0x13D', 'frame_name': 'Cell_Resistances_13_14', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Cell Internal Resistances 13-14 (0.1 mOhm)'},
    {'frame_id': '0x14E', 'frame_name': 'Cell_SOC_1_8', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Individual Cell State of Charge 1-8 (%)'},
    {'frame_id': '0x14F', 'frame_name': 'Cell_SOC_9_14', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Individual Cell State of Charge 9-14 (%)'},
    {'frame_id': '0x143', 'frame_name': 'Cell_OCV_1_4', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Cell Open Circuit Voltages 1-4 (mV resolution)'},
    {'frame_id': '0x144', 'frame_name': 'Cell_OCV_5_8', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Cell Open Circuit Voltages 5-8 (mV resolution)'},
    {'frame_id': '0x145', 'frame_name': 'Cell_OCV_9_12', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Cell Open Circuit Voltages 9-12 (mV resolution)'},
    {'frame_id': '0x146', 'frame_name': 'Cell_OCV_13_14', 'payload_length': 8, 'direction': 'rx', 'enabled': True, 'description': 'Cell Open Circuit Voltages 13-14 (mV resolution)'},
])

# 3. Clean, User-Understandable Variables matching Ather DBC with full 8-byte frame coverage
variables_data = [
    # --- 14S Cell Voltages (DBC: Vol1..Vol14, 0.1 mV resolution, group: Cell Voltages) ---
    ('0x132', 'Vol1', 'uint16', 1, 0, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 1 Voltage (Series Vol 1)', True),
    ('0x132', 'Vol2', 'uint16', 1, 2, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 2 Voltage (Series Vol 2)', True),
    ('0x132', 'Vol3', 'uint16', 1, 4, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 3 Voltage (Series Vol 3)', True),
    ('0x132', 'Vol4', 'uint16', 1, 6, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 4 Voltage (Series Vol 4)', True),

    ('0x133', 'Vol5', 'uint16', 1, 0, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 5 Voltage (Series Vol 5)', True),
    ('0x133', 'Vol6', 'uint16', 1, 2, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 6 Voltage (Series Vol 6)', True),
    ('0x133', 'Vol7', 'uint16', 1, 4, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 7 Voltage (Series Vol 7)', True),
    ('0x133', 'Vol8', 'uint16', 1, 6, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 8 Voltage (Series Vol 8)', True),

    ('0x134', 'Vol9', 'uint16', 1, 0, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 9 Voltage (Series Vol 9)', True),
    ('0x134', 'Vol10', 'uint16', 1, 2, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 10 Voltage (Series Vol 10)', True),
    ('0x134', 'Vol11', 'uint16', 1, 4, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 11 Voltage (Series Vol 11)', True),
    ('0x134', 'Vol12', 'uint16', 1, 6, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 12 Voltage (Series Vol 12)', True),

    ('0x135', 'Vol13', 'uint16', 1, 0, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 13 Voltage (Series Vol 13)', True),
    ('0x135', 'Vol14', 'uint16', 1, 2, 'little', 0.0001, 0, 'V', 'Cell Voltages', 2.0, 4.5, 'Cell 14 Voltage (Series Vol 14)', True),
    ('0x135', 'Series_Vol_Aux_1', 'uint16', 1, 4, 'little', 0.01, 0, '°C', 'Diagnostic Channels', -20.0, 80.0, 'Series Voltage Frame Auxiliary Sensor 1', True),
    ('0x135', 'Series_Vol_Aux_2', 'int16', 1, 6, 'little', 0.01, 0, '°C', 'Diagnostic Channels', -50.0, 50.0, 'Series Voltage Frame Auxiliary Sensor 2', True),

    # --- Battery Pack Thermal Sensors (DBC: Battery_Temp_1..Battery_Temp_6, 0.01 °C, group: Battery Temperatures) ---
    ('0x136', 'Battery_Temp_1', 'uint16', 1, 0, 'little', 0.01, 0, '°C', 'Battery Temperatures', -20.0, 80.0, 'Battery Temperature Sensor 1', True),
    ('0x136', 'Battery_Temp_2', 'uint16', 1, 2, 'little', 0.01, 0, '°C', 'Battery Temperatures', -20.0, 80.0, 'Battery Temperature Sensor 2', True),
    ('0x136', 'Battery_Temp_3', 'uint16', 1, 4, 'little', 0.01, 0, '°C', 'Battery Temperatures', -20.0, 80.0, 'Battery Temperature Sensor 3', True),
    ('0x136', 'BT1_3_Reserved', 'uint16', 1, 6, 'little', 0.01, 0, '°C', 'Diagnostic Channels', -20.0, 500.0, 'BT1_3 Reserved Channel / Sensor 2 Physical', True),

    ('0x137', 'BT4_6_Reserved', 'uint16', 1, 0, 'little', 0.01, 0, '°C', 'Diagnostic Channels', -20.0, 500.0, 'BT4_6 Reserved Channel', True),
    ('0x137', 'Battery_Temp_4', 'uint16', 1, 2, 'little', 0.01, 0, '°C', 'Battery Temperatures', -20.0, 80.0, 'Battery Temperature Sensor 4', True),
    ('0x137', 'Battery_Temp_5', 'uint16', 1, 4, 'little', 0.01, 0, '°C', 'Battery Temperatures', -20.0, 80.0, 'Battery Temperature Sensor 5', True),
    ('0x137', 'Battery_Temp_6', 'uint16', 1, 6, 'little', 0.01, 0, '°C', 'Battery Temperatures', -20.0, 80.0, 'Battery Temperature Sensor 6', True),

    # --- Internal BMS Module & Power Stage Temperatures ---
    ('0x170', 'Module_Temperature_1', 'uint16', 1, 0, 'little', 0.01, 0, '°C', 'Module Temperatures', -20.0, 100.0, 'BMS Module Temperature Sensor 1', True),
    ('0x170', 'Module_Temperature_2', 'uint16', 1, 2, 'little', 0.01, 0, '°C', 'Module Temperatures', -20.0, 100.0, 'BMS Module Temperature Sensor 2', True),
    ('0x170', 'Module_Temperature_3', 'uint16', 1, 4, 'little', 0.01, 0, '°C', 'Module Temperatures', -20.0, 100.0, 'BMS Module Temperature Sensor 3', True),
    ('0x170', 'Power_Stage_Temperature', 'uint16', 1, 6, 'little', 0.01, 0, '°C', 'Module Temperatures', -20.0, 100.0, 'Power Stage MOSFET Temperature', True),

    # --- Pack Telemetry & High Resolution Current (DBC: BC Battery_Current) ---
    ('0x141', 'Pack_Voltage', 'uint16', 1, 0, 'little', 0.01, 0, 'V', 'Pack Parameters', 0.0, 60.0, 'Total Battery Pack Voltage', True),
    ('0x141', 'Pack_Current', 'int16', 1, 2, 'little', 0.01, 0, 'A', 'Pack Parameters', -100.0, 100.0, 'Battery Pack Standby / Live Current', True),
    ('0x141', 'Pack_Telemetry_Status', 'uint32', 1, 4, 'little', 1.0, 0, '', 'Pack Parameters', 0, 4294967295, 'Pack Telemetry Status Word', True),

    ('0x601', 'Battery_Current', 'int32', 1, 0, 'little', -0.001, 0, 'A', 'Pack Parameters', -200.0, 200.0, 'Battery Current Flow (DBC BC: -0.001 A resolution)', True),
    ('0x601', 'BC_Status', 'uint32', 1, 4, 'little', 1.0, 0, '', 'Pack Parameters', 0, 4294967295, 'Battery Current Status Flags', True),

    # --- Battery State of Charge (DBC: SOC Battery_SOC) ---
    ('0x209', 'SOC_Algorithm_State', 'uint32', 1, 0, 'little', 1.0, 0, '', 'Pack Parameters', 0, 4294967295, 'Battery SOC Algorithm State Word', True),
    ('0x209', 'Battery_SOC', 'uint8', 1, 4, 'little', 1.0, 0, '%', 'Pack Parameters', 0.0, 100.0, 'Battery State of Charge (%)', True),
    ('0x209', 'SOC_Diagnostic_Word', 'uint16', 1, 5, 'little', 1.0, 0, '', 'Pack Parameters', 0, 65535, 'Battery SOC Diagnostic Word', True),
    ('0x209', 'SOC_Quality_Flag', 'uint8', 1, 7, 'little', 1.0, 0, '', 'Pack Parameters', 0, 255, 'Battery SOC Quality Flag', True),

    # --- Pack Limits ---
    ('0x147', 'Pack_Status_Header', 'uint32', 1, 0, 'little', 1.0, 0, '', 'Pack Parameters', 0, 4294967295, 'Pack Limits Header Word', True),
    ('0x147', 'Pack_Voltage_Threshold', 'uint16', 1, 4, 'little', 0.01, 0, 'V', 'Pack Parameters', 0.0, 60.0, 'Pack Voltage Upper Threshold', True),
    ('0x147', 'Discharge_Power_Limit', 'uint16', 1, 6, 'little', 1.0, 0, 'W', 'Pack Parameters', 0.0, 10000.0, 'Discharge Power Limit', True),

    ('0x148', 'Pack_Charge_Header', 'uint32', 1, 0, 'little', 1.0, 0, '', 'Pack Parameters', 0, 4294967295, 'Pack Charge Status Header', True),
    ('0x148', 'Pack_Current_Limit', 'uint16', 1, 4, 'little', 1.0, 0, 'A', 'Pack Parameters', 0.0, 150.0, 'Pack Current Limit', True),
    ('0x148', 'Charge_Power_Limit', 'uint16', 1, 6, 'little', 1.0, 0, 'W', 'Pack Parameters', 0.0, 10000.0, 'Charge Power Limit', True),

    # --- Vehicle & Auxiliary Parameters (DBC: VS, VT, DM, KS, Aux) ---
    ('0x153', 'Auxiliary_Power_Status', 'uint16', 1, 0, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 65535, 'Auxiliary Power Status Word', True),
    ('0x153', 'Auxiliary_12V_Voltage', 'uint16', 1, 2, 'little', 0.001, 0, 'V', 'Vehicle Parameters', 0.0, 16.0, 'Auxiliary 12V DC-DC System Rail', True),
    ('0x153', 'Pack_Overvoltage_Threshold', 'uint16', 1, 4, 'little', 0.01, 0, 'V', 'Pack Parameters', 0.0, 60.0, 'Pack Overvoltage Protection Threshold', True),
    ('0x153', 'Pack_Undervoltage_Threshold', 'uint16', 1, 6, 'little', 0.01, 0, 'V', 'Pack Parameters', 0.0, 60.0, 'Pack Undervoltage Protection Threshold', True),

    ('0x18C', 'VS_Status', 'uint8', 1, 0, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 255, 'Vehicle Speed Status Byte', True),
    ('0x18C', 'Vehicle_Speed', 'int16', 1, 1, 'little', 0.1, 0, 'km/h', 'Vehicle Parameters', 0.0, 150.0, 'Vehicle Speed (DBC VS: 0.1 Kmph)', True),
    ('0x18C', 'Motor_RPM', 'uint16', 1, 3, 'little', 1.0, 0, 'RPM', 'Vehicle Parameters', 0, 15000, 'Traction Motor Speed', True),
    ('0x18C', 'Vehicle_Status_Flags', 'uint8', 1, 5, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 255, 'Vehicle Status Flags', True),
    ('0x18C', 'Odometer_Reading', 'uint16', 1, 6, 'little', 1.0, 0, 'km', 'Vehicle Parameters', 0, 65535, 'Vehicle Odometer Reading', True),

    ('0x28C', 'VT_Status', 'uint16', 1, 0, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 65535, 'Throttle Controller Status', True),
    ('0x28C', 'Throttle_Sensor_Offset', 'uint8', 1, 2, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 255, 'Throttle Sensor Offset', True),
    ('0x28C', 'Throttle_2', 'uint16', 1, 3, 'little', 0.006, 0, '%', 'Vehicle Parameters', 0.0, 100.0, 'Vehicle Throttle Position (DBC VT: 0.006 scale)', True),
    ('0x28C', 'Throttle_Diagnostic_Code', 'uint16', 1, 5, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 65535, 'Throttle Diagnostic Code', True),
    ('0x28C', 'Throttle_Subsystem_Flag', 'uint8', 1, 7, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 255, 'Throttle Subsystem Flag', True),

    ('0x101', 'Drive_Mode', 'boolean', 1, 0, 'little', 1, 0, 'bool', 'Vehicle Parameters', 0, 1, 'Vehicle Drive Mode (DBC DM: 1=DRIVE, 0=STANDBY)', True),
    ('0x101', 'DM_Controller_Status', 'uint32', 1, 1, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 4294967295, 'Drive Controller Status Word', True),
    ('0x101', 'DM_Subsystem_State', 'uint16', 1, 5, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 65535, 'Drive Subsystem State', True),
    ('0x101', 'DM_Diagnostic_Byte', 'uint8', 1, 7, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 255, 'Drive Diagnostic Byte', True),

    ('0x205', 'Key_Switch', 'boolean', 1, 0, 'little', 1, 0, 'bool', 'Vehicle Parameters', 0, 1, 'Ignition Key Switch (DBC KS: 1=ON, 0=OFF)', True),
    ('0x205', 'KS_Controller_Word', 'uint32', 1, 1, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 4294967295, 'Key Switch Controller Word', True),
    ('0x205', 'KS_Subsystem_State', 'uint16', 1, 5, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 65535, 'Key Switch Subsystem State', True),
    ('0x205', 'KS_Diagnostic_Byte', 'uint8', 1, 7, 'little', 1.0, 0, '', 'Vehicle Parameters', 0, 255, 'Key Switch Diagnostic Byte', True),

    # --- Charger (DBC: CS, CC) ---
    ('0x002', 'Charger_Status', 'uint8', 1, 0, 'little', 1.0, 0, '', 'Charger', 0, 255, 'Charger Connection Status', True),
    ('0x002', 'CS_Extended', 'uint32', 1, 1, 'little', 1.0, 0, '', 'Charger', 0, 4294967295, 'Charger Status Extended', True),
    ('0x002', 'CS_Hardware_Flags', 'uint16', 1, 5, 'little', 1.0, 0, '', 'Charger', 0, 65535, 'Charger Hardware Flags', True),
    ('0x002', 'CS_Diagnostic_Code', 'uint8', 1, 7, 'little', 1.0, 0, '', 'Charger', 0, 255, 'Charger Diagnostic Code', True),

    ('0x003', 'CC_Prefix', 'uint32', 1, 0, 'little', 1.0, 0, '', 'Charger', 0, 4294967295, 'Charger Current Prefix', True),
    ('0x003', 'Charger_Current', 'uint16', 1, 4, 'little', 0.001, 0, 'A', 'Charger', 0.0, 50.0, 'Charger Output Current (DBC CC)', True),
    ('0x003', 'Charger_Voltage', 'uint16', 1, 6, 'little', 0.01, 0, 'V', 'Charger', 0.0, 100.0, 'Charger Output Voltage', True),

    # --- Cell Internal Resistances (0.1 mOhm resolution) ---
    ('0x13A', 'Cell_1_Resistance', 'uint16', 1, 0, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 1 Internal Resistance', True),
    ('0x13A', 'Cell_2_Resistance', 'uint16', 1, 2, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 2 Internal Resistance', True),
    ('0x13A', 'Cell_3_Resistance', 'uint16', 1, 4, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 3 Internal Resistance', True),
    ('0x13A', 'Cell_4_Resistance', 'uint16', 1, 6, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 4 Internal Resistance', True),

    ('0x13B', 'Cell_5_Resistance', 'uint16', 1, 0, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 5 Internal Resistance', True),
    ('0x13B', 'Cell_6_Resistance', 'uint16', 1, 2, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 6 Internal Resistance', True),
    ('0x13B', 'Cell_7_Resistance', 'uint16', 1, 4, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 7 Internal Resistance', True),
    ('0x13B', 'Cell_8_Resistance', 'uint16', 1, 6, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 8 Internal Resistance', True),

    ('0x13C', 'Cell_9_Resistance', 'uint16', 1, 0, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 9 Internal Resistance', True),
    ('0x13C', 'Cell_10_Resistance', 'uint16', 1, 2, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 10 Internal Resistance', True),
    ('0x13C', 'Cell_11_Resistance', 'uint16', 1, 4, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 11 Internal Resistance', True),
    ('0x13C', 'Cell_12_Resistance', 'uint16', 1, 6, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 12 Internal Resistance', True),

    ('0x13D', 'Cell_13_Resistance', 'uint16', 1, 0, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 13 Internal Resistance', True),
    ('0x13D', 'Cell_14_Resistance', 'uint16', 1, 2, 'little', 0.1, 0, 'mOhm', 'Cell Internal Resistances', 0.0, 100.0, 'Cell 14 Internal Resistance', True),
    ('0x13D', 'Diagnostic_Active_Count', 'uint16', 1, 4, 'little', 1.0, 0, '', 'Diagnostic Channels', 0, 65535, 'Cell Diagnostic Active Count', True),
    ('0x13D', 'Diagnostic_Flags', 'uint16', 1, 6, 'little', 1.0, 0, '', 'Diagnostic Channels', 0, 65535, 'Cell Diagnostic Flags', True),

    # --- Cell Open Circuit Voltages (mV resolution -> V) ---
    ('0x143', 'Cell_1_OCV', 'uint16', 1, 0, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 1 Open Circuit Voltage', True),
    ('0x143', 'Cell_2_OCV', 'uint16', 1, 2, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 2 Open Circuit Voltage', True),
    ('0x143', 'Cell_3_OCV', 'uint16', 1, 4, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 3 Open Circuit Voltage', True),
    ('0x143', 'Cell_4_OCV', 'uint16', 1, 6, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 4 Open Circuit Voltage', True),

    ('0x144', 'Cell_5_OCV', 'uint16', 1, 0, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 5 Open Circuit Voltage', True),
    ('0x144', 'Cell_6_OCV', 'uint16', 1, 2, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 6 Open Circuit Voltage', True),
    ('0x144', 'Cell_7_OCV', 'uint16', 1, 4, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 7 Open Circuit Voltage', True),
    ('0x144', 'Cell_8_OCV', 'uint16', 1, 6, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 8 Open Circuit Voltage', True),

    ('0x145', 'Cell_9_OCV', 'uint16', 1, 0, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 9 Open Circuit Voltage', True),
    ('0x145', 'Cell_10_OCV', 'uint16', 1, 2, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 10 Open Circuit Voltage', True),
    ('0x145', 'Cell_11_OCV', 'uint16', 1, 4, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 11 Open Circuit Voltage', True),
    ('0x145', 'Cell_12_OCV', 'uint16', 1, 6, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 12 Open Circuit Voltage', True),

    ('0x146', 'Cell_13_OCV', 'uint16', 1, 0, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 13 Open Circuit Voltage', True),
    ('0x146', 'Cell_14_OCV', 'uint16', 1, 2, 'little', 0.001, 0, 'V', 'Cell Open Circuit Voltages', 2.0, 4.5, 'Cell 14 Open Circuit Voltage', True),
    ('0x146', 'Cell_OCV_Diagnostic_Word', 'uint32', 1, 4, 'little', 1.0, 0, '', 'Cell Open Circuit Voltages', 0, 4294967295, 'Cell OCV Diagnostic Flags', True),

    # --- Individual Cell State of Charge (0-100 %) ---
    ('0x14E', 'Cell_1_SOC', 'uint8', 1, 0, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 1 State of Charge', True),
    ('0x14E', 'Cell_2_SOC', 'uint8', 1, 1, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 2 State of Charge', True),
    ('0x14E', 'Cell_3_SOC', 'uint8', 1, 2, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 3 State of Charge', True),
    ('0x14E', 'Cell_4_SOC', 'uint8', 1, 3, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 4 State of Charge', True),
    ('0x14E', 'Cell_5_SOC', 'uint8', 1, 4, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 5 State of Charge', True),
    ('0x14E', 'Cell_6_SOC', 'uint8', 1, 5, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 6 State of Charge', True),
    ('0x14E', 'Cell_7_SOC', 'uint8', 1, 6, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 7 State of Charge', True),
    ('0x14E', 'Cell_8_SOC', 'uint8', 1, 7, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 8 State of Charge', True),

    ('0x14F', 'Cell_9_SOC', 'uint8', 1, 0, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 9 State of Charge', True),
    ('0x14F', 'Cell_10_SOC', 'uint8', 1, 1, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 10 State of Charge', True),
    ('0x14F', 'Cell_11_SOC', 'uint8', 1, 2, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 11 State of Charge', True),
    ('0x14F', 'Cell_12_SOC', 'uint8', 1, 3, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 12 State of Charge', True),
    ('0x14F', 'Cell_13_SOC', 'uint8', 1, 4, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 13 State of Charge', True),
    ('0x14F', 'Cell_14_SOC', 'uint8', 1, 5, 'little', 1.0, 0, '%', 'Cell State of Charge', 0.0, 100.0, 'Cell 14 State of Charge', True),
    ('0x14F', 'Cell_SOC_Status_Word', 'uint16', 1, 6, 'little', 1.0, 0, '', 'Cell State of Charge', 0, 65535, 'Cell SOC Diagnostic Status Word', True),
]

variables = pd.DataFrame([{
    'id_or_address': item[0],
    'signal_name': item[1],
    'data_type': item[2],
    'count': item[3],
    'start_byte': item[4],
    'byte_order': item[5],
    'scale': item[6],
    'offset': item[7],
    'unit': item[8],
    'group': item[9],
    'read_write': 'R',
    'min_value': item[10],
    'max_value': item[11],
    'description': item[12],
    'enabled': item[13],
    'bit_index': 4 if item[1] == 'Key_Switch' else (0 if item[1] == 'Drive_Mode' else None)
} for item in variables_data])

# 4. Calculation Groups (Pack Analytics & Mathematical Aggregations)
calc_groups = pd.DataFrame([
    {'group_name': 'Cell Voltages', 'operations': 'min|max|diff|avg|sum', 'unit': 'V', 'frame_id': None, 'enabled': True},
    {'group_name': 'Battery Temperatures', 'operations': 'min|max|diff|avg', 'unit': '°C', 'frame_id': None, 'enabled': True},
    {'group_name': 'Module Temperatures', 'operations': 'min|max|diff|avg', 'unit': '°C', 'frame_id': None, 'enabled': True},
    {'group_name': 'Cell Internal Resistances', 'operations': 'min|max|diff|avg', 'unit': 'mOhm', 'frame_id': None, 'enabled': True},
    {'group_name': 'Cell Open Circuit Voltages', 'operations': 'min|max|diff|avg', 'unit': 'V', 'frame_id': None, 'enabled': True},
    {'group_name': 'Cell State of Charge', 'operations': 'min|max|diff|avg', 'unit': '%', 'frame_id': None, 'enabled': True},
])

# 5. Serial Defaults (COM10 2,000,000 baud)
serial_defaults = pd.DataFrame([{
    'baud_rate': 2000000,
    'data_bits': 8,
    'stop_bits': 1,
    'parity': 'N',
    'timeout_ms': 100
}])

# 6. Bitfields
bitfields = pd.DataFrame([
    {'id_or_address': '0x205', 'signal_name': 'Key_Switch', 'bit_index': 4, 'label': 'Key Switch ON', 'active_text': 'ON', 'inactive_text': 'OFF'},
    {'id_or_address': '0x101', 'signal_name': 'Drive_Mode', 'bit_index': 0, 'label': 'Drive Mode Active', 'active_text': 'DRIVE', 'inactive_text': 'STANDBY'}
])

# 7. Additional Schema Sheets
enums = pd.DataFrame(columns=['id_or_address', 'signal_name', 'value', 'label'])
tx_commands = pd.DataFrame(columns=['command_name', 'id_or_address', 'payload_hex', 'description', 'enabled'])
tx_command_fields = pd.DataFrame(columns=['command_name', 'signal_name', 'data_type', 'byte_order', 'scale', 'offset', 'unit', 'min_value', 'max_value', 'default'])
polling_schedule = pd.DataFrame(columns=['id_or_address', 'interval_ms', 'timeout_ms', 'enabled'])

def generate_excel():
    excel_path = Path("Ather_v1_0_1.xlsx")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
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
    
    print(f"Generated {excel_path.name} successfully.")
    cfg = load_config(excel_path)
    print(f"Validation successful: Loaded {len(cfg.frames)} frames and {len(cfg.all_signals)} clean signals.")
    print(f"Default baud rate: {cfg.serial_defaults.baud_rate}")

if __name__ == "__main__":
    generate_excel()
