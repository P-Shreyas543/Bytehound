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
