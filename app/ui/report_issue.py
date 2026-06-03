"""Background reporting thread and mixin for submitting issues to GitHub."""

from __future__ import annotations

import json
import logging
import platform
import sys
import urllib.error
import urllib.request
from datetime import datetime

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QProgressDialog

from .dialogs import ReportIssueDialog

_LOG = logging.getLogger("bytehound.reporter")
class IssueReporter(QThread):
    """Submits the issue details to the Cloudflare proxy Worker on a background thread."""

    finished = Signal(bool, str)

    def __init__(
        self,
        title: str,
        description: str,
        diagnostics: str,
        log_content: str | None,
        worker_url: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.description = description
        self.diagnostics = diagnostics
        self.log_content = log_content
        self.worker_url = worker_url

    def run(self) -> None:
        body_text = self.description

        body_text += (
            f"\n\n<details><summary>Diagnostics Info</summary>\n\n"
            f"```text\n{self.diagnostics}\n```\n</details>"
        )

        if self.log_content:
            body_text += (
                f"\n\n<details><summary>Application Log</summary>\n\n"
                f"```text\n{self.log_content}\n```\n</details>"
            )

        data = {
            "title": f"[App Report] {self.title}",
            "body": body_text,
            "labels": ["user-reported"],
        }

        req = urllib.request.Request(self.worker_url, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "BMSConfigurator-App")  # Matches proxy filter

        try:
            with urllib.request.urlopen(
                req, data=json.dumps(data).encode("utf-8"), timeout=15
            ) as response:
                if response.status == 201:
                    self.finished.emit(True, "Issue reported successfully.")
                else:
                    self.finished.emit(False, f"Status code: {response.status}")
        except urllib.error.HTTPError as e:
            self.finished.emit(False, f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            self.finished.emit(False, str(e))


class ReportIssueMixin:
    """MainWindow mixin to coordinate the issue report dialog and submission thread."""

    def _on_report_issue(self) -> None:
        self._log_activity("[ACTION] Report Issue")
        dlg = ReportIssueDialog(self)
        if dlg.exec() == ReportIssueDialog.DialogCode.Accepted:
            title, description, include_log = dlg.get_data()

            diagnostics = self._gather_issue_diagnostics()

            log_content = None
            if include_log:
                log_path = self._find_log_file_path()
                if log_path:
                    log_content = self._read_log_tail(log_path, lines=200)
                else:
                    log_content = "(log file not found)"

            self._progress_dialog = QProgressDialog(
                "Submitting issue report...", "Cancel", 0, 0, self
            )
            self._progress_dialog.setWindowTitle("Report Issue")
            self._progress_dialog.setWindowModality(Qt.WindowModality.NonModal)
            self._progress_dialog.setAutoClose(True)
            self._progress_dialog.setAutoReset(True)
            self._progress_dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self._progress_dialog.show()

            worker_url = self._version_info.get("issue_url", "https://bytehound.shreyasp182002.workers.dev/report_issue")
            self._reporter = IssueReporter(
                title, description, diagnostics, log_content, worker_url, self
            )
            self._reporter.finished.connect(self._on_report_finished)
            self._progress_dialog.canceled.connect(self._reporter.requestInterruption)
            self._reporter.start()

    def _on_report_finished(self, success: bool, message: str) -> None:
        if getattr(self, "_progress_dialog", None) is not None:
            self._progress_dialog.close()

        if success:
            self._popup_information("Report Issue", message)
            self._log_activity(f"[SESSION] {message}")
        else:
            self._popup_critical("Report Issue Error", f"Failed to report issue:\n{message}")
            self._log_activity(f"[ERROR] Issue report failed: {message}")

    def _gather_issue_diagnostics(self) -> str:
        try:
            from PySide6 import __version__ as pyside_version
        except Exception:
            pyside_version = "unknown"
        try:
            from PySide6.QtCore import qVersion
            qt_version = qVersion()
        except Exception:
            qt_version = "unknown"

        conn = "disconnected"
        port_info = ""
        if self._serial is not None and self._serial.is_open:
            conn = "connected"
            port_info = (
                f"  Port: {self._serial.settings.port} @ "
                f"{self._serial.settings.baud_rate} "
                f"{self._serial.settings.data_bits}{self._serial.settings.parity}"
                f"{self._serial.settings.stop_bits:g}"
            )

        diag = [
            f"Captured: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "--- Runtime ---",
            f"OS:      {platform.system()} {platform.release()} ({platform.version()})",
            f"Python:  {sys.version.split()[0]}",
            f"PySide6: {pyside_version}",
            f"Qt:      {qt_version}",
            f"Frozen:  {getattr(sys, 'frozen', False)}",
            "",
            "--- Session ---",
            f"Config:      {self._config_path or '(none loaded)'}",
            f"Connection:  {conn}",
        ]
        if port_info:
            diag.append(port_info)
        diag += [
            f"Logging:     {'active' if self._logging else 'stopped'}",
            f"Started:     {self._session_started.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Frames RX:   {self._packet_count}",
            f"CRC errors:  {self._error_count}",
            f"Timeouts:    {self._timeouts}",
            f"RX bytes:    {self._rx_bytes}",
            f"TX bytes:    {self._tx_bytes}",
        ]
        return "\n".join(diag)
