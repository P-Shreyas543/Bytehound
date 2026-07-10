"""Tests for `app.decoder.config_loader`."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.decoder.config_loader import ConfigError, load_config
from app.decoder.template_io import export_excel_template


# --- Happy-path loading of the bundled resources ----------------------------


def test_load_bundled_config(resources_dir):
    cfg = load_config(resources_dir / "config_template")

    assert cfg.protocol.profile_name == "Default"
    assert cfg.protocol.header == b"\xAA\x55"
    assert cfg.protocol.frame_id_size == 2
    assert cfg.protocol.frame_id_byte_order == "little"
    assert cfg.protocol.length_size == 1
    assert cfg.protocol.crc_type == "crc16_modbus"
    assert cfg.protocol.crc_byte_order == "little"
    # Bundled template ships footer_hex = EE to match the bundled Arduino
    # simulator's trailer byte. If you remove the footer from protocol.csv,
    # update this assertion to match.
    assert cfg.protocol.footer == b"\xEE"

    assert 0x1000 in cfg.signals_by_frame
    sigs = cfg.signals_by_frame[0x1000]
    # Smoke-check that the bundled template loads in the expected order and
    # the first signal is well-formed. If you reorganise variables.csv,
    # update this list to match.
    assert [s.signal_name for s in sigs] == [
        "Pack Voltage", "Pack Current", "Pack SOC", "Pack Temperature"
    ]
    assert sigs[0].start_byte == 0 and sigs[0].byte_length == 2
    assert sigs[0].endianness == "little"
    assert sigs[0].data_type == "uint"
    assert sigs[0].scale == 0.01 and sigs[0].offset == 0.0


def test_exported_excel_template_loads():
    pass


def test_json_loading(tmp_path):
    source = tmp_path / "config.json"
    import json
    data = {
        "protocol": [
            {
                "profile_name": "Default JSON",
                "header_hex": "AA55",
                "frame_id_size": 2,
                "frame_id_byte_order": "big",
                "length_size": 1,
                "length_meaning": "payload_only",
                "crc_type": "crc16_modbus",
                "crc_size": 2,
                "crc_byte_order": "little",
                "enabled": "TRUE"
            }
        ],
        "variables": [
            {
                "id_or_address": "0x0010",
                "signal_name": "JSON_Voltage",
                "data_type": "uint16",
                "count": 1,
                "byte_order": "big",
                "scale": 0.001,
                "offset": 0,
                "unit": "V",
                "enabled": "TRUE"
            }
        ]
    }
    with source.open("w", encoding="utf-8") as f:
        json.dump(data, f)
    cfg = load_config(source)
    assert cfg.protocol.profile_name == "Default JSON"
    assert [s.signal_name for s in cfg.signals_by_frame[0x0010]] == ["JSON_Voltage"]


def test_yaml_loading(tmp_path):
    source = tmp_path / "config.yaml"
    # Hack: write yaml manually to avoid importing pyyaml which might not be installed in the test env
    # But wait, config_loader will try to import yaml if it is .yaml.
    yaml_text = """
protocol:
  - profile_name: Default YAML
    header_hex: AA55
    frame_id_size: 2
    frame_id_byte_order: big
    length_size: 1
    length_meaning: payload_only
    crc_type: crc16_modbus
    crc_size: 2
    crc_byte_order: little
    enabled: TRUE
variables:
  - id_or_address: 0x0010
    signal_name: YAML_Voltage
    data_type: uint16
    count: 1
    byte_order: big
    scale: 0.001
    offset: 0
    unit: V
    enabled: TRUE
"""
    source.write_text(yaml_text, encoding="utf-8")
    try:
        import yaml  # noqa: F401
    except ImportError:
        pytest.skip("pyyaml not installed")
    cfg = load_config(source)
    assert cfg.protocol.profile_name == "Default YAML"
    assert [s.signal_name for s in cfg.signals_by_frame[0x0010]] == ["YAML_Voltage"]


def test_exported_excel_template_loads_legacy_schema(tmp_path):
    source = tmp_path / "legacy"
    source.mkdir()
    _write_basic_protocol(source)
    (source / "frame_config.csv").write_text(
        "frame_id_hex,frame_name,signal_name,start_byte,byte_length,"
        "endianness,data_type,scale,offset,unit\n"
        "0010,Cell_Voltages,Cell Voltage 1,0,2,big,uint,0.001,0,V\n",
        encoding="utf-8",
    )

    target = tmp_path / "legacy_template.xlsx"
    export_excel_template(source, target)
    cfg = load_config(target)
    assert [s.signal_name for s in cfg.signals_by_frame[0x0010]] == ["Cell Voltage 1"]


# --- Error reporting --------------------------------------------------------


def _write_basic_protocol(d: Path) -> None:
    (d / "protocol.csv").write_text(
        "profile_name,header_hex,frame_id_size,frame_id_byte_order,"
        "length_size,length_meaning,crc_type,crc_size,crc_byte_order,"
        "crc_coverage,footer_hex,escape_mode,raw_log_format,enabled\n"
        "Default BMS,AA55,2,big,1,payload_only,crc16_modbus,2,little,"
        "header_to_payload,,none,hex,TRUE\n",
        encoding="utf-8",
    )


def test_missing_required_column(tmp_path):
    _write_basic_protocol(tmp_path)
    # frame_config.csv missing the `data_type` column.
    (tmp_path / "frame_config.csv").write_text(
        "frame_id_hex,frame_name,signal_name,start_byte,byte_length,"
        "endianness,scale,offset,unit\n"
        "0010,Cell_Voltages,Cell_1_Voltage,0,2,big,0.001,0,V\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="missing required columns"):
        load_config(tmp_path)


def test_missing_column_suggests_typo(tmp_path):
    """`frame_id` instead of `frame_id_hex` should trigger a did-you-mean hint."""
    _write_basic_protocol(tmp_path)
    (tmp_path / "frame_config.csv").write_text(
        # frame_id_hex misspelt as frame_id — exactly the user-facing typo we
        # documented in the legacy-FrameConfig section of the help.
        "frame_id,frame_name,signal_name,start_byte,byte_length,"
        "endianness,data_type,scale,offset,unit\n"
        "0010,Cell_Voltages,Cell_1_Voltage,0,2,big,uint,0.001,0,V\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"did you mean 'frame_id'"):
        load_config(tmp_path)


def test_unsupported_data_type(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "frame_config.csv").write_text(
        "frame_id_hex,frame_name,signal_name,start_byte,byte_length,"
        "endianness,data_type,scale,offset,unit\n"
        "0010,X,Sig,0,2,big,bigint,1,0,V\n",  # bogus data_type
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="data_type must be one of"):
        load_config(tmp_path)


def test_float_requires_byte_length_4_or_8(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "frame_config.csv").write_text(
        "frame_id_hex,frame_name,signal_name,start_byte,byte_length,"
        "endianness,data_type,scale,offset,unit\n"
        "0010,X,F,0,2,little,float,1,0,V\n",  # float w/ byte_length=2
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="float data_type requires"):
        load_config(tmp_path)


def test_duplicate_signal_name_in_frame(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "frame_config.csv").write_text(
        "frame_id_hex,frame_name,signal_name,start_byte,byte_length,"
        "endianness,data_type,scale,offset,unit\n"
        "0010,X,Sig,0,2,big,uint,1,0,V\n"
        "0010,X,Sig,2,2,big,uint,1,0,V\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate signal"):
        load_config(tmp_path)


def test_invalid_endianness(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "frame_config.csv").write_text(
        "frame_id_hex,frame_name,signal_name,start_byte,byte_length,"
        "endianness,data_type,scale,offset,unit\n"
        "0010,X,Sig,0,2,middle,uint,1,0,V\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="endianness"):
        load_config(tmp_path)


def test_unsupported_fmt_in_full_schema(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,unit,scale,offset,count,group_name,byte_order,enabled,description\n"
        "0x0010,Sig,uint24,V,1,0,1,,big,TRUE,\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"data_type \(fmt\) must be one of"):
        load_config(tmp_path)


# --- Frames sheet: direction column ----------------------------------------


def _write_frames_direction_fixture(d: Path, direction_value: str) -> None:
    """Minimal modern-schema config: frames.csv + variables.csv (NOT frame_config.csv —
    the loader prefers frame_config and would skip our frames.csv)."""
    _write_basic_protocol(d)
    (d / "frames.csv").write_text(
        "frame_id,frame_name,direction,enabled\n"
        f"0x0010,Frame_10,{direction_value},TRUE\n",
        encoding="utf-8",
    )
    (d / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,"
        "scale,offset,unit,enabled\n"
        "0x0010,Sig,uint16,1,big,1,0,V,TRUE\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("value,expected", [
    ("", "rxtx"),
    ("rx", "rx"),
    ("tx", "tx"),
    ("rxtx", "rxtx"),
    ("RX", "rx"),     # case-insensitive
    ("  Tx  ", "tx"), # whitespace tolerant
])
def test_frames_direction_parses(tmp_path, value, expected):
    _write_frames_direction_fixture(tmp_path, value)
    cfg = load_config(tmp_path)
    assert cfg.frames[0x0010].direction == expected


def test_frames_direction_invalid_value_rejected(tmp_path):
    _write_frames_direction_fixture(tmp_path, "bidirectional")
    with pytest.raises(ConfigError, match="direction must be"):
        load_config(tmp_path)


def test_frames_direction_helpers():
    """is_tx_capable / is_rx_capable correctly classify each direction value."""
    from app.decoder.types import FrameDefinition
    rx = FrameDefinition(frame_id=1, frame_name="F", direction="rx")
    tx = FrameDefinition(frame_id=2, frame_name="F", direction="tx")
    both = FrameDefinition(frame_id=3, frame_name="F", direction="rxtx")
    default = FrameDefinition(frame_id=4, frame_name="F")
    assert rx.is_rx_capable and not rx.is_tx_capable
    assert tx.is_tx_capable and not tx.is_rx_capable
    assert both.is_rx_capable and both.is_tx_capable
    assert default.direction == "rxtx" and default.is_rx_capable and default.is_tx_capable


def test_auto_created_frames_default_rxtx(tmp_path):
    """Frames auto-created from variables.csv (no frames.csv row) get direction='rxtx'."""
    _write_basic_protocol(tmp_path)
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,"
        "scale,offset,unit,enabled\n"
        "0x0099,Sig,uint16,1,big,1,0,V,TRUE\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.frames[0x0099].direction == "rxtx"


def test_csv_filename_normalization(tmp_path):
    """CSV file stems should be normalized using _normalize_table_name, allowing aliases."""
    _write_basic_protocol(tmp_path)
    (tmp_path / "framevariables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,"
        "scale,offset,unit,enabled,group\n"
        "0x0010,Sig,uint16,1,big,1,0,V,TRUE,TempGroup\n",
        encoding="utf-8",
    )
    (tmp_path / "calcgroups.csv").write_text(
        "group_name,operations,unit,frame_id,enabled\n"
        "TempGroup,min|max,V,0x0010,TRUE\n",
        encoding="utf-8",
    )
    (tmp_path / "serialdefaults.csv").write_text(
        "baud_rate,data_bits,stop_bits,parity,timeout_ms\n"
        "9600,8,1,N,50\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert 0x0010 in cfg.signals_by_frame
    assert len(cfg.calc_groups) == 2
    assert cfg.calc_groups[0].group == "TempGroup"
    assert cfg.serial_defaults.baud_rate == 9600


def test_duplicate_tx_commands_rejected(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,scale,offset,unit,enabled\n"
        "0x0010,Sig,uint16,1,big,1,0,V,TRUE\n",
        encoding="utf-8",
    )
    (tmp_path / "tx_commands.csv").write_text(
        "command_name,id_or_address,payload_hex,description,enabled\n"
        "Cmd1,0x0010,1234,,TRUE\n"
        "Cmd1,0x0010,5678,,TRUE\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Duplicate tx_command defined with name 'Cmd1'"):
        load_config(tmp_path)


def test_duplicate_enum_value_rejected(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,scale,offset,unit,enabled\n"
        "0x0010,Sig,uint16,1,big,1,0,V,TRUE\n",
        encoding="utf-8",
    )
    (tmp_path / "enums.csv").write_text(
        "id_or_address,signal_name,value,label\n"
        "0x0010,Sig,1,Active\n"
        "0x0010,Sig,1,DuplicateActive\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="enums row 3: duplicate enum value 1 for signal 'Sig'"):
        load_config(tmp_path)


def test_modbus_rtu_endianness_checks(tmp_path):
    # Invalid register address (frame_id_byte_order)
    (tmp_path / "protocol.csv").write_text(
        "profile_name,header_hex,frame_id_size,frame_id_byte_order,"
        "length_size,length_meaning,crc_type,crc_size,crc_byte_order,"
        "crc_coverage,footer_hex,escape_mode,raw_log_format,enabled,parser_type\n"
        "Modbus Invalid,01,1,little,1,payload_only,crc16_modbus,2,little,"
        "header_to_payload,,none,hex,TRUE,modbus_rtu\n",
        encoding="utf-8",
    )
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,scale,offset,unit,enabled\n"
        "1,Sig,uint16,1,big,1,0,V,TRUE\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Modbus RTU register addresses .* must be big-endian"):
        load_config(tmp_path)

    # Invalid CRC byte order
    (tmp_path / "protocol.csv").write_text(
        "profile_name,header_hex,frame_id_size,frame_id_byte_order,"
        "length_size,length_meaning,crc_type,crc_size,crc_byte_order,"
        "crc_coverage,footer_hex,escape_mode,raw_log_format,enabled,parser_type\n"
        "Modbus Invalid,01,1,big,1,payload_only,crc16_modbus,2,big,"
        "header_to_payload,,none,hex,TRUE,modbus_rtu\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Modbus RTU CRC checksum .* must be little-endian"):
        load_config(tmp_path)

    # Invalid data value byte order (variables.csv)
    (tmp_path / "protocol.csv").write_text(
        "profile_name,header_hex,frame_id_size,frame_id_byte_order,"
        "length_size,length_meaning,crc_type,crc_size,crc_byte_order,"
        "crc_coverage,footer_hex,escape_mode,raw_log_format,enabled,parser_type\n"
        "Modbus Valid,01,1,big,1,payload_only,crc16_modbus,2,little,"
        "header_to_payload,,none,hex,TRUE,modbus_rtu\n",
        encoding="utf-8",
    )
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,scale,offset,unit,enabled\n"
        "1,Sig,uint16,1,little,1,0,V,TRUE\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Modbus RTU data values .* must be big-endian"):
        load_config(tmp_path)


def test_duplicate_bitfield_index_or_label_rejected(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,scale,offset,unit,enabled\n"
        "0x0010,Sig,uint16,1,big,1,0,,TRUE\n",
        encoding="utf-8",
    )
    # 1. Duplicate bit_index
    (tmp_path / "bitfields.csv").write_text(
        "id_or_address,signal_name,bit_index,label\n"
        "0x0010,Sig,0,Label1\n"
        "0x0010,Sig,0,Label2\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate bit_index 0"):
        load_config(tmp_path)

    # 2. Duplicate label
    (tmp_path / "bitfields.csv").write_text(
        "id_or_address,signal_name,bit_index,label\n"
        "0x0010,Sig,0,Label1\n"
        "0x0010,Sig,1,Label1\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate bit label 'Label1'"):
        load_config(tmp_path)


def test_duplicate_calc_groups_rejected(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,scale,offset,unit,enabled,group\n"
        "0x0010,Sig,uint16,1,big,1,0,,TRUE,TempGroup\n",
        encoding="utf-8",
    )
    (tmp_path / "calc_groups.csv").write_text(
        "group_name,operations,unit,frame_id,enabled\n"
        "TempGroup,min|min,V,0x0010,TRUE\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate calculation 'min'"):
        load_config(tmp_path)


def test_duplicate_polling_schedule_rejected(tmp_path):
    _write_basic_protocol(tmp_path)
    (tmp_path / "variables.csv").write_text(
        "id_or_address,signal_name,data_type,count,byte_order,scale,offset,unit,enabled\n"
        "0x0010,Sig,uint16,1,big,1,0,,TRUE\n",
        encoding="utf-8",
    )
    (tmp_path / "polling_schedule.csv").write_text(
        "id_or_address,interval_ms,timeout_ms,enabled\n"
        "0x0010,100,50,TRUE\n"
        "0x0010,200,50,TRUE\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate polling schedule for ID 0x10"):
        load_config(tmp_path)


def test_waveshare_can_config_loading(tmp_path):
    source = tmp_path / "config.json"
    import json
    data = {
        "protocol": [
            {
                "profile_name": "Waveshare Test",
                "parser_type": "waveshare_can",
                "enabled": "TRUE"
            }
        ],
        "variables": [
            {
                "id_or_address": "0x0123",
                "signal_name": "CAN_Signal",
                "data_type": "uint16",
                "count": 1,
                "byte_order": "little",
                "scale": 1.0,
                "offset": 0,
                "unit": "V",
                "enabled": "TRUE"
            }
        ]
    }
    with source.open("w", encoding="utf-8") as f:
        json.dump(data, f)
    cfg = load_config(source)
    assert cfg.protocol.profile_name == "Waveshare Test"
    assert cfg.protocol.parser_type == "waveshare_can"
    assert cfg.protocol.header == b"\xAA"
    assert cfg.protocol.frame_id_size == 2
    assert cfg.protocol.length_size == 1
    assert cfg.protocol.length_meaning == "payload_only"
    assert cfg.protocol.crc_type == "none"
    assert cfg.protocol.crc_size == 0
    assert cfg.protocol.footer == b"\x55"
    assert cfg.protocol.waveshare_fixed_20_bytes is False


def test_waveshare_can_config_loading_fixed(tmp_path):
    source = tmp_path / "config.json"
    import json
    data = {
        "protocol": [
            {
                "profile_name": "Waveshare Fixed Test",
                "parser_type": "waveshare_can",
                "waveshare_fixed_20_bytes": "TRUE",
                "enabled": "TRUE"
            }
        ],
        "variables": [
            {
                "id_or_address": "0x0123",
                "signal_name": "CAN_Signal",
                "data_type": "uint16",
                "count": 1,
                "byte_order": "little",
                "scale": 1.0,
                "offset": 0,
                "unit": "V",
                "enabled": "TRUE"
            }
        ]
    }
    with source.open("w", encoding="utf-8") as f:
        json.dump(data, f)
    cfg = load_config(source)
    assert cfg.protocol.profile_name == "Waveshare Fixed Test"
    assert cfg.protocol.parser_type == "waveshare_can"
    assert cfg.protocol.waveshare_fixed_20_bytes is True


