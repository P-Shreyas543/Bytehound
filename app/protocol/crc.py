"""Generic CRC implementations selected by name from the protocol config."""

from __future__ import annotations

import zlib


def crc16_modbus(data: bytes) -> int:
    """CRC16/MODBUS — poly 0x8005 reflected (effective 0xA001), init 0xFFFF, no xor out."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def crc16_ccitt(data: bytes) -> int:
    """CRC16/CCITT-FALSE — poly 0x1021, init 0xFFFF, no xor out, no reflection."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def compute(crc_type: str, data: bytes) -> int:
    name = crc_type.lower()
    if name == "crc16_modbus":
        return crc16_modbus(data)
    if name == "crc16_ccitt":
        return crc16_ccitt(data)
    if name == "crc32":
        return crc32(data)
    if name == "none":
        return 0
    raise ValueError(f"Unsupported crc_type: {crc_type!r}")
