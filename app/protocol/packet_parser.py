"""Generic framed-packet and Modbus RTU parsers."""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import crc as crc_mod
from ..decoder.types import ProtocolConfig

_LOG = logging.getLogger("bytehound.protocol.parser")

# Hard cap on per-parser receive buffer growth. A stream that never matches the
# expected framing pattern (wrong baud rate, disconnected garbage, malicious
# input) would otherwise grow the buffer without bound. When the cap is hit we
# drop the oldest bytes and keep the most-recent tail, which preserves any
# partial frame that may be in flight at the trim boundary.
_MAX_BUFFER_BYTES = 1_000_000
_BUFFER_TAIL_BYTES = 4096  # how many recent bytes to keep when trimming


LENGTH_MEANINGS = ("payload_only", "frame_total", "header_to_crc", "payload_plus_crc")
CRC_COVERAGES = ("header_to_payload", "frame_id_to_payload", "payload_only", "full_frame")
ESCAPE_MODES = ("none", "slip", "hdlc", "cobs")


# ---------------------------------------------------------------------------
# Outer escape / unescape layer.
#
# An "escape mode" is applied AFTER the inner Bytehound frame is built and
# BEFORE inner parsing on RX. The inner frame is the normal
# header+fid+length+payload+CRC+footer byte sequence; the outer layer wraps
# that with delimiter bytes and escapes any special bytes that would
# otherwise be mistaken for delimiters.
#
# We support three industry-standard schemes:
#   * SLIP (RFC 1055): END=0xC0 delimits frames; ESC=0xDB; 0xC0 inside a
#     frame is encoded as DB DC, 0xDB as DB DD.
#   * HDLC byte-stuffing: flag=0x7E delimits frames; ESC=0x7D; 0x7E in
#     payload becomes 7D 5E, 0x7D becomes 7D 5D.
#   * COBS (Cheshire/Baker 1999): every 0x00 in the encoded frame is
#     stripped; a code byte prefixes each chunk pointing to the next zero;
#     a final 0x00 byte delimits frames.
# ---------------------------------------------------------------------------

_SLIP_END = 0xC0
_SLIP_ESC = 0xDB
_SLIP_ESC_END = 0xDC
_SLIP_ESC_ESC = 0xDD

_HDLC_FLAG = 0x7E
_HDLC_ESC = 0x7D
_HDLC_XOR = 0x20  # XOR mask applied to the escaped byte


def escape_frame(inner: bytes, mode: str) -> bytes:
    """Return the on-wire byte sequence for ``inner`` under ``mode``.

    Empty input is allowed (some schemes produce a keepalive on empty input);
    callers that don't want keepalives must check before calling.
    """
    if mode == "none":
        return inner
    if mode == "slip":
        out = bytearray([_SLIP_END])
        for b in inner:
            if b == _SLIP_END:
                out.extend((_SLIP_ESC, _SLIP_ESC_END))
            elif b == _SLIP_ESC:
                out.extend((_SLIP_ESC, _SLIP_ESC_ESC))
            else:
                out.append(b)
        out.append(_SLIP_END)
        return bytes(out)
    if mode == "hdlc":
        out = bytearray([_HDLC_FLAG])
        for b in inner:
            if b == _HDLC_FLAG or b == _HDLC_ESC:
                out.append(_HDLC_ESC)
                out.append(b ^ _HDLC_XOR)
            else:
                out.append(b)
        out.append(_HDLC_FLAG)
        return bytes(out)
    if mode == "cobs":
        return _cobs_encode(inner) + b"\x00"
    raise ValueError(f"Unsupported escape_mode: {mode!r}")


def _cobs_encode(data: bytes) -> bytes:
    """Standard COBS encode (no trailing delimiter — the caller appends 0x00)."""
    out = bytearray()
    chunk = bytearray()
    for b in data:
        if b == 0:
            out.append(len(chunk) + 1)
            out.extend(chunk)
            chunk.clear()
        else:
            chunk.append(b)
            if len(chunk) == 0xFE:
                out.append(0xFF)
                out.extend(chunk)
                chunk.clear()
    out.append(len(chunk) + 1)
    out.extend(chunk)
    return bytes(out)


def _cobs_decode(data: bytes) -> bytes:
    """COBS decode of a complete frame (excluding the trailing 0x00 delimiter).

    Returns the decoded bytes, or raises ValueError if ``data`` is malformed.
    """
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        code = data[i]
        if code == 0:
            raise ValueError("unexpected zero byte inside COBS-encoded frame")
        block_len = code - 1
        if i + 1 + block_len > n:
            raise ValueError("COBS code byte points past end of frame")
        out.extend(data[i + 1 : i + 1 + block_len])
        i += 1 + block_len
        if code != 0xFF and i < n:
            out.append(0)
    return bytes(out)


class _Unframer:
    """Streaming outer-layer unframer.

    Feed raw on-wire bytes via :meth:`feed`; complete inner-frame byte blobs
    are queued and returned by :meth:`extract_frames`. The unframer maintains
    just enough state to span chunk boundaries (escape pending across feeds,
    half-built frame, etc).
    """

    def __init__(self, mode: str) -> None:
        if mode not in ESCAPE_MODES:
            raise ValueError(f"Unsupported escape_mode: {mode!r}")
        self._mode = mode
        self._cur = bytearray()
        self._ready: list[bytes] = []
        # SLIP / HDLC: tracks whether the previous byte was the ESC marker.
        self._esc_pending = False

    def feed(self, data: bytes) -> None:
        if self._mode == "slip":
            self._feed_slip(data)
        elif self._mode == "hdlc":
            self._feed_hdlc(data)
        elif self._mode == "cobs":
            self._feed_cobs(data)
        else:
            raise ValueError(f"unframer must not be used with escape_mode={self._mode!r}")

    def extract_frames(self) -> list[bytes]:
        out = self._ready
        self._ready = []
        return out

    def _emit_current(self) -> None:
        if self._cur:
            self._ready.append(bytes(self._cur))
            self._cur.clear()

    def _feed_slip(self, data: bytes) -> None:
        for b in data:
            if b == _SLIP_END:
                self._esc_pending = False
                self._emit_current()
            elif self._esc_pending:
                if b == _SLIP_ESC_END:
                    self._cur.append(_SLIP_END)
                elif b == _SLIP_ESC_ESC:
                    self._cur.append(_SLIP_ESC)
                else:
                    # Invalid escape sequence — drop the current frame
                    self._cur.clear()
                self._esc_pending = False
            elif b == _SLIP_ESC:
                self._esc_pending = True
            else:
                self._cur.append(b)
        _trim_if_overflow(self._cur, "Unframer")

    def _feed_hdlc(self, data: bytes) -> None:
        for b in data:
            if b == _HDLC_FLAG:
                if self._esc_pending:
                    self._cur.clear()
                    self._esc_pending = False
                self._emit_current()
            elif self._esc_pending:
                self._cur.append(b ^ _HDLC_XOR)
                self._esc_pending = False
            elif b == _HDLC_ESC:
                self._esc_pending = True
            else:
                self._cur.append(b)
        _trim_if_overflow(self._cur, "Unframer")

    def _feed_cobs(self, data: bytes) -> None:
        for b in data:
            if b == 0:
                if self._cur:
                    try:
                        decoded = _cobs_decode(bytes(self._cur))
                    except ValueError:
                        decoded = b""
                    if decoded:
                        self._ready.append(decoded)
                    self._cur.clear()
            else:
                self._cur.append(b)
        _trim_if_overflow(self._cur, "Unframer")


def encode_length_field(payload_size: int, protocol: "ProtocolConfig") -> int:
    """Return the integer to write into the length field, given a payload of
    ``payload_size`` bytes and the protocol's ``length_meaning``.

    The four supported meanings count different regions of the on-wire frame:

    * ``payload_only`` — just the payload bytes (legacy default).
    * ``frame_total`` — every byte in the frame (header through footer).
    * ``header_to_crc`` — header through CRC inclusive, footer excluded.
    * ``payload_plus_crc`` — payload bytes plus CRC bytes.
    """
    h = len(protocol.header)
    f = protocol.frame_id_size
    l = protocol.length_size
    c = protocol.crc_size if protocol.crc_type != "none" else 0
    z = len(protocol.footer)
    p = payload_size
    meaning = protocol.length_meaning
    if meaning == "payload_only":
        return p
    if meaning == "frame_total":
        return h + f + l + p + c + z
    if meaning == "header_to_crc":
        return h + f + l + p + c
    if meaning == "payload_plus_crc":
        return p + c
    raise ValueError(f"Unsupported length_meaning: {meaning!r}")


def decode_length_field(length_value: int, protocol: "ProtocolConfig") -> int:
    """Inverse of :func:`encode_length_field`. Returns the payload size that
    a frame with this length-field value would carry. A negative return means
    the on-wire length value is too small to be a valid frame of this shape —
    the parser should treat the byte as garbage and resync.
    """
    h = len(protocol.header)
    f = protocol.frame_id_size
    l = protocol.length_size
    c = protocol.crc_size if protocol.crc_type != "none" else 0
    z = len(protocol.footer)
    meaning = protocol.length_meaning
    if meaning == "payload_only":
        return length_value
    if meaning == "frame_total":
        return length_value - (h + f + l + c + z)
    if meaning == "header_to_crc":
        return length_value - (h + f + l + c)
    if meaning == "payload_plus_crc":
        return length_value - c
    raise ValueError(f"Unsupported length_meaning: {meaning!r}")


def crc_coverage_bytes(
    header: bytes,
    fid_bytes: bytes,
    length_bytes: bytes,
    payload: bytes,
    footer: bytes,
    protocol: "ProtocolConfig",
) -> bytes:
    """Return the byte range over which the CRC is computed, per
    ``protocol.crc_coverage``.

    * ``header_to_payload`` — header + frame_id + length + payload.
    * ``frame_id_to_payload`` — frame_id + length + payload (header excluded).
    * ``payload_only`` — payload bytes only.
    * ``full_frame`` — everything except the CRC field itself (header +
      frame_id + length + payload + footer).
    """
    coverage = protocol.crc_coverage
    if coverage == "header_to_payload":
        return header + fid_bytes + length_bytes + payload
    if coverage == "frame_id_to_payload":
        return fid_bytes + length_bytes + payload
    if coverage == "payload_only":
        return bytes(payload)
    if coverage == "full_frame":
        return header + fid_bytes + length_bytes + payload + footer
    raise ValueError(f"Unsupported crc_coverage: {coverage!r}")


@dataclass(frozen=True)
class ParsedPacket:
    raw: bytes
    frame_id: Optional[int]
    payload: bytes
    ok: bool
    error: Optional[str] = None


def _trim_if_overflow(buf: bytearray, parser_name: str) -> bool:
    """Trim ``buf`` to the most-recent tail if it has grown past the cap.

    Returns True when a trim happened, so callers can rate-limit warnings.
    """
    if len(buf) <= _MAX_BUFFER_BYTES:
        return False
    dropped = len(buf) - _BUFFER_TAIL_BYTES
    del buf[:dropped]
    _LOG.warning(
        "%s buffer overflow: dropped %d unmatched bytes (kept last %d)",
        parser_name, dropped, len(buf),
    )
    return True


class ParserProtocol(abc.ABC):
    @abc.abstractmethod
    def feed(self, data: bytes) -> None:
        pass

    @abc.abstractmethod
    def extract_all(self) -> List[ParsedPacket]:
        pass

    @property
    @abc.abstractmethod
    def buffered_bytes(self) -> int:
        pass


class FramedParser(ParserProtocol):
    def __init__(self, protocol: ProtocolConfig) -> None:
        self.protocol = protocol
        self._buf = bytearray()
        # When escape_mode != "none" an outer unframer extracts complete
        # inner-frame blobs from the on-wire stream; those blobs are then
        # appended to ``_buf`` and the existing header-search logic processes
        # them as if no escaping had ever happened.
        self._unframer = (
            _Unframer(protocol.escape_mode)
            if protocol.escape_mode != "none"
            else None
        )

    def feed(self, data: bytes) -> None:
        if self._unframer is None:
            self._buf.extend(data)
        else:
            self._unframer.feed(data)
            for inner in self._unframer.extract_frames():
                self._buf.extend(inner)
        _trim_if_overflow(self._buf, "FramedParser")

    def extract_all(self) -> List[ParsedPacket]:
        out: List[ParsedPacket] = []
        while True:
            pkt, consumed = self._try_parse_one()
            if pkt is None and consumed == 0:
                break
            del self._buf[:consumed]
            if pkt is not None:
                out.append(pkt)
        return out

    @property
    def buffered_bytes(self) -> int:
        return len(self._buf)

    def _try_parse_one(self) -> Tuple[Optional[ParsedPacket], int]:
        pc = self.protocol
        header = pc.header
        if len(header) == 0:
            raise ValueError("Protocol header must not be empty")

        if len(self._buf) < len(header):
            return None, 0

        idx = self._buf.find(header)
        if idx == -1:
            skip = max(0, len(self._buf) - (len(header) - 1))
            return None, skip
        if idx > 0:
            return None, idx

        fixed_size = (
            len(header) + pc.frame_id_size + pc.length_size
            + pc.crc_size + len(pc.footer)
        )
        if len(self._buf) < fixed_size:
            return None, 0

        buf_mv = memoryview(self._buf)

        length_off = len(header) + pc.frame_id_size
        length_bytes_mv = buf_mv[length_off : length_off + pc.length_size]
        # length_byte_order falls back to frame_id_byte_order when not
        # explicitly configured. Backward-compatible with existing configs.
        length_endian = pc.length_byte_order or pc.frame_id_byte_order
        length_value = int.from_bytes(length_bytes_mv, length_endian)

        # Translate the on-wire length value into the payload size per the
        # protocol's length_meaning. A negative result means the value is
        # too small to be a real frame of this shape (e.g. frame_total < fixed
        # bytes) — the bytes after the header marker are garbage; drop the
        # header byte to resync.
        payload_len = decode_length_field(length_value, pc)
        if payload_len < 0:
            return None, 1

        total_size = fixed_size + payload_len
        # Ensure we don't wait for a frame so large that it would be truncated by
        # _trim_if_overflow before it can be parsed.
        if total_size > _MAX_BUFFER_BYTES - 65536:
            return None, 1

        if len(self._buf) < total_size:
            return None, 0

        raw = bytes(buf_mv[:total_size])
        fid_bytes = bytes(buf_mv[len(header) : len(header) + pc.frame_id_size])
        frame_id = int.from_bytes(buf_mv[len(header) : len(header) + pc.frame_id_size], pc.frame_id_byte_order)

        payload_off = length_off + pc.length_size
        payload = bytes(buf_mv[payload_off : payload_off + payload_len])

        crc_off = payload_off + payload_len
        received_crc = (
            int.from_bytes(buf_mv[crc_off : crc_off + pc.crc_size], pc.crc_byte_order)
            if pc.crc_size > 0 else 0
        )

        footer_off = crc_off + pc.crc_size
        footer_bytes = bytes(buf_mv[footer_off : footer_off + len(pc.footer)])

        coverage = crc_coverage_bytes(
            header, fid_bytes, bytes(length_bytes_mv), payload, footer_bytes, pc,
        )

        if pc.crc_type != "none":
            expected = crc_mod.compute(pc.crc_type, coverage)
            if expected != received_crc:
                return (
                    ParsedPacket(
                        raw=raw, frame_id=frame_id, payload=b"",
                        ok=False,
                        error=f"CRC mismatch on frame 0x{frame_id:X}: got 0x{received_crc:X}, expected 0x{expected:X}"
                    ),
                    total_size,
                )

        if pc.footer and footer_bytes != pc.footer:
            return (
                ParsedPacket(
                    raw=raw, frame_id=frame_id, payload=b"",
                    ok=False,
                    error=f"Footer mismatch on frame 0x{frame_id:X}",
                ),
                total_size,
            )

        return (
            ParsedPacket(
                raw=raw, frame_id=frame_id, payload=payload, ok=True, error=None
            ),
            total_size,
        )



class WaveshareCanParser(ParserProtocol):
    def __init__(self, protocol: ProtocolConfig) -> None:
        self.protocol = protocol
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        self._buf.extend(data)
        _trim_if_overflow(self._buf, "WaveshareCanParser")

    def extract_all(self) -> List[ParsedPacket]:
        out: List[ParsedPacket] = []
        while True:
            pkt, consumed = self._try_parse_one()
            if pkt is None and consumed == 0:
                break
            del self._buf[:consumed]
            if pkt is not None:
                out.append(pkt)
        return out

    @property
    def buffered_bytes(self) -> int:
        return len(self._buf)

    def _try_parse_one(self) -> Tuple[Optional[ParsedPacket], int]:
        if len(self._buf) < 1:
            return None, 0

        is_fixed = (
            self.protocol.waveshare_fixed_20_bytes
            or self.protocol.parser_type == "waveshare_can_20_bytes"
        )

        if is_fixed:
            # Fixed 20-byte Protocol: Frame header must be AA 55
            idx = 0
            while idx < len(self._buf):
                pos = self._buf.find(0xAA, idx)
                if pos == -1:
                    return None, len(self._buf)
                if pos + 1 < len(self._buf):
                    if self._buf[pos + 1] == 0x55:
                        if pos > 0:
                            return None, pos
                        break
                    else:
                        idx = pos + 1
                else:
                    if pos > 0:
                        return None, pos
                    return None, 0

            if len(self._buf) < 20:
                return None, 0

            # Verify checksum: (sum of first 19 bytes + 1) & 0xFF
            expected_chk = (sum(self._buf[:19]) + 1) & 0xFF
            received_chk = self._buf[19]
            if expected_chk != received_chk:
                pkt = ParsedPacket(
                    raw=bytes(self._buf[:20]),
                    frame_id=0,
                    payload=b"",
                    ok=False,
                    error=f"Waveshare CAN checksum mismatch: expected 0x{expected_chk:02X}, got 0x{received_chk:02X}",
                )
                return pkt, 20

            raw = bytes(self._buf[:20])
            dlc = self._buf[9]
            if dlc > 8:
                dlc = 8

            # Frame ID is 4 bytes at index 5, little-endian
            frame_id = int.from_bytes(self._buf[5:9], byteorder='little')
            payload = bytes(self._buf[10 : 10 + dlc])

            pkt = ParsedPacket(
                raw=raw,
                frame_id=frame_id,
                payload=payload,
                ok=True,
                error=None,
            )
            return pkt, 20

        # Variable-Length Protocol (waveshare_can):
        # Find 0xAA header index
        idx = self._buf.find(0xAA)
        if idx == -1:
            return None, len(self._buf)
        if idx > 0:
            return None, idx

        # Header AA is at index 0. We need type byte at index 1.
        if len(self._buf) < 2:
            return None, 0

        type_byte = self._buf[1]
        # Check if type_byte is valid for Variable-Length Protocol (starts with 0xC0 or 0xE0)
        if (type_byte & 0xC0) != 0xC0:
            # Not a valid frame start. Drop the 0xAA byte to resync.
            return None, 1

        is_extended = bool(type_byte & 0x20)
        dlc = type_byte & 0x0F

        if dlc > 8:
            return None, 1

        id_size = 4 if is_extended else 2
        total_size = 1 + 1 + id_size + dlc + 1  # header + type + id + data + footer

        if len(self._buf) < total_size:
            return None, 0

        footer_byte = self._buf[total_size - 1]
        if footer_byte != 0x55:
            return None, 1

        raw = bytes(self._buf[:total_size])
        id_offset = 2
        fid_bytes = bytes(self._buf[id_offset : id_offset + id_size])
        frame_id = int.from_bytes(fid_bytes, byteorder='little')
        payload_offset = id_offset + id_size
        payload = bytes(self._buf[payload_offset : payload_offset + dlc])

        pkt = ParsedPacket(
            raw=raw,
            frame_id=frame_id,
            payload=payload,
            ok=True,
            error=None,
        )
        return pkt, total_size


def create_parser(protocol: ProtocolConfig) -> ParserProtocol:
    if protocol.parser_type in ("waveshare_can", "waveshare_can_20_bytes"):
        return WaveshareCanParser(protocol)
    return FramedParser(protocol)
