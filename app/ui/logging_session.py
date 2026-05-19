"""Logging-session methods extracted from MainWindow.

LoggingSessionMixin holds the six methods that control raw/decoded log
recording: settings dialog, start/stop toggle, log-level apply, error
handler, and the drain-on-shutdown helper. Designed to be mixed into
MainWindow.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QInputDialog, QProgressDialog,
)

from ..serial_logging.raw_logger import RawLogger
from ..serial_logging.decoded_logger import DecodedLogger
from .dialogs import LoggingSettingsDialog
from .widgets import _BTN_PINK, _BTN_YELLOW


class LoggingSessionMixin:
    """MainWindow mixin holding logging start/stop/error methods."""

    def _on_logging_settings(self) -> None:
        self._log_activity("[ACTION] Open Logging Settings dialog")
        dlg = LoggingSettingsDialog(self._settings, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        level_name, flush_interval = dlg.get_values()
        self._apply_logging_level(level_name)
        if self._raw_logger:
            self._raw_logger.set_flush_interval(flush_interval)
        if self._decoded_logger:
            self._decoded_logger.set_flush_interval(flush_interval)
        self._set_status(
            f"Logging settings updated: level {level_name}, flush {flush_interval:.2f}s"
        )
        self._log_activity(
            f"[ACTION] Logging settings updated: level {level_name}, flush {flush_interval:.2f}s"
        )

    def _on_toggle_logging(self) -> None:
        from .main_window import APP_NAME  # late import to break cycle
        if self._logging:
            self._stop_logging()
            return
        # Guard: logging only makes sense when connected
        if self._serial is None:
            self._popup_warning(
                "Start Logging",
                "Please connect to a device before starting logging.\n"
                "(Offline log replay does not support active logging.)"
            )
            return

        choice, ok = QInputDialog.getItem(
            self,
            "Logging mode",
            "What do you want to log?",
            ["Raw + Decoded", "Raw only", "Decoded only"],
            0,
            False,
        )
        if not ok:
            return
        log_raw = choice in ("Raw + Decoded", "Raw only")
        log_decoded = choice in ("Raw + Decoded", "Decoded only")

        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        default_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_file = default_dir / f"serial_log_{timestamp}.csv"

        target, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            str(default_file),
            "Log files (*.csv *.xlsx);;All files (*)",
        )
        if not target:
            return

        base = Path(target)
        base_stem = base.stem
        for suffix in ("_raw", "_decoded"):
            if base_stem.endswith(suffix):
                base_stem = base_stem[: -len(suffix)]
                break

        raw_path: Optional[Path] = None
        decoded_path: Optional[Path] = None
        if log_raw and log_decoded:
            raw_path = base.with_name(f"{base_stem}_raw.csv")
            decoded_path = base.with_name(f"{base_stem}_decoded.xlsx")
        elif log_raw:
            raw_path = base.with_name(f"{base_stem}.csv")
        else:
            decoded_path = base.with_name(f"{base_stem}.xlsx")

        # Set the logging t=0 BEFORE building metadata so the timestamp written
        # to the Metadata sheet matches the elapsed_ms baseline used in Data.
        # _log_started_perf is the monotonic baseline that elapsed_ms is
        # actually computed against; _log_started is the wall-clock string
        # for the Metadata sheet.
        self._log_started = datetime.now()
        self._log_started_perf = time.perf_counter()
        flush_interval = self._log_flush_interval()
        metadata = self._build_log_metadata(choice, raw_path, decoded_path)
        self._raw_logger = (
            RawLogger(
                raw_path,
                flush_interval=flush_interval,
                metadata=metadata,
                on_error=self._on_logger_error,
            )
            if raw_path
            else None
        )
        if decoded_path:
            assert self._config is not None
            self._decoded_logger = DecodedLogger(
                decoded_path,
                self._config,
                flush_interval=flush_interval,
                metadata=metadata,
                on_error=self._on_logger_error,
            )
        else:
            self._decoded_logger = None

        # Open eagerly so header-mismatch / permission errors surface here as
        # a popup, instead of being raised inside the 60 Hz UI flush callback
        # (which would crash the event loop) when the first packet arrives.
        try:
            if self._raw_logger:
                self._raw_logger.open()
            if self._decoded_logger:
                self._decoded_logger.open()
        except (ValueError, OSError) as exc:
            if self._raw_logger:
                self._raw_logger.close()
                self._raw_logger = None
            if self._decoded_logger:
                self._decoded_logger.close()
                self._decoded_logger = None
            self._popup_critical("Start Logging", f"Could not open log file:\n\n{exc}")
            return

        if self._config_path is not None:
            snapshot_config(self._config_path, base.with_name(f"{base_stem}_session"))

        self._logging = True
        self._logging_action.setText("Stop Logging")
        self._style_action_btn(self._logging_action, _BTN_PINK)   # active → pink

        label_parts = []
        if raw_path:
            label_parts.append(f"raw → {raw_path.name}")
        if decoded_path:
            label_parts.append(f"decoded → {decoded_path.name}")
        summary = ", ".join(label_parts)
        self._logging_label.setText(f"Logging: {summary}")
        self._set_status(f"Logging started ({choice}): {summary}")
        self._log_activity(f"Logging started ({choice}): {summary}")

    def _apply_logging_level(self, level_name: str) -> None:
        raw_level = getattr(logging, str(level_name).upper(), logging.INFO)
        level = raw_level if isinstance(raw_level, int) else logging.INFO
        root = logging.getLogger()
        root.setLevel(level)
        for handler in root.handlers:
            handler.setLevel(level)

    def _on_logger_error(self, message: str) -> None:
        logging.getLogger("bytehound.logging").error("Logging error: %s", message)
        if self._logging:
            self._stop_logging()
        self._set_status("Logging stopped (error)")
        self._log_activity(f"[ERROR] {message}")
        self._popup_warning("Logging Error", f"Logging stopped due to an error:\n\n{message}")

    def _stop_logging(self) -> None:
        was_logging = self._logging
        if self._raw_logger:
            self._raw_logger.close()
        if self._decoded_logger:
            self._decoded_logger.close()
        self._raw_logger = None
        self._decoded_logger = None
        self._logging = False
        self._log_started = None
        self._log_started_perf = None
        self._logging_action.setText("Start Logging")
        self._style_action_btn(self._logging_action, _BTN_YELLOW)   # back to yellow
        self._logging_label.setText("Logging: stopped")
        self._set_status("Logging stopped")
        if was_logging:
            self._log_activity("Logging stopped")

    def _wait_for_logger_drain(self, drainers: list) -> None:
        """Show a progress dialog and poll each logger until its writer
        thread exits (data on disk), the cap elapses, or the user
        cancels. ``drainers`` is a list of (name, logger) tuples for
        loggers where ``is_draining()`` returned True.
        """
        total_rows = sum(lg.pending_rows() for _, lg in drainers)
        dlg = QProgressDialog(
            f"Finishing log — {total_rows} row(s) remaining…",
            "Skip (may lose data)",
            0,
            max(total_rows, 1),
            self,
        )
        dlg.setWindowTitle("Closing")
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)

        deadline = time.monotonic() + self._DRAIN_CAP_SECONDS
        poll_s = self._DRAIN_POLL_MS / 1000.0
        try:
            while time.monotonic() < deadline:
                if dlg.wasCanceled():
                    self._log_activity(
                        "[SESSION] User skipped log drain; some rows may be lost"
                    )
                    break
                # Re-check all drainers each iteration; remove finished ones.
                still_draining = []
                remaining = 0
                for name, lg in drainers:
                    if lg.await_drain(timeout=poll_s):
                        continue
                    still_draining.append((name, lg))
                    remaining += lg.pending_rows()
                if not still_draining:
                    break
                drainers = still_draining
                written = max(0, total_rows - remaining)
                dlg.setValue(written)
                dlg.setLabelText(
                    f"Finishing {', '.join(n for n, _ in drainers)} — "
                    f"{remaining} row(s) remaining…"
                )
                QApplication.processEvents()
            else:
                # Cap reached; log which loggers gave up.
                names = ", ".join(n for n, _ in drainers if n)
                self._log_activity(
                    f"[SESSION] Log drain cap ({self._DRAIN_CAP_SECONDS}s) "
                    f"reached for {names}; some rows may be lost"
                )
        finally:
            dlg.close()


def _format_number(value) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)

