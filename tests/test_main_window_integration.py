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


def test_dashboard_connect_uses_serial_settings(main_window, monkeypatch):
    captured = {}

    def fake_attempt(settings, is_retry=False):
        captured["settings"] = settings
        captured["is_retry"] = is_retry
        return True

    monkeypatch.setattr(main_window, "_attempt_connect", fake_attempt)

    main_window._on_dashboard_connect("COM7", 57600)

    assert captured["settings"].port == "COM7"
    assert captured["settings"].baud_rate == 57600
    assert captured["is_retry"] is False


def test_table_no_duplicate_units(main_window):
    sig = DecodedSignal(
        frame_id=1, frame_name="F1", signal_name="TestSig",
        raw_value=100, scaled_value=12.5, unit="V", status="ok",
        group="BMS", index=0, enum_label=None, bit_values={}, display_value="12.5 V"
    )
    calc_sig = DecodedSignal(
        frame_id=1, frame_name="F1", signal_name="Temps max",
        raw_value=2786, scaled_value=27.86, unit="°C", status="ok",
        group="Temps", index=0, enum_label=None, bit_values={}, display_value="27.86 °C",
        is_calculated=True
    )
    frame = DecodedFrame(
        frame_id=1, frame_name="F1", signals=[sig],
        calculations=[calc_sig], error=None, warnings=[]
    )
    packet = ParsedPacket(
        ok=True, frame_id=1, payload=b"", raw=b""
    )

    main_window._on_packets_received([(packet, frame)])
    main_window._flush_ui()

    row_sig = main_window._table_model.row_for_key((1, "TestSig"))
    if row_sig is not None:
        val_text = main_window._table_model.cell_text(row_sig, 6)
        unit_text = main_window._table_model.cell_text(row_sig, 7)
        assert val_text == "12.5"
        assert unit_text == "V"

    row_calc = main_window._table_model.row_for_key(("calc", "Temps max"))
    assert row_calc is not None
    calc_val = main_window._table_model.cell_text(row_calc, 6)
    calc_unit = main_window._table_model.cell_text(row_calc, 7)
    assert calc_val == "27.86"
    assert calc_unit == "°C"

