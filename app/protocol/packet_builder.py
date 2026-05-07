"""Generic framed-packet builder. Mirrors `packet_parser` in reverse.

Used by the TX command builder. Takes a frame ID + payload and produces the
fully-wrapped packet (header, frame_id, length, payload, CRC, footer) per
the active `ProtocolConfig`.
"""

from __future__ import annotations

from . import crc as crc_mod
from ..decoder.types import ProtocolConfig


def build_packet(protocol: ProtocolConfig, frame_id: int, payload: bytes) -> bytes:
    if protocol.parser_type == "modbus_rtu":
        return build_modbus_packet(protocol, frame_id, payload)
    
    pc = protocol
    if pc.length_meaning != "payload_only":
        raise ValueError(f"Unsupported length_meaning: {pc.length_meaning!r}")
    if pc.crc_coverage != "header_to_payload":
        raise ValueError(f"Unsupported crc_coverage: {pc.crc_coverage!r}")

    fid_bytes = frame_id.to_bytes(pc.frame_id_size, pc.frame_id_byte_order)
    max_payload = (1 << (8 * pc.length_size)) - 1
    if len(payload) > max_payload:
        raise ValueError(
            f"Payload is {len(payload)} bytes but length field can hold {max_payload}"
        )
    length_bytes = len(payload).to_bytes(pc.length_size, pc.frame_id_byte_order)

    coverage = pc.header + fid_bytes + length_bytes + payload

    if pc.tx_pad_length is not None:
        total_len_without_crc = len(coverage)
        target_total_len = pc.tx_pad_length - pc.crc_size - len(pc.footer)
        if target_total_len > total_len_without_crc:
            padding = b'\x00' * (target_total_len - total_len_without_crc)
            coverage += padding
            # update payload length byte if length_meaning is payload_only?
            # actually if we pad, usually padding is part of payload or just extra bytes.
            # let's just append the padding.

    if pc.crc_type == "none":
        crc_bytes = b""
    else:
        crc_value = crc_mod.compute(pc.crc_type, coverage)
        crc_bytes = crc_value.to_bytes(pc.crc_size, pc.crc_byte_order)

    return coverage + crc_bytes + pc.footer


def build_modbus_packet(protocol: ProtocolConfig, target_id: int, payload: bytes) -> bytes:
    """Build a Modbus RTU request. target_id is used to construct the frame.
    If payload is empty, we assume it's a read request (FC 03).
    If payload is not empty, we assume it's a write request (FC 06 or 16).
    """
    node_address = 1  # Default node address since it's not configured
    
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
