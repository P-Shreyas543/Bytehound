"""Generic framed-packet builder. Mirrors `packet_parser` in reverse.

Used by the TX command builder. Takes a frame ID + payload and produces the
fully-wrapped packet (header, frame_id, length, payload, CRC, footer) per
the active `ProtocolConfig`.
"""

from __future__ import annotations

from . import crc as crc_mod
from .packet_parser import encode_length_field, crc_coverage_bytes, escape_frame
from ..decoder.types import ProtocolConfig


def build_waveshare_can_packet(protocol: ProtocolConfig, frame_id: int, payload: bytes) -> bytes:
    dlc = len(payload)
    if dlc > 8:
        raise ValueError(f"Waveshare CAN payload must be <= 8 bytes (got {dlc})")
    
    is_extended = (protocol.frame_id_size == 4) or (frame_id > 0x7FF)
    type_byte = 0xE0 | dlc if is_extended else 0xC0 | dlc
    
    packet = bytearray()
    packet.append(0xAA)
    packet.append(type_byte)
    if is_extended:
        packet.extend(frame_id.to_bytes(4, byteorder='little'))
    else:
        packet.extend(frame_id.to_bytes(2, byteorder='little'))
    packet.extend(payload)
    packet.append(0x55)
    return bytes(packet)


def build_packet(protocol: ProtocolConfig, frame_id: int, payload: bytes) -> bytes:
    if protocol.parser_type == "modbus_rtu":
        return build_modbus_packet(protocol, frame_id, payload)
    if protocol.parser_type == "waveshare_can":
        return build_waveshare_can_packet(protocol, frame_id, payload)

    pc = protocol
    fid_bytes = frame_id.to_bytes(pc.frame_id_size, pc.frame_id_byte_order)
    max_length_value = (1 << (8 * pc.length_size)) - 1
    length_value = encode_length_field(len(payload), pc)
    if length_value > max_length_value or length_value < 0:
        raise ValueError(
            f"Encoded length field is {length_value} but length_size={pc.length_size} "
            f"can only hold 0..{max_length_value}; reduce payload, increase length_size, "
            f"or switch length_meaning."
        )
    # length_byte_order falls back to frame_id_byte_order when unset, matching
    # the parser's behaviour so build/parse round-trips are byte-exact.
    length_endian = pc.length_byte_order or pc.frame_id_byte_order
    length_bytes = length_value.to_bytes(pc.length_size, length_endian)

    pre_crc = pc.header + fid_bytes + length_bytes + payload

    if pc.tx_pad_length is not None:
        target_total_len = pc.tx_pad_length - pc.crc_size - len(pc.footer)
        if target_total_len < 0:
            raise ValueError(
                f"tx_pad_length={pc.tx_pad_length} is smaller than CRC+footer "
                f"({pc.crc_size + len(pc.footer)} bytes); cannot pad"
            )
        unpadded_total = len(pre_crc) + pc.crc_size + len(pc.footer)
        if unpadded_total > pc.tx_pad_length:
            raise ValueError(
                f"TX frame (id=0x{frame_id:X}) is {unpadded_total} bytes but "
                f"tx_pad_length is {pc.tx_pad_length}; increase tx_pad_length "
                f"or shrink the command payload"
            )
        if target_total_len > len(pre_crc):
            # The padding is conceptually part of the on-wire payload region;
            # extend `payload` so the CRC coverage helper sees the same bytes
            # the parser would on the wire.
            payload = payload + b'\x00' * (target_total_len - len(pre_crc))
            pre_crc = pc.header + fid_bytes + length_bytes + payload

    if pc.crc_type == "none":
        crc_bytes = b""
    else:
        coverage = crc_coverage_bytes(
            pc.header, fid_bytes, length_bytes, payload, pc.footer, pc,
        )
        crc_value = crc_mod.compute(pc.crc_type, coverage)
        crc_bytes = crc_value.to_bytes(pc.crc_size, pc.crc_byte_order)

    inner = pre_crc + crc_bytes + pc.footer
    return escape_frame(inner, pc.escape_mode)


def build_modbus_packet(protocol: ProtocolConfig, target_id: int, payload: bytes) -> bytes:
    """Build a Modbus RTU request. target_id is used to construct the frame.
    If payload is empty, we assume it's a read request (FC 03).
    If payload is not empty, we assume it's a write request (FC 06 or 16).
    """
    node_address = protocol.modbus_node_address

    if not payload:
        # Read Holding Registers (FC 03)
        # target_id is the starting address. We'll default to reading 1 register.
        # The polling engine should ideally pass how many to read, but we'll assume 1 for now if empty.
        fc = 3
        req = bytes([node_address, fc]) + target_id.to_bytes(2, "big") + (1).to_bytes(2, "big")
    else:
        # Write Single Register (FC 06) if payload is 2 bytes
        # or Write Multiple Registers (FC 16) if more
        if len(payload) == 2:
            fc = 6
            req = bytes([node_address, fc]) + target_id.to_bytes(2, "big") + payload
        else:
            fc = 16
            qty = len(payload) // 2
            req = bytes([node_address, fc]) + target_id.to_bytes(2, "big") + qty.to_bytes(2, "big") + bytes([len(payload)]) + payload

    crc = crc_mod.compute("crc16_modbus", req)
    return req + crc.to_bytes(2, "little")
