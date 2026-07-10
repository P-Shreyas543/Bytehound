from __future__ import annotations

import pytest
from app.decoder.types import ProtocolConfig
from app.protocol.packet_parser import create_parser
from app.protocol.packet_builder import build_packet


def make_waveshare_protocol(frame_id_size: int = 2) -> ProtocolConfig:
    return ProtocolConfig(
        profile_name="waveshare_test",
        header=b"\xAA",
        frame_id_size=frame_id_size,
        frame_id_byte_order="little",
        length_size=1,
        length_meaning="payload_only",
        crc_type="none",
        crc_size=0,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"\x55",
        escape_mode="none",
        enabled=True,
        parser_type="waveshare_can"
    )


def test_waveshare_can_parse_standard_happy():
    protocol = make_waveshare_protocol(frame_id_size=2)
    parser = create_parser(protocol)

    # Standard data frame, ID 0x0123, payload 11 22, footer 55
    # AA + C2 (standard, dlc=2) + 23 01 + 11 22 + 55
    raw_packet = b"\xAA\xC2\x23\x01\x11\x22\x55"
    parser.feed(raw_packet)
    packets = parser.extract_all()

    assert len(packets) == 1
    p = packets[0]
    assert p.ok
    assert p.frame_id == 0x0123
    assert p.payload == b"\x11\x22"
    assert p.raw == raw_packet


def test_waveshare_can_parse_extended_happy():
    protocol = make_waveshare_protocol(frame_id_size=4)
    parser = create_parser(protocol)

    # Extended data frame, ID 0x07654321, payload 99, footer 55
    # AA + E1 (extended, dlc=1) + 21 43 65 07 + 99 + 55
    # Wait, 0x07654321 in 4 bytes little endian: 21 43 65 07
    # Let's use 0x12345678: 78 56 34 12
    raw_packet_correct = b"\xAA\xE1\x78\x56\x34\x12\x99\x55"
    parser.feed(raw_packet_correct)
    packets = parser.extract_all()

    assert len(packets) == 1
    p = packets[0]
    assert p.ok
    assert p.frame_id == 0x12345678
    assert p.payload == b"\x99"
    assert p.raw == raw_packet_correct


def test_waveshare_can_parse_unaligned_garbage():
    protocol = make_waveshare_protocol(frame_id_size=2)
    parser = create_parser(protocol)

    # Garbage bytes before and between valid frames
    garbage = b"\x11\x22\xAA\x00\xFF"  # includes dummy AA with invalid type byte 0x00
    valid1 = b"\xAA\xC0\x10\x00\x55"  # Standard DLC 0, ID 0x10
    valid2 = b"\xAA\xC1\x20\x00\x99\x55"  # Standard DLC 1, ID 0x20

    parser.feed(garbage + valid1 + b"\xBB\xCC" + valid2)
    packets = parser.extract_all()

    assert len(packets) == 2
    assert packets[0].frame_id == 0x10
    assert packets[0].payload == b""
    assert packets[1].frame_id == 0x20
    assert packets[1].payload == b"\x99"


def test_waveshare_can_parse_invalid_type_and_footer():
    protocol = make_waveshare_protocol(frame_id_size=2)
    parser = create_parser(protocol)

    # 1. Invalid type byte (doesn't start with 0xC0)
    # AA + 80 + 10 00 + 55
    parser.feed(b"\xAA\x80\x10\x00\x55")
    assert len(parser.extract_all()) == 0

    # 2. DLC > 8
    # AA + C9 + 10 00 + 9 bytes + 55
    parser.feed(b"\xAA\xC9\x10\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x55")
    assert len(parser.extract_all()) == 0

    # 3. Invalid footer (ends with 99 instead of 55)
    # AA + C1 + 10 00 + FF + 99
    parser.feed(b"\xAA\xC1\x10\x00\xFF\x99")
    assert len(parser.extract_all()) == 0

    # Should recover on subsequent valid frame
    parser.feed(b"\xAA\xC0\x10\x00\x55")
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].frame_id == 0x10


def test_waveshare_can_build_standard():
    protocol = make_waveshare_protocol(frame_id_size=2)

    # Standard DLC 2, ID 0x123
    built = build_packet(protocol, 0x123, b"\x11\x22")
    assert built == b"\xAA\xC2\x23\x01\x11\x22\x55"


def test_waveshare_can_build_extended():
    protocol = make_waveshare_protocol(frame_id_size=4)

    # Extended DLC 1, ID 0x12345678
    built = build_packet(protocol, 0x12345678, b"\x99")
    assert built == b"\xAA\xE1\x78\x56\x34\x12\x99\x55"


def test_waveshare_can_build_invalid():
    protocol = make_waveshare_protocol(frame_id_size=2)

    # Payload > 8 bytes should raise ValueError
    with pytest.raises(ValueError, match="payload must be <= 8 bytes"):
        build_packet(protocol, 0x123, b"\x01\x02\x03\x04\x05\x06\x07\x08\x09")


def test_waveshare_can_parse_fixed_happy():
    protocol = make_waveshare_protocol()
    parser = create_parser(protocol)

    # Happy path for fixed 20-byte frame:
    # AA 55 01 01 01 F0 02 00 00 04 7B BA 90 01 FF FF FF F8 00 B4
    raw_packet = b"\xAA\x55\x01\x01\x01\xF0\x02\x00\x00\x04\x7B\xBA\x90\x01\xFF\xFF\xFF\xF8\x00\xB4"
    parser.feed(raw_packet)
    packets = parser.extract_all()

    assert len(packets) == 1
    p = packets[0]
    assert p.ok
    assert p.frame_id == 0x2F0
    assert p.payload == b"\x7B\xBA\x90\x01"
    assert p.raw == raw_packet


def test_waveshare_can_parse_fixed_bad_checksum():
    protocol = make_waveshare_protocol()
    parser = create_parser(protocol)

    # Bad checksum at the end (B5 instead of B4)
    raw_packet = b"\xAA\x55\x01\x01\x01\xF0\x02\x00\x00\x04\x7B\xBA\x90\x01\xFF\xFF\xFF\xF8\x00\xB5"
    parser.feed(raw_packet)
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].ok is False
    assert "checksum mismatch" in packets[0].error

    # Recover with standard variable-length frame
    parser.feed(b"\xAA\xC0\x10\x00\x55")
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].frame_id == 0x10


def test_waveshare_can_build_fixed_standard():
    import dataclasses
    protocol = make_waveshare_protocol()
    fixed_protocol = dataclasses.replace(protocol, waveshare_fixed_20_bytes=True)

    built = build_packet(fixed_protocol, 0x2F0, b"\x7B\xBA\x90\x01")
    assert built == b"\xAA\x55\x01\x01\x01\xF0\x02\x00\x00\x04\x7B\xBA\x90\x01\x00\x00\x00\x00\x00\xBF"


def test_waveshare_can_build_fixed_extended():
    import dataclasses
    protocol = make_waveshare_protocol(frame_id_size=4)
    fixed_protocol = dataclasses.replace(protocol, waveshare_fixed_20_bytes=True)

    built = build_packet(fixed_protocol, 0x12345678, b"\x99")
    assert built == b"\xAA\x55\x01\x02\x01\x78\x56\x34\x12\x01\x99\x00\x00\x00\x00\x00\x00\x00\x00\xB2"

