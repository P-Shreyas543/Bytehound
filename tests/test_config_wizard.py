"""Tests for the Visual Protocol & Frame Configuration Wizard."""

import pytest
from PySide6.QtWidgets import QApplication
from app.ui.config_wizard import ProtocolWizardDialog
from app.decoder.config_loader import load_config


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_protocol_wizard_init_and_navigation(qapp):
    dlg = ProtocolWizardDialog()
    assert dlg.stack.currentIndex() == 0
    assert dlg.back_btn.isEnabled() is False
    assert not dlg.next_btn.isHidden()

    # Navigate to Step 2 (Frames)
    dlg._on_next()
    assert dlg.stack.currentIndex() == 1
    assert dlg.back_btn.isEnabled() is True

    # Navigate to Step 3 (Variables / RX)
    dlg._on_next()
    assert dlg.stack.currentIndex() == 2

    # Navigate to Step 4 (TX Commands)
    dlg._on_next()
    assert dlg.stack.currentIndex() == 3
    assert not dlg.next_btn.isHidden()

    # Navigate to Step 5 (Summary & Export)
    dlg._on_next()
    assert dlg.stack.currentIndex() == 4
    assert dlg.next_btn.isHidden()
    assert "Profile Name:" in dlg.summary_label.text()
    assert "Transmit Commands (TX)" in dlg.summary_label.text()

    # Back navigation
    dlg._on_prev()
    assert dlg.stack.currentIndex() == 3


def test_protocol_wizard_parser_type_toggle(qapp):
    dlg = ProtocolWizardDialog()

    # Switch to Waveshare CAN Variable Length
    dlg.set_parser_type("waveshare_can_variable_length")
    assert dlg._get_selected_parser_type() == "waveshare_can_variable_length"
    assert dlg.baud_combo.currentText() == "2000000"
    assert dlg.header_hex_edit.text() == "AA"
    assert dlg.crc_combo.currentText() == "none"

    # Switch to Waveshare CAN Fixed 20 Bytes
    dlg.set_parser_type("waveshare_can_20_bytes")
    assert dlg._get_selected_parser_type() == "waveshare_can_20_bytes"
    assert dlg.baud_combo.currentText() == "2000000"
    assert dlg.header_hex_edit.text() == "AA 55"
    assert dlg.crc_combo.currentText() == "none"

    # Switch back to Framed
    dlg.set_parser_type("framed")
    assert dlg._get_selected_parser_type() == "framed"
    assert dlg.baud_combo.currentText() == "115200"
    assert dlg.header_hex_edit.isEnabled() is True
    assert dlg.crc_combo.isEnabled() is True


def test_protocol_wizard_save_and_load(qapp, tmp_path, monkeypatch):
    dlg = ProtocolWizardDialog()

    out_file = tmp_path / "test_wizard_complete.xlsx"
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(out_file), "Excel Files (*.xlsx)"),
    )
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.information",
        lambda *args, **kwargs: None,
    )

    dlg._save_wizard_config()
    assert out_file.exists()

    # Verify that the generated workbook loads cleanly with Bytehound's config loader
    cfg = load_config(out_file)
    assert cfg.protocol.parser_type == "framed"
    assert cfg.serial_defaults.baud_rate == 115200
    assert len(cfg.frames) >= 1
    signal_names = [s.signal_name for s in cfg.all_signals]
    assert len(signal_names) >= 1
    assert "Pack Voltage" in signal_names or "Voltage" in signal_names
