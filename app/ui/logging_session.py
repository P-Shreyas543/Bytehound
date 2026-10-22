"""Logging-session methods extracted from MainWindow.

LoggingSessionMixin holds the six methods that control decoded log
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

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QMessageBox, QProgressDialog,
)

from ..serial_logging.decoded_logger import DecodedLogger
from ..serial_logging.session import SessionLog, SessionSettings, find_unfinished_sessions, recover_session
from .dialogs import LoggingSettingsDialog
from .widgets import _BTN_PINK, _BTN_YELLOW


class _GuiCallbackRelay(QObject):
    """Runs session callbacks on the GUI thread.

    The capture worker writes frames to the session on its own thread, and
    the session's warning / error callbacks touch widgets. Emitting from the
    worker queues the call to this object's (GUI) thread; emitting from the
    GUI thread calls it directly.
    """

    _call = Signal(object, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._call.connect(self._deliver)

    @Slot(object, str)
    def _deliver(self, callback, message: str) -> None:
        callback(message)

    def wrap(self, callback):
        return lambda message: self._call.emit(callback, message)


def _attach_session_sink(worker, session) -> bool:
    """Hand the session to a worker that logs on its own thread. False when
    the worker cannot (capture-process mode): the GUI then logs as before."""
    setter = getattr(worker, "set_session_sink", None)
    if worker is None or setter is None or not getattr(worker, "logs_sessions", False):
        return False
    setter(session)
    return True


class _RecoveryNotifier(QObject):
    """Carries the temp-log recovery result from its worker thread to the GUI thread."""
    done = Signal(str, bool)   # message, show a toast


class _WorkerRawCapture:
    """Points a session's raw capture at whichever capture worker is current
    (it changes on every reconnect)."""

    def __init__(self, window) -> None:
        self._window = window

    def start(self, path: Path, metadata: dict) -> None:
        worker = getattr(self._window, "_serial", None)
        if worker is not None:
            worker.start_raw_capture(path, metadata)

    def stop(self):
        worker = getattr(self._window, "_serial", None)
        return worker.stop_raw_capture() if worker is not None else None

    def rotate(self, path, metadata):
        worker = getattr(self._window, "_serial", None)
        if worker is None:
            raise OSError("not connected")
        return worker.rotate_raw_capture(path, metadata)


class LoggingSessionMixin:
    """MainWindow mixin holding logging start/stop/error methods."""

    _DRAIN_CAP_SECONDS = 60.0
    # Longest the GUI thread blocks per wait while a stopped log finishes.
    # 200 ms made the window respond five times a second for the whole
    # finishing time (seconds, measured with tools/gui_latency_probe.py).
    _DRAIN_POLL_MS = 40

    def _on_logging_settings(self) -> None:
        self._log_activity("[ACTION] Open Logging Settings dialog")
        dlg = LoggingSettingsDialog(self._settings, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        level_name, flush_interval = dlg.get_values()
        self._apply_logging_level(level_name)
        self._set_status("Logging settings updated (applied to the next logging session)")
        self._log_activity(
            f"[ACTION] Logging settings updated: level {level_name}, flush {flush_interval:.2f}s, "
            f"{self._session_settings_summary(self._session_settings_from_qsettings())}"
        )

    # -- session settings ---------------------------------------------------

    def _session_settings_from_qsettings(self) -> SessionSettings:
        s = self._settings

        def num(key: str, default: float) -> float:
            try:
                return float(s.value(key, default))
            except (TypeError, ValueError):
                return float(default)

        def flag(key: str, default: bool) -> bool:
            return str(s.value(key, "true" if default else "false")).lower() == "true"

        fixed_on = flag("logging/fixed_step_enabled", False)
        return SessionSettings(
            segment_seconds=max(60.0, num("logging/segment_minutes", 60) * 60.0),
            event_log=flag("logging/event_log", True) or not fixed_on,
            fixed_step_s=max(0.01, num("logging/fixed_step_s", 1.0)) if fixed_on else None,
            stale_steps=max(1, int(num("logging/stale_steps", 3))),
            hold_stale=str(s.value("logging/stale_policy", "hold")) != "blank",
            disk_warn_bytes=int(max(0.0, num("logging/disk_warn_gb", 10)) * 1024 ** 3),
            disk_stop_bytes=int(max(0.0, num("logging/disk_stop_gb", 2)) * 1024 ** 3),
        )

    @staticmethod
    def _session_settings_summary(st: SessionSettings) -> str:
        parts = [f"segments {st.segment_seconds / 60:g} min"]
        if st.event_log:
            parts.append("event log")
        if st.fixed_step_s:
            parts.append(f"fixed step {st.fixed_step_s:g} s ({'hold' if st.hold_stale else 'blank'} stale)")
        return ", ".join(parts)

    # -- start / stop -------------------------------------------------------

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

        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        default_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = default_dir / f"session_{timestamp}"

        target, _ = QFileDialog.getSaveFileName(
            self,
            "Name the logging session (a folder with this name is created)",
            str(default_name),
            "Logging session folder (*)",
        )
        if not target:
            return

        self._start_logging_file(target)

    def _start_logging_file(self, target: Path | str) -> bool:
        """Start a logging session in the folder *target* (created).

        A session is a folder of hourly segments — event log, optional
        fixed-step log, rejected frames and lossless raw capture — plus a
        ``session.json`` manifest (see ``serial_logging/session.py``).
        """
        if self._logging or self._serial is None:
            return False
        if self._config is None:
            self._popup_critical("Start Logging", "No configuration loaded.")
            return False

        folder = Path(target)
        if folder.suffix.lower() in (".xlsx", ".csv"):
            folder = folder.with_suffix("")
        self._log_started = datetime.now()
        self._log_started_perf = time.perf_counter()
        polling_active = hasattr(self, "_polling_action") and self._polling_action.isChecked()
        settings = self._session_settings_from_qsettings()
        session = SessionLog(
            folder,
            self._config,
            settings,
            config_source=self._config_path,
            metadata=self._build_log_metadata(folder),
            app_version=self._version_info.get("version", "") if hasattr(self, "_version_info") else "",
            polling_mode=polling_active,
            raw_capture=_WorkerRawCapture(self),
            on_warning=self._session_relay().wrap(lambda msg: self._log_activity(f"[WARN] {msg}")),
            on_error=self._session_relay().wrap(self._on_logger_error),
        )
        try:
            session.start()
        except (OSError, ValueError) as exc:
            self._popup_critical("Start Logging", f"Could not start the logging session:\n\n{exc}")
            return False
        self._session_log = session
        # From here on the capture worker writes frames to the session on its
        # thread (the GUI thread only does housekeeping).
        _attach_session_sink(self._serial, session)
        self._remember_session_folder(folder)
        if getattr(self, "_integrity", None):
            session.set_integrity(self._integrity)

        self._attach_session_logfile(folder, settings)
        self._logging = True
        self._logging_action.setText("Stop Logging")
        self._style_action_btn(self._logging_action, _BTN_PINK)   # active → pink
        self._session_timer.start()
        self._update_logging_label()
        self._set_status(f"Logging started: {folder.name}")
        self._log_activity(
            f"Logging started: {folder} ({self._session_settings_summary(settings)})"
        )
        return True

    def _start_logging_auto(self) -> bool:
        from .main_window import APP_NAME
        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        default_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._start_logging_file(default_dir / f"auto_session_{timestamp}")

    def _remembered_session_folders(self) -> list:
        raw = self._settings.value("logging/recent_sessions", []) or []
        if isinstance(raw, str):
            raw = [raw]
        return [Path(p) for p in raw if p]

    def _remember_session_folder(self, folder: Path) -> None:
        """Remember sessions saved outside the default folder so crash
        recovery can find them on the next launch."""
        folders = [str(folder)] + [str(p) for p in self._remembered_session_folders() if p != folder]
        self._settings.setValue("logging/recent_sessions", folders[:20])

    def _on_session_tick(self) -> None:
        """1 Hz session housekeeping: fixed-step rows for quiet periods,
        segment rotation, disk guard, status label."""
        session = getattr(self, "_session_log", None)
        if session is None:
            return
        try:
            session.tick()
        except Exception as exc:
            logging.getLogger("bytehound.logging").exception("Session housekeeping failed")
            self._on_logger_error(f"Session housekeeping failed: {exc}")
            return
        if session.stopped_for_disk and self._logging:
            self._stop_logging(title="Disk Full")
            return
        self._update_logging_label()

    def _update_logging_label(self) -> None:
        session = getattr(self, "_session_log", None)
        if session is None:
            self._logging_label.setText("Logging: stopped")
            return
        seg = session.segment_index
        free = getattr(session, "disk_free_bytes", None)
        free_txt = f" · {free / 1e9:.0f} GB free" if free is not None else ""
        state = f"segment {seg}" if seg is not None else "waiting for reconnect"
        self._logging_label.setText(f"Logging: {session.folder.name} · {state}{free_txt}")

    def _apply_logging_level(self, level_name: str) -> None:
        raw_level = getattr(logging, str(level_name).upper(), logging.INFO)
        level = raw_level if isinstance(raw_level, int) else logging.INFO
        root = logging.getLogger()
        root.setLevel(level)
        for handler in root.handlers:
            handler.setLevel(level)

    def _session_relay(self) -> _GuiCallbackRelay:
        relay = getattr(self, "_session_callback_relay", None)
        if relay is None:
            relay = self._session_callback_relay = _GuiCallbackRelay(self)
        return relay

    def _on_logger_error(self, message: str) -> None:
        logging.getLogger("bytehound.logging").error("Logging error: %s", message)
        if self._logging:
            self._stop_logging()
        self._set_status("Logging stopped (error)")
        self._log_activity(f"[ERROR] {message}")
        self._popup_warning("Logging Error", f"Logging stopped due to an error:\n\n{message}")

    def _stop_logging(self, title: str = "Saving Log") -> None:
        was_logging = self._logging
        session = getattr(self, "_session_log", None)
        self._session_log = None
        # Detach before stopping: a frame the worker is logging right now is
        # serialised with stop() by the session's lock; later ones are not
        # written (the session has ended).
        _attach_session_sink(getattr(self, "_serial", None), None)
        if hasattr(self, "_session_timer"):
            self._session_timer.stop()
        if session is not None:
            session.stop()
            if session.is_finishing():
                # Skipping only stops waiting: finishing continues in the
                # background and loses nothing.
                self._wait_for_logger_drain([("logging session", session)], title=title,
                                            skip_label="Continue in background")
            if session.is_finishing():
                self._log_activity(
                    f"Logging stopped: {session.folder} is still being finished in the background "
                    "(the .xlsx files and session.json are complete when it is done)"
                )
            else:
                self._log_activity(f"Logging session saved: {session.folder}")
            self._offer_rebuild_if_dropped(session)

        if session is not None:
            self._detach_session_logfile(session)
        self._logging = False
        self._log_started = None
        self._log_started_perf = None
        self._logging_action.setText("Start Logging")
        self._style_action_btn(self._logging_action, _BTN_YELLOW)   # back to yellow
        self._logging_label.setText("Logging: stopped")
        self._set_status("Logging stopped")
        if was_logging:
            self._log_activity("Logging stopped")

    # -- per-session log.txt (owner request 2026-10-22) -------------------
    # Every session folder gets the application log of that recording, so a
    # zipped session is self-explanatory when shared for debugging.

    SESSION_LOG_NAME = "log.txt"

    def _attach_session_logfile(self, folder: Path, settings) -> None:
        self._detach_session_logfile(None)               # never two at once
        try:
            handler = logging.FileHandler(Path(folder) / self.SESSION_LOG_NAME, mode="a", encoding="utf-8")
        except OSError as exc:
            self._log_activity(f"[WARN] Session log.txt not created: {exc}")
            return
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logging.getLogger().addHandler(handler)
        self._session_log_handler = handler
        import platform
        version = self._version_info.get("version", "") if hasattr(self, "_version_info") else ""
        conn = getattr(self, "_saved_settings", None)
        log = logging.getLogger("bytehound.session")
        log.info("==== Bytehound %s — session log ====", version)
        log.info("Session folder: %s", folder)
        log.info("Configuration: %s", getattr(self, "_config_path", ""))
        if conn is not None:
            log.info("Connection: %s %s @ %s baud", getattr(conn, "connection_type", "serial"),
                     getattr(conn, "port", ""), getattr(conn, "baud_rate", ""))
        log.info("Settings: %s", self._session_settings_summary(settings))
        log.info("System: %s, Python %s", platform.platform(), platform.python_version())

    def _detach_session_logfile(self, session) -> None:
        """Close the session's log.txt — once its background finishing (xlsx,
        caches) is done, so the end of the story is in the file too."""
        handler = getattr(self, "_session_log_handler", None)
        if handler is None:
            return
        if session is not None and session.is_finishing():
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1000, lambda s=session: self._detach_session_logfile(s))
            return
        if session is not None:
            logging.getLogger("bytehound.session").info("==== session log closed ====")
        self._session_log_handler = None
        logging.getLogger().removeHandler(handler)
        handler.close()

    def _offer_rebuild_if_dropped(self, session: SessionLog) -> None:
        """F10: if the decoded log had to drop frames, rebuild it from the
        lossless raw capture so the saved session is complete."""
        dropped = session.decoded_dropped
        if not dropped or self._config is None:
            return
        self._log_activity(
            f"[WARN] {dropped} frame(s) were missing from the decoded log; every frame is in the raw capture."
        )
        answer = QMessageBox.question(
            self,
            "Rebuild Decoded Log",
            f"{dropped} frame(s) could not be written to the decoded log in time "
            f"(the PC was too busy).\n\nEvery frame is in the raw capture. Rebuild the "
            f"decoded log for this session now? Rebuilt files are saved next to the originals "
            f"as seg_NNNN_event_rebuilt.xlsx.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        import threading
        from ..serial_logging.session import rebuild_session_event_logs

        config, folder = self._config, session.folder
        notifier = _RecoveryNotifier(self)

        def _on_done(msg: str, ok: bool) -> None:
            self._log_activity(f"[SESSION] {msg}")
            self._toast(msg) if ok else self._popup_warning("Rebuild Decoded Log", msg)
            notifier.deleteLater()

        notifier.done.connect(_on_done)

        def _worker() -> None:
            try:
                n = rebuild_session_event_logs(folder, config)
                notifier.done.emit(f"Rebuilt the decoded log of {n} segment(s) in {folder.name}", True)
            except Exception as exc:
                logging.getLogger("bytehound").error("Session rebuild failed", exc_info=True)
                notifier.done.emit(f"Rebuild failed: {exc}", False)

        threading.Thread(target=_worker, name="RebuildSession", daemon=False).start()

    def _wait_for_logger_drain(self, drainers: list, title: str = "Closing",
                               skip_label: str = "Skip (may lose data)") -> None:
        """Show a progress dialog and poll each logger until its writer
        thread exits (data on disk), the cap elapses, or the user
        cancels. ``drainers`` is a list of (name, logger) tuples for
        loggers where ``is_draining()`` returned True.
        """
        total_rows = sum(lg.pending_rows() for _, lg in drainers)
        dlg = QProgressDialog(
            f"Finishing log — {total_rows} row(s) remaining…",
            skip_label,
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

    def _on_rebuild_decoded_log(self) -> None:
        """Regenerate a decoded .xlsx from a raw capture using the loaded config."""
        import threading
        from .main_window import APP_NAME
        from ..serial_logging.raw_capture import read_metadata, rebuild_decoded_log

        self._log_activity("[ACTION] Rebuild Decoded Log")
        if self._config is None:
            self._popup_warning("Rebuild Decoded Log", "Load the configuration the capture was recorded with first.")
            return
        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        raw, _ = QFileDialog.getOpenFileName(
            self,
            "Select a raw capture, or a session's session.json to rebuild every segment",
            str(default_dir),
            "Raw capture or session (*.bhraw session.json);;All files (*)",
        )
        if not raw:
            return
        raw_path = Path(raw)
        if raw_path.name == "session.json":
            self._rebuild_whole_session(raw_path.parent)
            return
        try:
            meta = read_metadata(raw_path)
        except (OSError, ValueError) as exc:
            self._popup_critical("Rebuild Decoded Log", str(exc))
            return
        recorded_cfg = meta.get("config_source") or ""
        if recorded_cfg and self._config_path is not None and Path(recorded_cfg) != Path(self._config_path):
            self._log_activity(
                f"[WARN] Capture was recorded with {recorded_cfg}; rebuilding with {self._config_path}"
            )

        target = raw_path.with_suffix(".xlsx")
        if target.exists():
            target = raw_path.with_name(f"{raw_path.stem}_rebuilt.xlsx")
        out, _ = QFileDialog.getSaveFileName(self, "Save rebuilt log", str(target), "Log files (*.xlsx)")
        if not out:
            return
        out_path = Path(out).with_suffix(".xlsx")
        config = self._config

        notifier = _RecoveryNotifier(self)

        def _on_done(msg: str, ok: bool) -> None:
            self._log_activity(f"[SESSION] {msg}")
            self._set_status(msg)
            if ok:
                self._toast(msg)
            else:
                self._popup_critical("Rebuild Decoded Log", msg)
            notifier.deleteLater()

        notifier.done.connect(_on_done)

        def _worker() -> None:
            try:
                n = rebuild_decoded_log(raw_path, config, out_path)
                notifier.done.emit(f"Rebuilt {out_path.name} from {n} frame(s)", True)
            except Exception as exc:  # surfaced to the user, never silent
                logging.getLogger("bytehound").error("Rebuild failed for %s", raw_path, exc_info=True)
                notifier.done.emit(f"Rebuild failed: {exc}", False)

        self._set_status(f"Rebuilding {out_path.name}…")
        threading.Thread(target=_worker, name="RebuildDecodedLog", daemon=False).start()

    def _rebuild_whole_session(self, folder: Path) -> None:
        """Rebuild every segment's event log of a session from its raw captures."""
        import threading
        from ..serial_logging.session import read_manifest, rebuild_session_event_logs

        try:
            manifest = read_manifest(folder)
        except (OSError, ValueError) as exc:
            self._popup_critical("Rebuild Decoded Log", str(exc))
            return
        if manifest.get("status") == "recording":
            self._popup_warning(
                "Rebuild Decoded Log", "This session is still recording. Stop logging first."
            )
            return
        config, n_segs = self._config, len(manifest.get("segments", []))
        notifier = _RecoveryNotifier(self)

        def _on_done(msg: str, ok: bool) -> None:
            self._log_activity(f"[SESSION] {msg}")
            self._set_status(msg)
            self._toast(msg) if ok else self._popup_critical("Rebuild Decoded Log", msg)
            notifier.deleteLater()

        notifier.done.connect(_on_done)

        def _worker() -> None:
            try:
                n = rebuild_session_event_logs(folder, config)
                notifier.done.emit(f"Rebuilt {n} of {n_segs} segment(s) in {folder.name}", True)
            except Exception as exc:
                logging.getLogger("bytehound").error("Session rebuild failed", exc_info=True)
                notifier.done.emit(f"Rebuild failed: {exc}", False)

        self._set_status(f"Rebuilding {n_segs} segment(s) of {folder.name}…")
        threading.Thread(target=_worker, name="RebuildSession", daemon=False).start()

    def _check_and_recover_temp_logs(self) -> None:
        """Recover logging sessions and single-file logs that were still being
        written when the app stopped (crash, power loss), in the background."""
        import threading
        from .main_window import APP_NAME

        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        tmp_files = [f for f in default_dir.glob("*.tmp_data") if f.exists()] if default_dir.exists() else []
        sessions = find_unfinished_sessions(default_dir)
        for remembered in self._remembered_session_folders():
            if remembered.exists() and remembered not in sessions:
                sessions += find_unfinished_sessions(remembered, max_depth=0)
        if not tmp_files and not sessions:
            return

        def _recovery_worker():
            import shutil
            recovered_count = 0
            cleaned_count = 0

            for folder in sessions:
                try:
                    if recover_session(folder):
                        recovered_count += 1
                        logging.getLogger("bytehound").info("Recovered logging session %s", folder)
                except Exception as exc:
                    logging.getLogger("bytehound").error("Failed to recover session %s: %s", folder, exc, exc_info=True)

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

            # Widgets may only be touched on the GUI thread: hand the result
            # back through a queued signal instead of calling _log_activity /
            # _toast from here (that could crash the app at startup).
            if recovered_count > 0:
                notifier.done.emit(f"Recovered {recovered_count} unsaved log file(s) from previous session.", True)
            elif cleaned_count > 0:
                notifier.done.emit(f"Cleaned up {cleaned_count} stale temporary log file(s).", False)

        def _on_done(msg: str, toast: bool) -> None:
            self._log_activity(f"[SESSION] {msg}")
            if toast:
                self._toast(msg)

        notifier = _RecoveryNotifier(self)
        notifier.done.connect(_on_done)

        # Spawn background recovery thread to prevent blocking main UI loop on startup
        thread = threading.Thread(target=_recovery_worker, name="TempLogRecoveryThread", daemon=True)
        thread.start()


def _format_number(value) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)

