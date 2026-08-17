import pandas as pd

protocol = pd.DataFrame([{
    'profile_name': 'single cell configuration',
    'header_hex': 'AA 55',
    'frame_id_size': 2,
    'frame_id_byte_order': 'little',
    'length_size': 1,
    'length_meaning': 'payload_only',
    'length_byte_order': '',
    'crc_type': 'crc16_modbus',
    'crc_size': 2,
    'crc_byte_order': 'big',
    'crc_coverage': 'header_to_payload',
    'footer_hex': '',
    'escape_mode': 'none',
    'raw_log_format': 'hex',
    'inter_frame_delay_ms': 10,
    'tx_pad_length': 12,
    'enabled': True
}])

frames = pd.DataFrame([{
    'frame_id': '0x1000',
    'frame_name': 'Single Cell Data',
    'payload_length': 30,
    'direction': 'rx',
    'enabled': True,
    'description': 'Simulink Byte Pack Output'
}])

variables_data = [
    ('CellVoltage', 'uint16', 0.001, 'V'),
    ('CellCurrent', 'int16', 0.001, 'A'),
    ('CellTerminalTemperature', 'int16', 0.001, 'C'),
    ('CellBodyTemperature', 'uint16', 0.001, 'C'),
    ('AmbientTemperature', 'int16', 0.001, 'C'),
    ('ChargeVoltage', 'uint16', 0.001, 'V'),
    ('LoadVoltage', 'uint16', 0.001, 'V'),
    ('OVc', 'uint16', 0.001, ''),
    ('UVc', 'uint16', 0.001, ''),
    ('OCc', 'uint16', 0.001, ''),
    ('OCdc', 'uint16', 0.001, ''),
    ('OTc', 'uint16', 0.001, ''),
    ('UTc', 'uint16', 0.001, ''),
    ('OCV_SOC', 'uint16', 0.01, '%'),
    ('CC_SOC', 'uint16', 0.01, '%'),
]

variables = pd.DataFrame([{
    'id_or_address': '0x1000',
    'signal_name': name,
    'data_type': dtype,
    'count': 1,
    'byte_order': 'little',
    'scale': scale,
    'offset': 0,
    'unit': unit,
    'group': 'Cell Data',
    'read_write': 'R',
    'min_value': None,
    'max_value': None,
    'description': '',
    'enabled': True
} for name, dtype, scale, unit in variables_data])

bitfields = pd.DataFrame(columns=['id_or_address', 'signal_name', 'bit_index', 'label', 'active_text', 'inactive_text'])
enums = pd.DataFrame(columns=['id_or_address', 'signal_name', 'value', 'label'])
calc_groups = pd.DataFrame(columns=['group_name', 'operations', 'unit', 'frame_id', 'enabled'])
tx_commands = pd.DataFrame(columns=['command_name', 'id_or_address', 'payload_hex', 'description', 'enabled'])
tx_command_fields = pd.DataFrame(columns=['command_name', 'signal_name', 'data_type', 'byte_order', 'scale', 'offset', 'unit', 'min_value', 'max_value', 'default'])
polling_schedule = pd.DataFrame(columns=['id_or_address', 'interval_ms', 'timeout_ms', 'enabled'])
serial_defaults = pd.DataFrame([{
    'baud_rate': 115200,
    'data_bits': 8,
    'stop_bits': 1,
    'parity': 'N',
    'timeout_ms': 100
}])

with pd.ExcelWriter('single cell configuration.xlsx') as writer:
    protocol.to_excel(writer, sheet_name='Protocol', index=False)
    frames.to_excel(writer, sheet_name='Frames', index=False)
    variables.to_excel(writer, sheet_name='Variables', index=False)
    bitfields.to_excel(writer, sheet_name='Bitfields', index=False)
    enums.to_excel(writer, sheet_name='Enums', index=False)
    calc_groups.to_excel(writer, sheet_name='CalcGroups', index=False)
    tx_commands.to_excel(writer, sheet_name='TxCommands', index=False)
    tx_command_fields.to_excel(writer, sheet_name='TxCommandFields', index=False)
    polling_schedule.to_excel(writer, sheet_name='PollingSchedule', index=False)
    serial_defaults.to_excel(writer, sheet_name='SerialDefaults', index=False)

print("Created single cell configuration.xlsx successfully.")
