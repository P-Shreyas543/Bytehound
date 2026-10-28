"""Logging sheet (next version, owner request 2026-10-23): a configuration
says how its experiment is recorded (segments, fixed step, merge when
logging stops); activating it sets Logging Settings, and a session is
merged in the background when logging stops."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.decoder import canonical
from app.decoder.config_loader import ConfigError, load_config, read_source_tables
from app.decoder.types import LoggingDefaults

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "resources" / "config_template"

FULL = {"segment_minutes": 30, "event_log": True, "fixed_step_s": "0.5", "stale_steps": 4,
        "stale_values": "blank", "merge_on_stop": "day", "merge_keep_csv": False, "merge_kind": "fixed"}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _doc(rows):
    tables, _ = read_source_tables(TEMPLATE)
    doc = canonical.tables_to_canonical(tables)
    doc["tables"]["logging"] = rows
    return doc


def test_the_row_loads_and_blank_cells_mean_unchanged():
    cfg = load_config(_doc([FULL]))
    assert cfg.logging == LoggingDefaults(30, True, 0.5, 4, "blank", "day", False, "fixed")
    partial = load_config(_doc([{"merge_on_stop": "one"}])).logging
    assert partial == LoggingDefaults(merge_on_stop="one")
    assert load_config(_doc([{"fixed_step_s": "off"}])).logging.fixed_step_s == 0.0
    assert load_config(_doc([])).logging is None
    assert load_config(TEMPLATE).logging is None                 # old configurations are unaffected


@pytest.mark.parametrize("row, text", [
    ({"segment_minutes": 5}, "outside 15..1440"),
    ({"fixed_step_s": "fast"}, "not a number"),
    ({"stale_values": "zero"}, "must be one of hold, blank"),
    ({"merge_on_stop": "weekly"}, "must be one of none, one, day"),
    ({"merge_kind": "raw"}, "must be one of event, fixed, both"),
])
def test_bad_values_are_explained(row, text):
    with pytest.raises(ConfigError, match=text):
        load_config(_doc([row]))


def test_sheet_round_trips_through_every_format(tmp_path):
    doc = _doc([FULL])
    expected = load_config(doc).logging
    for target in (tmp_path / "c.json", tmp_path / "c.xlsx", tmp_path / "csv"):
        canonical.export(doc, target)
        assert load_config(target).logging == expected, target


def _ini(tmp_path, monkeypatch):
    import app.ui.main_window as mw

    ini = str(tmp_path / "settings.ini")

    class IsolatedSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(ini, QSettings.Format.IniFormat)

    monkeypatch.setattr(mw, "QSettings", IsolatedSettings)
    monkeypatch.setattr(mw.MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_popup_warning", lambda self, *a, **k: None)
    monkeypatch.setattr(mw.MainWindow, "_popup_critical", lambda self, *a, **k: None)
    return mw


def test_activating_the_configuration_sets_logging_settings(qapp, tmp_path, monkeypatch):
    mw = _ini(tmp_path, monkeypatch)
    path = tmp_path / "exp.json"
    canonical.export(_doc([FULL]), path)
    win = mw.MainWindow()
    try:
        win._settings.setValue("logging/disk_warn_gb", 7)       # not in the sheet: untouched
        win._load_config_from_path(path, suppress_popups=True)
        s = win._settings
        assert int(s.value("logging/segment_minutes")) == 30
        assert s.value("logging/fixed_step_enabled") == "true" and float(s.value("logging/fixed_step_s")) == 0.5
        assert int(s.value("logging/stale_steps")) == 4 and s.value("logging/stale_policy") == "blank"
        assert s.value("logging/merge_on_stop") == "day" and s.value("logging/merge_keep_csv") == "false"
        assert s.value("logging/merge_kind") == "fixed"
        assert int(s.value("logging/disk_warn_gb")) == 7
        settings = win._session_settings_from_qsettings()
        assert settings.segment_seconds == 1800 and settings.fixed_step_s == 0.5
    finally:
        win.close()


def test_logging_settings_dialog_shows_and_saves_the_merge_option(qapp, tmp_path):
    from app.ui.dialogs import LoggingSettingsDialog

    s = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    s.setValue("logging/merge_on_stop", "day")
    s.setValue("logging/merge_keep_csv", "false")
    dlg = LoggingSettingsDialog(s)
    assert dlg._merge_combo.currentIndex() == 2 and not dlg._merge_csv_chk.isChecked()
    assert dlg._merge_kind_combo.currentIndex() == 0                  # default: both logs
    dlg._merge_combo.setCurrentIndex(1)
    dlg._merge_kind_combo.setCurrentIndex(2)
    dlg._merge_csv_chk.setChecked(True)
    dlg._on_accept()
    assert s.value("logging/merge_on_stop") == "one" and s.value("logging/merge_keep_csv") == "true"
    assert s.value("logging/merge_kind") == "fixed"


def test_a_session_is_merged_when_logging_stops(qapp, tmp_path, monkeypatch):
    from app.protocol.packet_builder import build_packet
    from app.serial_io.serial_worker import SerialSettings
    from app.serial_logging.session import SessionSettings
    from tests.test_session_gui import Device, _pump

    mw = _ini(tmp_path, monkeypatch)
    config = load_config(TEMPLATE)
    frames = [build_packet(config.protocol, fid, bytes(f.payload_length)) for fid, f in config.frames.items()]
    dev = Device(frames)
    win = mw.MainWindow()
    lines = []
    monkeypatch.setattr(win, "_log_activity", lambda text, *a, **k: lines.append(text))
    try:
        win._load_config_from_path(TEMPLATE, suppress_popups=True)
        win._settings.setValue("logging/merge_on_stop", "one")
        win._settings.setValue("logging/merge_keep_csv", "true")
        monkeypatch.setattr(win, "_session_settings_from_qsettings",
                            lambda: SessionSettings(segment_seconds=3600, fixed_step_s=0.5))
        assert win._attempt_connect(SerialSettings(port="127.0.0.1", connection_type="tcp", host="127.0.0.1",
                                                   port_num=dev.port, auto_reconnect=False))
        folder = tmp_path / "session"
        assert win._start_logging_file(folder)
        assert _pump(qapp, 10, until=lambda: win._packet_count > 50)
        win._stop_logging()
        assert _pump(qapp, 180, until=lambda: any(t.startswith("[SESSION] Merged session (fixed log)")
                                                  for t in lines)), lines
    finally:
        win._disconnect(reason="test done")
        win.close()
        dev.close()
        _pump(qapp, 0.3)
    merged = folder / "merged"
    names = sorted(p.name for p in merged.iterdir())
    assert names == ["session_event.csv", "session_event.xlsx", "session_fixed.csv", "session_fixed.xlsx"], names
    assert any("(event log)" in t for t in lines if t.startswith("[SESSION] Merged"))
    assert not any(t.startswith("[WARN] Automatic merge") for t in lines)
