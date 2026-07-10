"""Tests for `app.protocol.packet_builder.build_packet`."""

from __future__ import annotations

from app.protocol.packet_builder import build_packet
from app.protocol.packet_parser import create_parser
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


# --- length_meaning x crc_coverage round-trip matrix ------------------------
#
# Build a frame, feed it back through the parser, and confirm the parser
# recovers the same frame_id and payload. Doing this for every combination
# of length_meaning and crc_coverage is the self-consistency check: it
# proves build/parse agree on the byte layout for each variant. It does
# NOT prove the variant matches anyone else's spec — only that our parser
# can decode what our builder produces.

import pytest  # noqa: E402  (kept inline so the existing top stays tidy)

from app.protocol.packet_parser import LENGTH_MEANINGS, CRC_COVERAGES, ESCAPE_MODES  # noqa: E402
from tests.conftest import dummy_protocol_config  # noqa: E402


@pytest.mark.parametrize("length_meaning", LENGTH_MEANINGS)
@pytest.mark.parametrize("crc_coverage", CRC_COVERAGES)
@pytest.mark.parametrize("with_footer", [False, True])
@pytest.mark.parametrize("escape_mode", ESCAPE_MODES)
def test_build_parse_roundtrip_all_variants(length_meaning, crc_coverage, with_footer, escape_mode):
    proto = dummy_protocol_config(
        length_meaning=length_meaning,
        crc_coverage=crc_coverage,
        footer=b"\xEE" if with_footer else b"",
        escape_mode=escape_mode,
        # length_size=2 keeps headroom for the larger length values that
        # frame_total / header_to_crc encode.
        length_size=2,
    )
    payloads = [
        b"\x0F\xA0\x0B\xB8",
        b"\x10\x00\xFF\xFF",
        b"\x00\x00\x00\x01",
    ]
    parser = create_parser(proto)
    for p in payloads:
        frame = build_packet(proto, 0x1234, p)
        parser.feed(frame)
    packets = parser.extract_all()
    assert len(packets) == len(payloads), (
        f"expected {len(payloads)} packets, got {len(packets)} for "
        f"length_meaning={length_meaning} crc_coverage={crc_coverage} "
        f"escape_mode={escape_mode} footer={with_footer}"
    )
    assert [pkt.payload for pkt in packets] == payloads
    assert all(pkt.ok and pkt.frame_id == 0x1234 for pkt in packets)


# Each escape scheme has 1-2 bytes that MUST round-trip correctly when they
# appear inside the payload (the encoder is supposed to expand them, the
# decoder is supposed to collapse them back). These targeted tests use
# payloads constructed to maximally exercise each scheme's escape path.
@pytest.mark.parametrize("escape_mode,payload", [
    ("slip", b"\xC0\xC0\xDB\xDB\xC0\xDB"),    # SLIP: END=0xC0 and ESC=0xDB
    ("hdlc", b"\x7E\x7E\x7D\x7D\x7E\x7D"),    # HDLC: FLAG=0x7E and ESC=0x7D
    ("cobs", b"\x00\x00\x00\x00\x00\x00"),    # COBS: all zeros (worst case)
    ("cobs", b"\x01\x00\x02\x00\x03\x00"),    # COBS: alternating non-zero/zero
])
def test_escape_modes_handle_their_own_special_bytes(escape_mode, payload):
    proto = dummy_protocol_config(escape_mode=escape_mode, length_size=2)
    parser = create_parser(proto)
    parser.feed(build_packet(proto, 0xABCD, payload))
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].ok
    assert packets[0].frame_id == 0xABCD
    assert packets[0].payload == payload


@pytest.mark.parametrize("escape_mode", ["slip", "hdlc", "cobs"])
def test_escape_modes_handle_frames_split_across_feeds(escape_mode):
    """A single TX frame chunked into one-byte feeds must still reassemble.
    Catches state-machine bugs where escape sequences span chunk boundaries."""
    proto = dummy_protocol_config(escape_mode=escape_mode, length_size=2)
    payload = b"\x0F\xA0\xC0\xDB\x7E\x7D\x00\xFF"
    frame = build_packet(proto, 0x1234, payload)
    parser = create_parser(proto)
    for b in frame:
        parser.feed(bytes([b]))
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].ok
    assert packets[0].payload == payload


@pytest.mark.parametrize("escape_mode", ["slip", "hdlc", "cobs"])
def test_escape_modes_handle_multiple_frames_in_one_feed(escape_mode):
    """Three concatenated frames in a single feed() must all be extracted."""
    proto = dummy_protocol_config(escape_mode=escape_mode, length_size=2)
    payloads = [b"\x01\x02", b"\xC0\x7E\x00", b"\xFF\xFF\xFF\xFF"]
    blob = b"".join(build_packet(proto, 0x1234, p) for p in payloads)
    parser = create_parser(proto)
    parser.feed(blob)
    packets = parser.extract_all()
    assert len(packets) == len(payloads)
    assert [p.payload for p in packets] == payloads
    assert all(p.ok and p.frame_id == 0x1234 for p in packets)


def test_invalid_length_value_resyncs_not_hangs():
    """A length value too small for the protocol shape (e.g. frame_total < fixed
    overhead) must not deadlock the parser — it should drop the header byte and
    keep going."""
    proto = dummy_protocol_config(length_meaning="frame_total", length_size=2)
    parser = create_parser(proto)
    # Header AA 55, frame_id 0x1234 (big), length=0 (impossible for frame_total).
    # Followed by a valid frame after enough trailing bytes so the parser can
    # find the next AA 55 and lock on.
    garbage = b"\xAA\x55\x12\x34\x00\x00\xDE\xAD\xBE\xEF"
    good_frame = build_packet(proto, 0x4321, b"\x99\x88")
    parser.feed(garbage + good_frame)
    packets = parser.extract_all()
    ok = [p for p in packets if p.ok]
    assert ok, "parser should have eventually recovered the good frame"
    assert ok[-1].frame_id == 0x4321
    assert ok[-1].payload == b"\x99\x88"
