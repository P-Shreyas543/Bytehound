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

    def feed(self, data: bytes) -> None:
        self._buf.extend(data)
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

        length_off = len(header) + pc.frame_id_size
        length_bytes = bytes(self._buf[length_off : length_off + pc.length_size])
        # length_byte_order falls back to frame_id_byte_order when not
        # explicitly configured. Backward-compatible with existing configs.
        length_endian = pc.length_byte_order or pc.frame_id_byte_order
        payload_len = int.from_bytes(length_bytes, length_endian)

        total_size = fixed_size + payload_len
        if len(self._buf) < total_size:
            return None, 0

        raw = bytes(self._buf[:total_size])
        fid_bytes = bytes(self._buf[len(header) : len(header) + pc.frame_id_size])
        frame_id = int.from_bytes(fid_bytes, pc.frame_id_byte_order)

        payload_off = length_off + pc.length_size
        payload = bytes(self._buf[payload_off : payload_off + payload_len])

        crc_off = payload_off + payload_len
        crc_bytes = bytes(self._buf[crc_off : crc_off + pc.crc_size])
        received_crc = (
            int.from_bytes(crc_bytes, pc.crc_byte_order)
            if pc.crc_size > 0 else 0
        )

        footer_off = crc_off + pc.crc_size
        footer_bytes = bytes(self._buf[footer_off : footer_off + len(pc.footer)])

        # Only "header_to_payload" is supported; the config validator
        # (config_loader._validate_protocol) rejects anything else, so
        # there's no runtime branch here. If/when additional coverages
        # are added, gate them at the validator first.
        coverage = bytes(self._buf[: payload_off + payload_len])

        if pc.crc_type != "none":
            expected = crc_mod.compute(pc.crc_type, coverage)
            if expected != received_crc:
                return (
                    ParsedPacket(
                        raw=raw, frame_id=frame_id, payload=b"",
                        ok=False,
                        error=f"CRC mismatch on frame 0x{frame_id:X}: got 0x{received_crc:X}, expected 0x{expected:X}"
                    ),
                    1,
                )

        if pc.footer and footer_bytes != pc.footer:
            return (
                ParsedPacket(
                    raw=raw, frame_id=frame_id, payload=b"",
                    ok=False,
                    error=f"Footer mismatch on frame 0x{frame_id:X}",
                ),
                1,
            )

        return (
            ParsedPacket(
                raw=raw, frame_id=frame_id, payload=payload, ok=True, error=None
            ),
            total_size,
        )


class ModbusRtuParser(ParserProtocol):
    def __init__(self, protocol: ProtocolConfig) -> None:
        self.protocol = protocol
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        self._buf.extend(data)
        _trim_if_overflow(self._buf, "ModbusRtuParser")

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
        if len(self._buf) < 4:
            return None, 0

        address = self._buf[0]
        fc = self._buf[1]

        expected_len = 0
        if fc in (3, 4):
            if len(self._buf) < 3:
                return None, 0
            byte_count = self._buf[2]
            # Modbus FC3/4 byte_count counts register data bytes. Valid range
            # is 2..250 (1..125 16-bit registers). Anything outside means we
            # latched onto random bytes — skip 1 to resync rather than waiting
            # for a length that will never arrive.
            if byte_count < 2 or byte_count > 250 or byte_count % 2 != 0:
                return None, 1
            expected_len = 5 + byte_count
        elif fc in (6, 16):
            expected_len = 8
        elif fc >= 0x80:
            expected_len = 5
        else:
            return None, 1

        if len(self._buf) < expected_len:
            return None, 0

        frame = bytes(self._buf[:expected_len])
        
        if fc in (3, 4):
            payload = frame[3:-2]
        elif fc == 6:
            payload = frame[4:6]
        elif fc == 16:
            payload = frame[4:6]
        else:
            payload = b""
            
        received_crc = int.from_bytes(frame[-2:], "little")
        expected_crc = crc_mod.compute("crc16_modbus", frame[:-2])
        
        if received_crc != expected_crc:
            return (
                ParsedPacket(
                    raw=frame, frame_id=address, payload=b"",
                    ok=False,
                    error=f"Modbus CRC mismatch: got 0x{received_crc:04X}, expected 0x{expected_crc:04X}"
                ),
                1
            )

        return (
            ParsedPacket(
                raw=frame, frame_id=address, payload=payload, ok=True, error=None
            ),
            expected_len
        )


def create_parser(protocol: ProtocolConfig) -> ParserProtocol:
    if protocol.parser_type == "modbus_rtu":
        return ModbusRtuParser(protocol)
    return FramedParser(protocol)
