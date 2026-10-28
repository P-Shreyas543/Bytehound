"""Tests never touch the user's real Bytehound settings (see conftest.py)."""

from __future__ import annotations

from pathlib import Path

import PySide6.QtCore as QtCore


def test_app_settings_go_to_a_temp_ini_not_the_registry(_isolated_qsettings):
    import app.ui.main_window as mw

    for cls in (QtCore.QSettings, mw.QSettings):
        s = cls("Bytehound", "Bytehound")
        assert s.format() == QtCore.QSettings.Format.IniFormat
        assert Path(s.fileName()).parent == Path(_isolated_qsettings)
    # Functions that import QSettings locally get the isolated class too.
    from PySide6.QtCore import QSettings
    assert QSettings("Bytehound", "Bytehound").format() == QtCore.QSettings.Format.IniFormat


def test_explicit_file_settings_pass_through(tmp_path):
    path = tmp_path / "x.ini"
    s = QtCore.QSettings(str(path), QtCore.QSettings.Format.IniFormat)
    s.setValue("a", 1)
    s.sync()
    assert path.exists()
