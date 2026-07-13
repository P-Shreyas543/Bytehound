"""Tests for ConnectionDialog field-priority behaviour.

The dialog's pre-population is a small but easy-to-break interaction:
QSettings (user's last choice) should win over the config's SerialDefaults,
and SerialDefaults should win over the hard-coded SerialDefaults() fallback.
Tested headlessly under offscreen Qt so the dialog never actually paints.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.decoder.types import SerialDefaults
from app.ui.dialogs import ConnectionDialog


@pytest.fixture(scope="module")
def qapp():
    # One QApplication for all dialog tests in this module.
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def fresh_settings(tmp_path):
    """A QSettings backed by an .ini file in tmp_path so each test starts
    from a clean slate without touching the user's real registry/plist."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_connection_dialog_uses_config_defaults_on_fresh_settings(qapp, fresh_settings):
    """With no QSettings stored, the dialog pre-populates from config_defaults."""
    cd = SerialDefaults(baud_rate=9600, data_bits=8, stop_bits=2.0, parity="E", timeout_ms=250)
    dlg = ConnectionDialog(fresh_settings, config_defaults=cd)
    settings = dlg.get_settings()
    assert settings.baud_rate == 9600
    assert settings.data_bits == 8
    assert settings.stop_bits == 2.0
    assert settings.parity == "E"
    assert settings.timeout_ms == 250


def test_connection_dialog_qsettings_wins_over_config_defaults(qapp, fresh_settings):
    """If QSettings already has a value, it overrides the config default."""
    fresh_settings.setValue("conn/baud", "57600")
    fresh_settings.setValue("conn/parity", "O")
    cd = SerialDefaults(baud_rate=9600, parity="E")
    dlg = ConnectionDialog(fresh_settings, config_defaults=cd)
    settings = dlg.get_settings()
    assert settings.baud_rate == 57600   # from QSettings, not config
    assert settings.parity == "O"        # from QSettings, not config


def test_connection_dialog_without_config_defaults_uses_serialdefaults_class_defaults(qapp, fresh_settings):
    """Omitting config_defaults falls back to the SerialDefaults() class defaults
    (baud=115200, data=8, stop=1, parity=N, timeout=100) — same as before."""
    dlg = ConnectionDialog(fresh_settings)
    settings = dlg.get_settings()
    assert settings.baud_rate == 115200
    assert settings.data_bits == 8
    assert settings.stop_bits == 1.0
    assert settings.parity == "N"
    assert settings.timeout_ms == 100

def test_serial_port_auto_discovery_formatting_and_sorting(monkeypatch):
    from app.serial_io.serial_worker import available_ports
    from serial.tools import list_ports
    
    class MockPortInfo:
        def __init__(self, device, description, manufacturer, vid, pid):
            self.device = device
            self.description = description
            self.manufacturer = manufacturer
            self.vid = vid
            self.pid = pid
            
    mock_ports = [
        MockPortInfo("COM1", "Generic Serial Port", "Microsoft", None, None),
        MockPortInfo("COM3", "USB Serial Port", "FTDI", 0x0403, 0x6001),
        MockPortInfo("COM7", "STMicroelectronics Virtual COM Port", "STMicroelectronics", 0x0483, 0x5740),
    ]
    
    monkeypatch.setattr(list_ports, "comports", lambda: mock_ports)
    
    ports = list(available_ports())
    
    assert len(ports) == 3
    
    assert ports[0][0] == "COM3"
    assert "Mfg: FTDI" in ports[0][1]
    assert "VID:PID=0403:6001" in ports[0][1]
    
    assert ports[1][0] == "COM7"
    assert "Mfg: STMicroelectronics" in ports[1][1]
    assert "VID:PID=0483:5740" in ports[1][1]
    
    assert ports[2][0] == "COM1"
    assert "Generic Serial Port" in ports[2][1]
    assert "Mfg: Microsoft" in ports[2][1]
    assert "VID:PID" not in ports[2][1]
