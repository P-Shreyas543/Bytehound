"""Tools → Merge Session… end to end: menu action → folder → options → merge
in a child process → result; refusals; cancel; the options dialog."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from app.ui.session_merge_ui import MergeSessionDialog
from tests.test_merge_session import _record


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp, monkeypatch):
    import app.ui.main_window as mw

    monkeypatch.setattr(mw.MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = mw.MainWindow()
    warnings = []
    monkeypatch.setattr(w, "_popup_warning", lambda title, text: warnings.append(text))
    monkeypatch.setattr(w, "_popup_critical", lambda title, text: warnings.append(text))
    w._test_warnings = warnings
    yield w
    w.close()


def _pump(app, seconds, until):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until():
            return True
        time.sleep(0.02)
    return False


def _choose(monkeypatch, folder, values):
    import app.ui.session_merge_ui as ui

    monkeypatch.setattr(ui.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(folder)))
    monkeypatch.setattr(MergeSessionDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(MergeSessionDialog, "values", lambda self: values)


def test_tools_menu_merges_a_session_in_a_child_process(qapp, win, tmp_path, monkeypatch):
    folder = tmp_path / "sess"
    m = _record(folder, time.time() - 7200, 1790)
    out = tmp_path / "merged_out"
    _choose(monkeypatch, folder, ("event", "none", str(out), False))
    results = []
    monkeypatch.setattr(win, "_show_merge_result", results.extend)
    from PySide6.QtWidgets import QMenu

    tools = [mn for mn in win.menuBar().findChildren(QMenu) if mn.title().replace("&", "") == "Tools"]
    assert tools and win._merge_session_action in tools[0].actions()
    win._merge_session_action.trigger()
    assert _pump(qapp, 120, lambda: bool(results)), win._test_warnings
    assert len(results) == 1 and Path(results[0]["xlsx"]).parent == out
    assert results[0]["rows"] == sum(s["rows"]["event"] for s in m["segments"])
    assert Path(results[0]["xlsx"]).exists()
    assert not win._merge_runner.is_running()


def test_not_a_session_and_unclosed_session_are_refused(qapp, win, tmp_path):
    win._merge_session_folder(tmp_path)
    assert "not a session folder" in win._test_warnings[-1]
    folder = tmp_path / "sess"
    _record(folder, time.time() - 7200, 100)
    m = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    m["status"] = "recording"
    (folder / "session.json").write_text(json.dumps(m), encoding="utf-8")
    win._merge_session_folder(folder)
    assert "not closed" in win._test_warnings[-1]


def test_cancel_stops_the_merge_and_writes_nothing(qapp, win, tmp_path):
    folder = tmp_path / "sess"
    _record(folder, time.time() - 7200, 1790)
    out = tmp_path / "out"
    win._start_merge(folder, "event", "none", str(out), False)
    win._merge_runner.cancel()                         # before the child gets going
    cancelled = []
    win._merge_runner.cancelled.connect(lambda: cancelled.append(True))
    assert _pump(qapp, 120, lambda: bool(cancelled) or not win._merge_runner.is_running())
    assert cancelled
    assert not out.exists() or list(out.iterdir()) == []


def test_options_dialog(qapp, tmp_path):
    info = {"segments": 66, "started_utc": "2026-10-19T10:06:28", "ended_utc": "2026-10-22T03:24:21",
            "rows": {"event": 1_200_000, "fixed": 50}, "gaps": 1, "config_changes": 0}
    dlg = MergeSessionDialog(tmp_path / "session_x", info)
    assert dlg._kind.count() == 2
    assert "Data_2" in dlg._note.text()                  # over one Excel sheet: says so
    dlg._daily.setChecked(True)
    kind, split, out, keep = dlg.values()
    assert (kind, split, keep) == ("event", "day", False)
    assert Path(out) == tmp_path / "session_x" / "merged"
    dlg._kind.setCurrentIndex(1)
    assert dlg.values()[0] == "fixed"
