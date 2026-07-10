"""Integration smoke tests for MainWindow."""
import pytest
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from unittest.mock import patch

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])

from pathlib import Path

@pytest.fixture
def main_window(qapp, config):
    window = MainWindow()
    # Mock load config to use our fixture
    with patch("app.ui.config_loader.load_config", return_value=config):
        window._load_config_from_path(Path("dummy.csv"))
    yield window
    window.close()

def test_main_window_instantiation(main_window):
    assert main_window is not None
    assert "Bytehound" in main_window.windowTitle()
    assert main_window.centralWidget() is not None

from app.protocol.packet_parser import ParsedPacket
from app.decoder.frame_decoder import DecodedFrame, DecodedSignal

def test_main_window_telemetry_flow(main_window):
    sig = DecodedSignal(
        frame_id=1, frame_name="F1", signal_name="TestSig",
        raw_value=100, scaled_value=12.5, unit="V", status="ok",
        group="BMS", index=0, enum_label=None, bit_values={}, display_value="12.5 V"
    )
    frame = DecodedFrame(
        frame_id=1, frame_name="F1", signals=[sig],
        calculations=[], error=None, warnings=[]
    )
    packet = ParsedPacket(
        ok=True, frame_id=1, payload=b"", raw=b""
    )

    main_window._on_packets_received([(packet, frame)])
    main_window._flush_ui()

    # Just verify it doesn't crash and the state is valid
    assert main_window._packet_count == 1

def test_main_window_save_state(main_window):
    # Verify save state doesn't crash
    main_window._save_window_state()

