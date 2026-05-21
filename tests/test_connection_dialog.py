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
