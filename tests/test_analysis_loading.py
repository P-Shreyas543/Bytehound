"""Analysis Suite loading (owner request 2026-10-22): a workbook and its CSV
twin give the same data; the twin is preferred (~100x faster); progress is
reported against the workbook's recorded row count; loading can be
cancelled; the Analysis Suite shows a progress dialog while files load."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from app.serial_logging.session_merge import merge
from app.ui.log_io import LogLoaderThread
from tests.test_merge_session import _record


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def merged(tmp_path_factory, qapp):
    """A merged session saved as workbook + CSV twin."""
    base = tmp_path_factory.mktemp("merged")
    folder = base / "sess"
    _record(folder, time.time() - 7200, 1790)
    out = merge(folder, out=base / "out", keep_csv=True)[0]
    return Path(out["xlsx"]), Path(out["csv"]), out["rows"]


def _load(path, monkeypatch=None, chunk=None, cancel=False):
    t = LogLoaderThread(str(path), "id", "#fff")
    if chunk is not None:
        t._XLSX_CHUNK = chunk
    if cancel:
        t.isInterruptionRequested = lambda: True
    got = {"status": [], "pct": [], "entry": None, "cancelled": False, "error": None}
    t.sigStatus.connect(got["status"].append)
    t.sigProgress.connect(got["pct"].append)
    t.sigFinished.connect(lambda _i, _p, e: got.__setitem__("entry", e))
    t.sigCancelled.connect(lambda _p: got.__setitem__("cancelled", True))
    t.error.connect(lambda _p, m: got.__setitem__("error", m))
    t.run()                                   # synchronously, on this thread
    return got


def test_workbook_and_its_csv_give_the_same_data(merged, tmp_path):
    xlsx, csv_path, rows = merged
    alone = tmp_path / xlsx.name
    shutil.copy2(xlsx, alone)                 # no CSV next to this copy: read the workbook
    from_xlsx = _load(alone)["entry"]
    from_csv = _load(csv_path)["entry"]
    assert from_xlsx is not None and from_csv is not None
    assert len(from_xlsx.elapsed) == len(from_csv.elapsed) == rows
    assert np.allclose(from_xlsx.elapsed, from_csv.elapsed)
    assert from_xlsx.start_timestamp == from_csv.start_timestamp is not None   # clock time kept
    assert set(from_xlsx.columns) == set(from_csv.columns)
    for name, arr in from_csv.columns.items():
        assert np.allclose(from_xlsx.columns[name], arr, equal_nan=True), name


def test_the_csv_twin_is_used_and_the_workbook_name_kept(merged):
    xlsx, csv_path, rows = merged
    got = _load(xlsx)
    assert any("the CSV saved with this workbook" in s for s in got["status"])
    assert got["entry"].path == str(xlsx) and len(got["entry"].elapsed) == rows


def test_workbook_progress_counts_up_to_the_recorded_rows(merged, tmp_path):
    xlsx, _csv, rows = merged
    alone = tmp_path / xlsx.name
    shutil.copy2(xlsx, alone)
    got = _load(alone, chunk=50)
    pcts = [p for p in got["pct"] if p >= 0]
    assert pcts == sorted(pcts) and pcts[-1] == 100 and len(pcts) >= 3
    assert any(f"of {rows:,} rows" in s for s in got["status"])


def test_cancel_stops_the_load(merged, tmp_path):
    xlsx, _csv, _rows = merged
    alone = tmp_path / xlsx.name
    shutil.copy2(xlsx, alone)
    got = _load(alone, chunk=50, cancel=True)
    assert got["cancelled"] and got["entry"] is None and got["error"] is None


def test_analysis_suite_shows_progress_while_loading(qapp, merged, monkeypatch):
    import app.ui.analysis_suite as asu

    monkeypatch.setattr(asu.AnalysisSuiteWindow, "_popup_warning", lambda self, *a, **k: None)
    win = asu.AnalysisSuiteWindow()
    try:
        xlsx, _csv, _rows = merged
        seen = []
        orig = asu.AnalysisSuiteWindow._show_load_dialog

        def show(self):
            orig(self)
            seen.append(self._load_dialog is not None and self._load_dialog.isVisible())
        monkeypatch.setattr(asu.AnalysisSuiteWindow, "_show_load_dialog", show)
        win._load_single_path(str(xlsx))
        win._load_dialog_timer.setInterval(0)                  # show at once for the test
        win._load_dialog_timer.start()
        end = time.monotonic() + 60
        while time.monotonic() < end and (win._load_states or not win._logs):
            QApplication.processEvents()
            time.sleep(0.01)
        assert seen == [True]                                   # shown while loading
        assert win._logs and getattr(win, "_load_dialog", None) is None   # closed when done
    finally:
        win.close()
