"""Every ``self._popup_*`` / ``self._toast`` call in the UI must name a method
MainWindow really has. A call to a non-existent ``_popup_info`` (File →
Restore Previous Configuration with no history) raised AttributeError in
the running app; the tests that covered that path replaced the popup, so
they never noticed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def window_cls():
    QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow
    return MainWindow


def test_every_popup_and_toast_call_names_an_existing_method(window_cls):
    missing = []
    for path in sorted((ROOT / "app" / "ui").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"self\.(_popup_[a-z_]+|_toast)\(", text):
            if not hasattr(window_cls, m.group(1)):
                line = text.count("\n", 0, m.start()) + 1
                missing.append(f"{path.name}:{line} {m.group(1)}")
    assert not missing, missing


def test_restore_with_no_history_shows_a_message(qapp_win, monkeypatch, tmp_path):
    w = qapp_win
    monkeypatch.setenv("BYTEHOUND_CONFIG_HISTORY_DIR", str(tmp_path / "empty"))
    shown = []
    monkeypatch.setattr(w, "_popup_information", lambda title, text: shown.append(text))
    w._on_restore_config()                          # raised AttributeError before the fix
    assert shown == ["No earlier configuration is stored yet."]


@pytest.fixture()
def qapp_win(monkeypatch):
    QApplication.instance() or QApplication([])
    import app.ui.main_window as mw

    monkeypatch.setattr(mw.MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = mw.MainWindow()
    yield w
    w.close()
