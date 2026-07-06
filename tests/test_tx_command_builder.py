from __future__ import annotations

from pathlib import Path

import pytest

from app.commands.tx_command_builder import CommandBuildError, build_payload, build_tx_command
from app.decoder.config_loader import load_config
from app.protocol.packet_parser import create_parser, FramedParser


def test_builds_static_tx_command(config):
    packet = build_tx_command(config, "Request Fault Codes")
    parser = create_parser(config.protocol)
    parser.feed(packet)
    parsed = parser.extract_all()
    assert len(parsed) == 1
    assert parsed[0].ok
    assert parsed[0].frame_id == 0x8001
    assert parsed[0].payload == b"\x01"


def test_builds_field_tx_payload(config):
    command = config.tx_commands["Set Charge Current"]
    assert build_payload(command, {"Current Limit": 12.3}) == b"\x00\x7b"


def test_rejects_out_of_range_tx_value(config):
    with pytest.raises(CommandBuildError, match="above maximum"):
        build_tx_command(config, "Set Charge Current", {"Current Limit": 120})


# ─── Regression: TxCommand field order = sheet row order ────────────────────
#
# This locks the documented contract in app/decoder/config_loader.py: the
# bytes a multi-field command emits follow the order of rows in
# tx_command_fields.csv. Re-shuffling that loader (e.g. dict-sorting fields,
# or stable-sorting by name) would silently break every config in the wild
# that relies on row order, and the test catches that.


def _write_two_field_cmd_config(d: Path, *, field_order: list[str]) -> None:
    (d / "protocol.csv").write_text(
        "profile_name,header_hex,frame_id_size,frame_id_byte_order,"
        "length_size,length_meaning,crc_type,crc_size,crc_byte_order,enabled\n"
        "p,AA55,2,big,1,payload_only,crc16_modbus,2,little,TRUE\n",
        encoding="utf-8",
    )
    (d / "frames.csv").write_text(
        "frame_id,frame_name\n0x9000,SetTwoBytes\n",
        encoding="utf-8",
    )
    # Loader requires at least one signal row; add a placeholder so the
    # config is valid. The signal itself is irrelevant for this test.
    (d / "variables.csv").write_text(
        "id_or_address,signal_name,data_type\n"
        "0x9000,Echo,uint8\n",
        encoding="utf-8",
    )
    (d / "tx_commands.csv").write_text(
        "command_name,id_or_address,payload_hex,enabled\n"
        "SetTwoBytes,0x9000,,TRUE\n",
        encoding="utf-8",
    )
    csv_lines = ["command_name,signal_name,data_type,byte_order,factor,offset,unit,default,min_value,max_value"]
    for field in field_order:
        csv_lines.append(f"SetTwoBytes,{field},uint8,big,1,0,,12,,")
    
    (d / "tx_command_fields.csv").write_text(
        "\n".join(csv_lines) + "\n",
        encoding="utf-8",
    )


def test_tx_field_factor_zero():
    from app.decoder.types import TxCommandFieldSpec
    field = TxCommandFieldSpec(
        command_name="test", field_name="test", fmt="uint8", byte_order="little",
        factor=0, offset=0, default=None, min_value=None, max_value=None
    )
    from app.commands.tx_command_builder import _encode_field, CommandBuildError
    with pytest.raises(CommandBuildError, match="factor must not be zero"):
        _encode_field(field, 10.0)


def test_tx_field_float_encoding():
    from app.decoder.types import TxCommandFieldSpec
    field32 = TxCommandFieldSpec(
        command_name="test", field_name="test", fmt="float32", byte_order="big",
        factor=1.0, offset=0.0, default=None, min_value=None, max_value=None
    )
    from app.commands.tx_command_builder import _encode_field
    import struct
    # 1.5 in float32 big-endian is \x3f\xc0\x00\x00
    assert _encode_field(field32, 1.5) == b"\x3f\xc0\x00\x00"


def test_tx_field_overflow():
    from app.decoder.types import TxCommandFieldSpec
    field = TxCommandFieldSpec(
        command_name="test", field_name="test", fmt="uint8", byte_order="little",
        factor=1.0, offset=0.0, default=None, min_value=None, max_value=None
    )
    from app.commands.tx_command_builder import _encode_field, CommandBuildError
    # We bypass min/max_value checks since they are None. Value 300 > 255.
    with pytest.raises(CommandBuildError, match="does not fit in"):
        _encode_field(field, 300)


def test_field_order_follows_sheet_rows(tmp_path):
    """Field row order in tx_command_fields.csv is the wire order."""
    forward = tmp_path / "forward"
    forward.mkdir()
    _write_two_field_cmd_config(forward, field_order=["A", "B"])
    cfg_f = load_config(forward)
    cmd_f = cfg_f.tx_commands["SetTwoBytes"]
    # field_name list reflects the order the loader iterated tx_command_fields rows.
    assert [f.field_name for f in cmd_f.fields] == ["A", "B"]
    # Payload bytes follow that same order — A first, then B.
    assert build_payload(cmd_f, {"A": 0x11, "B": 0x22}) == b"\x11\x22"

    backward = tmp_path / "backward"
    backward.mkdir()
    _write_two_field_cmd_config(backward, field_order=["B", "A"])
    cfg_b = load_config(backward)
    cmd_b = cfg_b.tx_commands["SetTwoBytes"]
    assert [f.field_name for f in cmd_b.fields] == ["B", "A"]
    # Swapping the rows swaps the bytes — proving row order drives the wire order.
    assert build_payload(cmd_b, {"A": 0x11, "B": 0x22}) == b"\x22\x11"
