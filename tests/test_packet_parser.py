"""Tests for `app.protocol.packet_parser.PacketParser`."""

from __future__ import annotations

from app.protocol.packet_parser import create_parser, FramedParser
from tests.conftest import (
    CANONICAL_FRAME_HEX,
    CANONICAL_FRAME_ID,
    CANONICAL_PAYLOAD_HEX,
    hex_to_bytes,
)


def test_parses_canonical_frame(config):
    parser = create_parser(config.protocol)
    parser.feed(hex_to_bytes(CANONICAL_FRAME_HEX))
    packets = parser.extract_all()
    assert len(packets) == 1
    p = packets[0]
    assert p.ok and p.error is None
    assert p.frame_id == CANONICAL_FRAME_ID
    assert p.payload == hex_to_bytes(CANONICAL_PAYLOAD_HEX)
    assert parser.buffered_bytes == 0


def test_recovers_from_leading_garbage(config):
    parser = create_parser(config.protocol)
    parser.feed(b"\xFF\x01\x02" + hex_to_bytes(CANONICAL_FRAME_HEX))
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].ok
    assert packets[0].frame_id == CANONICAL_FRAME_ID


def test_handles_partial_feed(config):
    parser = create_parser(config.protocol)
    full = hex_to_bytes(CANONICAL_FRAME_HEX)
    parser.feed(full[:5])
    assert parser.extract_all() == []
    parser.feed(full[5:])
    packets = parser.extract_all()
    assert len(packets) == 1 and packets[0].ok


def test_bad_crc_emits_error_and_resyncs(config):
    parser = create_parser(config.protocol)
    # Same frame layout but with a deliberately wrong CRC, followed
    # by a valid frame. The parser should report an error for the
    # first frame and recover the second.
    bad = hex_to_bytes("AA55 0010 04 0FA00BB8 0000")
    good = hex_to_bytes(CANONICAL_FRAME_HEX)
    parser.feed(bad + good)

    packets = parser.extract_all()
    assert len(packets) >= 1
    assert any(not p.ok and "CRC" in (p.error or "") for p in packets)
    assert any(p.ok and p.frame_id == CANONICAL_FRAME_ID for p in packets)


def test_back_to_back_frames(config):
    parser = create_parser(config.protocol)
    frame = hex_to_bytes(CANONICAL_FRAME_HEX)
    parser.feed(frame * 3)
    packets = parser.extract_all()
    assert len(packets) == 3
    assert all(p.ok for p in packets)
