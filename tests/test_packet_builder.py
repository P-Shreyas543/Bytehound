"""Tests for `app.protocol.packet_builder.build_packet`."""

from __future__ import annotations

from app.protocol.packet_builder import build_packet
from app.protocol.packet_parser import create_parser, FramedParser
from tests.conftest import (
    CANONICAL_FRAME_HEX,
    CANONICAL_FRAME_ID,
    CANONICAL_PAYLOAD_HEX,
    hex_to_bytes,
)


def test_builds_canonical_frame(config):
    payload = hex_to_bytes(CANONICAL_PAYLOAD_HEX)
    built = build_packet(config.protocol, CANONICAL_FRAME_ID, payload)
    assert built == hex_to_bytes(CANONICAL_FRAME_HEX)


def test_round_trip_through_parser(config):
    payloads = [bytes.fromhex(h) for h in ("0FA00BB8", "1000FFFF", "00000001")]
    parser = create_parser(config.protocol)
    for p in payloads:
        parser.feed(build_packet(config.protocol, 0x0010, p))
    packets = parser.extract_all()
    assert [p.payload for p in packets] == payloads
    assert all(p.ok and p.frame_id == 0x0010 for p in packets)
