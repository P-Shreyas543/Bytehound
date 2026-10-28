"""Tools → Merge Session… (owner request 2026-10-22).

Joins a recorded session's hourly segments into one workbook, or one per
day, so an analyst does not have to stitch 24+ files together. The merge
itself (``app/serial_logging/session_merge.py``) runs in a child process:
compiling hundreds of MB of xlsx is minutes of Python work and would
otherwise stall the GUI (and a running capture) through the GIL.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..serial_logging.session_merge import MergeError, merge_job, session_summary

_EXCEL_ROWS = 1_048_575          # data rows per sheet (one header row)
_LOG_LABELS = {"event": "Event log (one row per received cycle)", "fixed": "Fixed-step log"}


class MergeSessionDialog(QDialog):
    """Options for one merge: which log, one file or one per day, where."""

    def __init__(self, folder: Path, info: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Merge Session")
        self.setMinimumWidth(520)
        self._folder = Path(folder)
        root = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Session:", QLabel(f"<b>{self._folder.name}</b>"))
        span = f"{info.get('started_utc', '')[:19].replace('T', ' ')} → {info.get('ended_utc', '')[:19].replace('T', ' ')} UTC"
        form.addRow("Recorded:", QLabel(span))
        extra = []
        if info.get("gaps"):
            extra.append(f"{info['gaps']} gap(s)")
        if info.get("config_changes"):
            extra.append(f"{info['config_changes']} configuration change(s): one part per configuration")
        form.addRow("Segments:", QLabel(f"{info.get('segments', 0)}" + (f"  ({'; '.join(extra)})" if extra else "")))

        self._kind = QComboBox(self)
        for kind, rows in info.get("rows", {}).items():
            self._kind.addItem(f"{_LOG_LABELS.get(kind, kind)} — {rows:,} rows", (kind, rows))
        form.addRow("Log:", self._kind)

        self._one = QRadioButton("One workbook for the whole session", self)
        self._daily = QRadioButton("One workbook per day (split at midnight, local time)", self)
        self._one.setChecked(True)
        box = QVBoxLayout()
        box.addWidget(self._one)
        box.addWidget(self._daily)
        form.addRow("Output:", box)

        self._csv = QCheckBox("Also keep the merged CSV (the Analysis Suite opens it ~100× faster)", self)
        self._csv.setChecked(True)
        form.addRow("", self._csv)

        self._out = QLineEdit(str(self._folder / "merged"), self)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self._out, 1)
        row.addWidget(browse)
        form.addRow("Save to:", row)
        root.addLayout(form)

        self._note = QLabel(self)
        self._note.setWordWrap(True)
        root.addWidget(self._note)
        self._kind.currentIndexChanged.connect(self._update_note)
        self._one.toggled.connect(self._update_note)
        self._update_note()

        buttons = QDialogButtonBox(self)
        ok = buttons.addButton("Merge", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Save merged workbooks to", self._out.text())
        if path:
            self._out.setText(path)

    def _update_note(self) -> None:
        data = self._kind.currentData()
        rows = data[1] if data else 0
        if self._one.isChecked() and rows > _EXCEL_ROWS:
            self._note.setText(f"{rows:,} rows exceed one Excel sheet: the workbook continues on Data_2, "
                               "Data_3 …. One workbook per day keeps each file on one sheet.")
        elif self._one.isChecked() and rows > 200_000:
            self._note.setText("A workbook this large opens slowly in Excel; one workbook per day is easier "
                               "to work with.")
        else:
            self._note.setText("The session folder is not changed.")

    def values(self) -> tuple:
        kind = (self._kind.currentData() or ("event", 0))[0]
        split = "none" if self._one.isChecked() else "day"
        return kind, split, self._out.text().strip(), self._csv.isChecked()


class MergeRunner(QObject):
    """Runs ``merge_job`` in a child process and relays its messages."""

    progress = Signal(str, int, int)
    finished = Signal(list)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._ctx = mp.get_context("spawn")
        self._queue = None
        self._cancel = None
        self._proc = None
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll)
        self._done = False

    def start(self, folder: Path, kind: str, split: str, out: str, keep_csv: bool) -> None:
        self._queue = self._ctx.Queue()
        self._cancel = self._ctx.Event()
        self._proc = self._ctx.Process(
            target=merge_job, name="BytehoundMerge", daemon=True,
            args=(str(folder), kind, split, out or None, keep_csv, self._queue, self._cancel),
        )
        self._proc.start()
        self._timer.start()

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

    def is_running(self) -> bool:
        return self._proc is not None and not self._done

    def _finish(self) -> None:
        self._done = True
        self._timer.stop()
        if self._proc is not None:
            self._proc.join(5)
            if self._proc.is_alive():
                self._proc.terminate()

    def _poll(self) -> None:
        import queue as _queue

        while True:
            try:
                msg = self._queue.get_nowait()
            except _queue.Empty:
                break
            kind = msg[0]
            if kind == "progress":
                self.progress.emit(msg[1], int(msg[2]), int(msg[3]))
            elif kind == "done":
                self._finish()
                self.finished.emit(list(msg[1]))
                return
            elif kind == "cancelled":
                self._finish()
                self.cancelled.emit()
                return
            elif kind == "error":
                self._finish()
                self.failed.emit(str(msg[1]))
                return
        if self._proc is not None and not self._proc.is_alive() and not self._done:
            self._finish()
            self.failed.emit(f"The merge process stopped unexpectedly (exit code {self._proc.exitcode}).")


class SessionMergeMixin:
    """MainWindow mixin: Tools → Merge Session…"""

    def _on_merge_session(self) -> None:
        from .main_window import APP_NAME

        self._log_activity("[ACTION] Merge Session")
        if getattr(self, "_merge_runner", None) is not None and self._merge_runner.is_running():
            self._popup_warning("Merge Session", "A merge is already running.")
            return
        start_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        folder = QFileDialog.getExistingDirectory(self, "Select a session folder (it contains session.json)",
                                                  str(start_dir))
        if not folder:
            return
        self._merge_session_folder(Path(folder))

    def _merge_session_folder(self, folder: Path) -> None:
        try:
            info = session_summary(folder)
        except MergeError as exc:
            self._popup_warning("Merge Session", str(exc))
            return
        active = getattr(self, "_session_log", None)
        if info["status"] == "recording":
            same = active is not None and Path(active.folder).resolve() == folder.resolve()
            self._popup_warning("Merge Session", "This session is still recording. Stop logging first."
                                if same else "This session was not closed (still marked as recording). "
                                "Restart Bytehound to recover it, then merge.")
            return
        if not info["rows"]:
            self._popup_warning("Merge Session", "This session has no event or fixed-step log to merge.")
            return
        dlg = MergeSessionDialog(folder, info, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        kind, split, out, keep_csv = dlg.values()
        self._start_merge(folder, kind, split, out, keep_csv)

    def _start_merge(self, folder: Path, kind: str, split: str, out: str, keep_csv: bool) -> None:
        runner = MergeRunner(self)
        self._merge_runner = runner
        progress = QProgressDialog("Merging session — preparing…", "Cancel", 0, 100, self)
        progress.setWindowTitle("Merge Session")
        progress.setWindowModality(Qt.WindowModality.NonModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        self._merge_progress = progress

        def on_progress(phase: str, done: int, total: int) -> None:
            progress.setLabelText(f"{phase} — {done:,} of {total:,} rows")
            progress.setValue(int(100 * done / total) if total else 0)

        def on_cancel_clicked() -> None:
            progress.setLabelText("Cancelling…")
            runner.cancel()

        def close_progress() -> None:
            progress.reset()
            progress.close()

        def on_done(results: list) -> None:
            close_progress()
            rows = sum(int(r["rows"]) for r in results)
            self._log_activity(f"[SESSION] Merged {folder.name}: {len(results)} workbook(s), {rows:,} rows")
            self._show_merge_result(results)

        def on_failed(message: str) -> None:
            close_progress()
            self._log_activity(f"[ERROR] Merge failed for {folder.name}: {message}")
            self._popup_critical("Merge Session", f"The merge did not complete:\n\n{message}\n\n"
                                 "Nothing was written; the session folder is unchanged.")

        def on_cancelled() -> None:
            close_progress()
            self._log_activity(f"[SESSION] Merge of {folder.name} cancelled; nothing was written")
            self._set_status("Merge cancelled")

        runner.progress.connect(on_progress)
        runner.finished.connect(on_done)
        runner.failed.connect(on_failed)
        runner.cancelled.connect(on_cancelled)
        progress.canceled.connect(on_cancel_clicked)
        progress.show()
        runner.start(folder, kind, split, out, keep_csv)

    def _show_merge_result(self, results: list) -> None:
        files = [Path(r["xlsx"]) for r in results]
        rows = sum(int(r["rows"]) for r in results)
        lines = "\n".join(f"• {p.name} — {int(r['rows']):,} rows" for p, r in zip(files, results, strict=True))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Merge Session")
        box.setText(f"Merged {rows:,} rows into {len(files)} workbook(s):")
        box.setInformativeText(f"{lines}\n\nSaved in: {files[0].parent}")
        open_btn = box.addButton("Open Folder", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(files[0].parent)))
