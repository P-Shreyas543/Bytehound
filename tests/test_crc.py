"""Verify CRC16-Modbus matches instruction.md §Unit Test Sample Frame."""

from __future__ import annotations

from app.protocol import crc as crc_mod
from tests.conftest import CANONICAL_CRC_COVERAGE_HEX, CANONICAL_CRC_VALUE, hex_to_bytes


def test_crc16_modbus_canonical_frame():
    coverage = hex_to_bytes(CANONICAL_CRC_COVERAGE_HEX)
    assert crc_mod.crc16_modbus(coverage) == CANONICAL_CRC_VALUE


def test_crc16_modbus_known_vector():
    # Standard Modbus test vector: CRC of "123456789" == 0x4B37.
    assert crc_mod.crc16_modbus(b"123456789") == 0x4B37


def test_crc_dispatch_by_name():
    coverage = hex_to_bytes(CANONICAL_CRC_COVERAGE_HEX)
    assert crc_mod.compute("crc16_modbus", coverage) == CANONICAL_CRC_VALUE
    assert crc_mod.compute("none", coverage) == 0

def test_crc16_ccitt_known_vector():
    # CRC16/CCITT-FALSE of "123456789" is 0x29B1
    assert crc_mod.crc16_ccitt(b"123456789") == 0x29B1

def test_crc32_known_vector():
    # CRC32 of "123456789" is 0xCBF43926
    assert crc_mod.crc32(b"123456789") == 0xCBF43926

def test_crc_empty_input():
    assert crc_mod.crc16_modbus(b"") == 0xFFFF
    assert crc_mod.crc16_ccitt(b"") == 0xFFFF
    assert crc_mod.crc32(b"") == 0x00000000
