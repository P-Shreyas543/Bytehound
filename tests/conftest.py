"""Shared pytest fixtures for the Bytehound test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.decoder.config_loader import load_config
from app.decoder.types import FrameConfig, ProtocolConfig

def dummy_protocol_config(parser_type="framed", **kwargs) -> ProtocolConfig:
    d = dict(
        profile_name="test", header=b"\\xAA\\x55", frame_id_size=2,
        frame_id_byte_order="big", length_size=1, length_meaning="payload_only",
        crc_type="crc16_modbus", crc_size=2, crc_byte_order="little",
        crc_coverage="header_to_payload", footer=b"", escape_mode="none",
        enabled=True, parser_type=parser_type,
        tx_pad_length=None, inter_frame_delay_ms=10
    )
    d.update(kwargs)
    return ProtocolConfig(**d)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCES = PROJECT_ROOT / "app" / "resources"
DEFAULT_CONFIG = PROJECT_ROOT / "tests" / "fixtures" / "canonical_config"


@pytest.fixture(autouse=True)
def _delete_main_windows():
    """Destroy every MainWindow a test created once it finishes.

    Fixtures only close() their windows, and a closed QMainWindow is not
    deleted. Dozens piled up over a run, and any app-wide restyle
    (qdarktheme.setup_theme in the theme tests) had to repolish all of them:
    the suite stalled for hours at 100% CPU in test_boot_smoke.
    """
    yield
    mw_module = sys.modules.get("app.ui.main_window")
    if mw_module is None:
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    stale = [w for w in app.topLevelWidgets() if isinstance(w, mw_module.MainWindow)]
    for w in stale:
        w.deleteLater()
    if stale:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def resources_dir() -> Path:
    return RESOURCES


@pytest.fixture
def config() -> FrameConfig:
    return load_config(DEFAULT_CONFIG)


# The canonical milestone-1 frame from instruction.md §Unit Test Sample Frame:
#   header AA 55, frame_id 0x0010, length 4, payload 0F A0 0B B8, CRC BE 70.
CANONICAL_FRAME_HEX = "AA55001004 0FA00BB8 BE70"
CANONICAL_PAYLOAD_HEX = "0FA00BB8"
CANONICAL_FRAME_ID = 0x0010
CANONICAL_CRC_LE = b"\xBE\x70"           # transmitted little-endian
CANONICAL_CRC_VALUE = 0x70BE             # expected CRC16-Modbus result
CANONICAL_CRC_COVERAGE_HEX = "AA55001004 0FA00BB8"


def hex_to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str.replace(" ", ""))
