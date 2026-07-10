"""Tests for `app.protocol.packet_parser.PacketParser`."""

from __future__ import annotations

from app.protocol.packet_parser import (
    create_parser,
    FramedParser,
    ModbusRtuParser,
    _MAX_BUFFER_BYTES,
)
from tests.conftest import (
    CANONICAL_FRAME_HEX,
    CANONICAL_FRAME_ID,
    CANONICAL_PAYLOAD_HEX,
    dummy_protocol_config,
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


# ─── Hardening: unbounded-buffer protection ─────────────────────────────────


def test_framed_parser_buffer_does_not_grow_unbounded(config):
    """Stream that never matches the framing pattern must not exhaust memory.

    Without the cap in feed(), a flood of 0xFF would grow _buf without limit.
    With the cap, the buffer should stay bounded near _MAX_BUFFER_BYTES.
    """
    parser = create_parser(config.protocol)
    chunk = b"\xFF" * 100_000  # 100 KB of garbage that can never form a frame
    for _ in range(50):  # 5 MB total fed in
        parser.feed(chunk)
        # extract_all() advances past any unmatched leading bytes too, but the
        # cap in feed() is the real safety net: even if the user never calls
        # extract_all(), memory stays bounded.
        parser.extract_all()
    assert parser.buffered_bytes <= _MAX_BUFFER_BYTES


def test_modbus_parser_buffer_does_not_grow_unbounded():
    """Same protection for the Modbus parser."""
    parser = ModbusRtuParser(dummy_protocol_config(parser_type="modbus_rtu"))
    chunk = b"\xFF" * 100_000
    for _ in range(50):
        parser.feed(chunk)
        parser.extract_all()
    assert parser.buffered_bytes <= _MAX_BUFFER_BYTES


# ─── Hardening: Modbus byte_count clamp ─────────────────────────────────────


def _modbus_frame(address: int, fc: int, body: bytes) -> bytes:
    """Build a Modbus RTU frame with a valid CRC16-Modbus suffix."""
    from app.protocol import crc as crc_mod
    head = bytes([address, fc]) + body
    crc = crc_mod.compute("crc16_modbus", head)
    return head + crc.to_bytes(2, "little")


def test_modbus_rejects_malformed_byte_count_too_large():
    """byte_count > 250 means the parser latched onto random bytes.

    Without the clamp, the parser would wait for 5 + 255 = 260 bytes that
    will never arrive — starving every other polling schedule.
    """
    parser = ModbusRtuParser(dummy_protocol_config(parser_type="modbus_rtu"))
    # Address 0x01, FC=3 (read holding registers), bogus byte_count=0xFF.
    # Followed by enough garbage bytes that the parser COULD have tried to
    # collect 260 bytes — we want to assert it doesn't.
    parser.feed(bytes([0x01, 0x03, 0xFF]) + b"\x00" * 300)
    # Parser should skip past the bogus start without waiting for 260 bytes.
    # We can't assert exact buffer state, but extract_all() must complete
    # quickly and the parser must not be wedged with hundreds of bytes
    # buffered indefinitely.
    parser.extract_all()
    # If the clamp works, the parser keeps trying to resync by dropping bytes,
    # eventually shrinking the buffer well below the 300 bytes we fed.
    assert parser.buffered_bytes < 300


def test_modbus_rejects_byte_count_zero():
    """byte_count == 0 means no data — invalid for FC3/FC4 reads."""
    parser = ModbusRtuParser(dummy_protocol_config(parser_type="modbus_rtu"))
    parser.feed(bytes([0x01, 0x03, 0x00]) + b"\x00" * 10)
    parser.extract_all()
    # Bogus header byte gets skipped; the parser should not have produced
    # a successful packet.
    # (No way to introspect dropped bytes directly; verify by feeding a
    # real frame next and checking it parses cleanly.)
    good = _modbus_frame(0x01, 0x03, bytes([0x02, 0x00, 0x2A]))  # 1 register = 0x002A
    parser.feed(good)
    packets = parser.extract_all()
    assert any(p.ok and p.frame_id == 0x01 for p in packets)


def test_modbus_rejects_odd_byte_count():
    """FC3/4 returns 16-bit registers, so byte_count must be even."""
    parser = ModbusRtuParser(dummy_protocol_config(parser_type="modbus_rtu"))
    # Odd byte_count = 3 is impossible for register reads.
    parser.feed(bytes([0x01, 0x03, 0x03]) + b"\x00" * 10)
    parser.extract_all()
    # Recovery check: a real frame fed afterward should still parse.
    good = _modbus_frame(0x01, 0x03, bytes([0x02, 0x00, 0x2A]))
    parser.feed(good)
    packets = parser.extract_all()
    assert any(p.ok and p.frame_id == 0x01 for p in packets)


def test_modbus_accepts_valid_byte_count():
    """Sanity: a well-formed FC3 response with byte_count=2 still parses."""
    parser = ModbusRtuParser(dummy_protocol_config(parser_type="modbus_rtu"))
    good = _modbus_frame(0x01, 0x03, bytes([0x02, 0x12, 0x34]))
    parser.feed(good)
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].ok
    assert packets[0].frame_id == 0x01
    assert packets[0].payload == bytes([0x12, 0x34])


def test_parser_buffer_overflow_trim(config):
    parser = create_parser(config.protocol)
    # Feed slightly more than max buffer to trigger overflow protection
    garbage = b"\x00" * (_MAX_BUFFER_BYTES + 10)
    parser.feed(garbage)

    # Buffer should be trimmed
    assert parser.buffered_bytes <= _MAX_BUFFER_BYTES

    # It should still be able to parse a valid frame after a trim
    good = hex_to_bytes(CANONICAL_FRAME_HEX)
    parser.feed(good)
    packets = parser.extract_all()
    assert len(packets) == 1
    assert packets[0].ok
    assert packets[0].frame_id == CANONICAL_FRAME_ID
    assert packets[0].payload == hex_to_bytes(CANONICAL_PAYLOAD_HEX)


# ─── Hardening: oversized length field cannot stall the parser ──────────────


def test_framed_parser_skips_impossible_length():
    """A spurious header followed by a payload_len > _MAX_BUFFER_BYTES must
    not wedge the parser.

    Before the fix, a stream of garbage that happened to contain ``AA 55``
    plus a length field decoding to e.g. 0xFFFFFFFF made _try_parse_one
    return ``(None, 0)`` ("wait for more bytes") forever. Recovery only
    happened once _trim_if_overflow rotated past the false header, which
    requires ~1 MB of subsequent traffic — at low data rates that's a
    multi-minute outage. The fix drops the spurious header byte the moment
    we see an impossible length, so the next real frame parses on time.
    """
    # length_size=4 so a single field can encode 0xFFFFFFFF (>> 1 MB cap).
    proto = dummy_protocol_config(header=b"\xAA\x55", length_size=4)
    parser = FramedParser(proto)
    # Header + frame_id (2 bytes per dummy config) + length=0xFFFFFFFF + tail.
    parser.feed(b"\xAA\x55\x00\x10\xFF\xFF\xFF\xFF" + b"\x00" * 20)
    parser.extract_all()
    # Parser must have made progress past the spurious header. Without the
    # fix the full 28 bytes would still be buffered waiting for ~4 GB more.
    assert parser.buffered_bytes < 4


def test_framed_parser_recovers_real_frame_after_impossible_length(config):
    """After the spurious-header byte is dropped, the next valid frame parses."""
    # Use the canonical 1-byte-length config; spike the length to a value
    # that still exceeds the buffer cap by feeding a header where the
    # length byte alone is fine (max 255), so this scenario only triggers
    # on the 4-byte-length protocol. Reuse the dummy config for that.
    proto = dummy_protocol_config(header=b"\xAA\x55", length_size=4)
    parser = FramedParser(proto)
    parser.feed(b"\xAA\x55\x00\x10\xFF\xFF\xFF\xFF")
    parser.extract_all()  # consumes the spurious header byte
    # Build a real frame for this 4-byte-length protocol:
    #   header AA 55 | frame_id 00 10 | length 00 00 00 04 | payload 0F A0 0B B8 | CRC
    from app.protocol import crc as crc_mod
    body = b"\xAA\x55\x00\x10\x00\x00\x00\x04\x0F\xA0\x0B\xB8"
    real_crc = crc_mod.compute("crc16_modbus", body)
    parser.feed(body + real_crc.to_bytes(2, "little"))
    packets = parser.extract_all()
    assert any(p.ok and p.frame_id == 0x0010 for p in packets), \
        "Real frame must parse after the parser resyncs past the bogus length"


# ─── Hardening: CRC-mismatch resync consumes the whole frame ────────────────


def test_framed_crc_mismatch_emits_one_error_per_frame(config):
    """N back-to-back CRC-failed frames must yield exactly N error packets.

    Before the fix, a CRC mismatch consumed only 1 byte to "resync". That
    let the parser re-latch on overlapping bytes and (especially for
    Modbus, but also for framed when the noise contained multiple AA 55
    sequences) emit many error packets per real corrupted frame, flooding
    the Qt event loop. The fix consumes the full frame, so one bad frame
    produces exactly one error event.
    """
    # Canonical layout with a deliberately wrong CRC. Same 10-byte length as
    # the real frame, so consuming total_size on failure cleanly aligns the
    # next frame.
    bad = hex_to_bytes("AA55 0010 04 0FA00BB8 0000")
    parser = create_parser(config.protocol)
    parser.feed(bad * 5)
    packets = parser.extract_all()
    error_packets = [p for p in packets if not p.ok]
    assert len(error_packets) == 5, (
        f"Expected exactly 5 CRC errors for 5 bad frames, got {len(error_packets)}"
    )
    assert all("CRC" in (p.error or "") for p in error_packets)


def test_modbus_crc_mismatch_emits_one_error_per_frame():
    """Same one-error-per-frame guarantee for ModbusRtuParser."""
    parser = ModbusRtuParser(dummy_protocol_config(parser_type="modbus_rtu"))
    # Build a valid FC3 response, then corrupt only the CRC byte.
    real = _modbus_frame(0x01, 0x03, bytes([0x02, 0x12, 0x34]))
    # real has correct CRC at [-2:]; XOR the last byte to break it.
    bad = real[:-1] + bytes([real[-1] ^ 0xFF])
    parser.feed(bad * 5)
    packets = parser.extract_all()
    error_packets = [p for p in packets if not p.ok]
    assert len(error_packets) == 5, (
        f"Expected exactly 5 CRC errors for 5 bad frames, got {len(error_packets)}"
    )
    assert all("CRC" in (p.error or "") for p in error_packets)
