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

    _DRAIN_CAP_SECONDS = 60.0
    _DRAIN_POLL_MS = 200

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
                "Please connect to a device before starting logging."
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
        default_file = default_dir / f"serial_log_{timestamp}.xlsx"

        target, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            str(default_file),
            "Log files (*.xlsx);;All files (*)",
        )
        if not target:
            return

        self._start_logging_file(target, choice=choice)

    def _start_logging_file(self, target: Path | str, choice: str = "Raw + Decoded") -> bool:
        if self._logging or self._serial is None:
            return False
        log_raw = choice in ("Raw + Decoded", "Raw only")
        log_decoded = choice in ("Raw + Decoded", "Decoded only")

        base = Path(target)
        base_stem = base.stem
        for suffix in ("_raw", "_decoded"):
            if base_stem.endswith(suffix):
                base_stem = base_stem[: -len(suffix)]
                break

        raw_path: Optional[Path] = None
        decoded_path: Optional[Path] = None
        if log_raw and log_decoded:
            raw_path = base.with_name(f"{base_stem}_raw.xlsx")
            decoded_path = base.with_name(f"{base_stem}_decoded.xlsx")
        elif log_raw:
            raw_path = base.with_name(f"{base_stem}.xlsx")
        else:
            decoded_path = base.with_name(f"{base_stem}.xlsx")

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
                on_warning=self._log_activity,
                hex_format=self._config.protocol.raw_log_format if self._config else "hex",
            )
            if raw_path
            else None
        )
        if decoded_path:
            if self._config is None:
                self._popup_critical("Start Logging", "No configuration loaded.")
                return False
            polling_active = False
            if hasattr(self, "_polling_action") and self._polling_action.isChecked():
                polling_active = True

            self._decoded_logger = DecodedLogger(
                decoded_path,
                self._config,
                flush_interval=flush_interval,
                metadata=metadata,
                on_error=self._on_logger_error,
                on_warning=self._log_activity,
                polling_mode=polling_active,
            )
        else:
            self._decoded_logger = None

        try:
            if self._raw_logger:
                self._raw_logger.open()
            if self._decoded_logger:
                self._decoded_logger.open()
        except (ValueError, OSError) as exc:
            if self._raw_logger:
                try:
                    self._raw_logger.close()
                except Exception:
                    pass
            if self._decoded_logger:
                try:
                    self._decoded_logger.close()
                except Exception:
                    pass
            self._raw_logger = None
            self._decoded_logger = None
            self._popup_critical("Start Logging", str(exc))
            return False

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
        return True

    def _start_logging_auto(self, choice: str = "Raw + Decoded") -> bool:
        from .main_window import APP_NAME
        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        default_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = default_dir / f"auto_log_{timestamp}.xlsx"
        return self._start_logging_file(base, choice=choice)

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

    def _stop_logging(self, title: str = "Saving Log") -> None:
        was_logging = self._logging
        loggers = []
        if self._raw_logger:
            loggers.append(("raw log", self._raw_logger))
        if self._decoded_logger:
            loggers.append(("decoded log", self._decoded_logger))

        if self._raw_logger:
            self._raw_logger.close(timeout=0.0)
        if self._decoded_logger:
            self._decoded_logger.close(timeout=0.0)

        drainers = [(name, lg) for name, lg in loggers if lg.is_draining()]
        if drainers:
            self._wait_for_logger_drain(drainers, title=title)

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

    def _wait_for_logger_drain(self, drainers: list, title: str = "Closing") -> None:
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
        dlg.setWindowTitle(title)
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

    def _check_and_recover_temp_logs(self) -> None:
        """Scan default log directory for orphaned .tmp_data files and recover/clean them asynchronously."""
        import threading
        from .main_window import APP_NAME

        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        if not default_dir.exists():
            return

        tmp_files = [f for f in default_dir.glob("*.tmp_data") if f.exists()]
        if not tmp_files:
            return

        def _recovery_worker():
            import shutil
            recovered_count = 0
            cleaned_count = 0

            for tmp_data in tmp_files:
                tmp_meta = tmp_data.with_suffix(".tmp_meta")
                try:
                    # Clean empty 0-byte temp files
                    if not tmp_data.exists() or tmp_data.stat().st_size == 0:
                        tmp_data.unlink(missing_ok=True)
                        tmp_meta.unlink(missing_ok=True)
                        cleaned_count += 1
                        continue

                    target_path = tmp_data.parent / tmp_data.name[:-9]
                    
                    # DecodedLogger handles Excel creation or CSV fallback internally without losing data
                    DecodedLogger.recover_temp_files(tmp_data, tmp_meta, target_path)
                    recovered_count += 1
                except Exception as exc:
                    logging.getLogger("bytehound").error("Failed to recover %s: %s", tmp_data.name, exc, exc_info=True)
                    # DO NOT UNLINK non-empty temp files! Attempt direct CSV fallback preservation.
                    try:
                        if tmp_data.exists() and tmp_data.stat().st_size > 0:
                            target_path = tmp_data.parent / tmp_data.name[:-9]
                            csv_fallback = target_path.with_suffix(".csv")
                            shutil.copy2(tmp_data, csv_fallback)
                            logging.getLogger("bytehound").info("Preserved raw temp file as %s", csv_fallback)
                            tmp_data.unlink(missing_ok=True)
                            tmp_meta.unlink(missing_ok=True)
                            recovered_count += 1
                    except Exception as fallback_exc:
                        logging.getLogger("bytehound").error("CSV fallback preservation failed for %s: %s", tmp_data.name, fallback_exc)

            if recovered_count > 0:
                msg = f"Recovered {recovered_count} unsaved log file(s) from previous session."
                if hasattr(self, "_toast"):
                    from PySide6.QtCore import QMetaObject, Q_ARG, Qt
                    QMetaObject.invokeMethod(self, "_toast", Qt.ConnectionType.QueuedConnection, Q_ARG(str, msg))
                if hasattr(self, "_log_activity"):
                    self._log_activity(f"[SESSION] {msg}")
            elif cleaned_count > 0:
                if hasattr(self, "_log_activity"):
                    self._log_activity(f"[SESSION] Cleaned up {cleaned_count} stale temporary log file(s).")

        # Spawn background recovery thread to prevent blocking main UI loop on startup
        thread = threading.Thread(target=_recovery_worker, name="TempLogRecoveryThread", daemon=True)
        thread.start()


def _format_number(value) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)

