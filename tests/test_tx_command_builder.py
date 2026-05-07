from __future__ import annotations

import pytest

from app.commands.tx_command_builder import CommandBuildError, build_payload, build_tx_command
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
