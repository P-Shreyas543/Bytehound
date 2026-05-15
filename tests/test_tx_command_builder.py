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
    rows = [
        f"SetTwoBytes,{name},uint8,1,0,,,,\n" for name in field_order
    ]
    (d / "tx_command_fields.csv").write_text(
        "command_name,signal_name,data_type,scale,offset,unit,byte_order,min_value,max_value,default\n"
        + "".join(rows),
        encoding="utf-8",
    )


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
