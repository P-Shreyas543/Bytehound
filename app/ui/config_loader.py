"""Configuration loading / recent-files logic extracted from MainWindow.

ConfigLoaderMixin holds the 10 methods that read FrameConfig from disk,
wire it into MainWindow state (parser, plot history, table model, recent
selector), and handle the file-picker / recent-config UX. Designed to be
mixed into MainWindow.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QLabel,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from ..decoder.config_loader import load_config
from ..decoder.lifecycle import Candidate, ConfigHistory, prepare_candidate

_LOG = logging.getLogger("bytehound.ui")


def config_history_dir() -> Path:
    """Where activated configurations are kept for rollback (Part C4).
    ``BYTEHOUND_CONFIG_HISTORY_DIR`` overrides it (tests)."""
    override = os.environ.get("BYTEHOUND_CONFIG_HISTORY_DIR")
    if override:
        return Path(override)
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(base or Path.home() / ".bytehound") / "config_history"
from ..protocol.packet_parser import create_parser


def format_display_data_type(data_type: str, byte_length: int, is_boolean: bool = False) -> str:
    if is_boolean or (data_type or "").strip().lower() in ("bool", "boolean"):
        return "boolean"
    dt = (data_type or "").strip().lower()
    if dt in ("uint", "int", "float"):
        if dt == "float":
            return f"float{byte_length * 8}"
        return f"{dt}{byte_length * 8}"
    return data_type or "-"


class ConfigLoaderMixin:
    """MainWindow mixin holding config load/save/recent methods."""

    def _on_show_config_info(self) -> None:
        """View → Config Info… — shows current config, protocol and logging state."""
        self._log_activity("[ACTION] Open Config Info dialog")
        dlg = QDialog(self)
        dlg.setWindowTitle("Config Info")
        dlg.setMinimumWidth(420)
        root = QVBoxLayout(dlg)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        def _row(lbl: str, val: str) -> None:
            v = QLabel(val)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(f"<b>{lbl}:</b>", v)

        if self._config is None:
            _row("Configuration", "None loaded")
        else:
            _row("Config path", str(self._config_path) if self._config_path else "(preset)")
            p = self._config.protocol
            _row("Profile name", p.profile_name)
            _row("Parser type", p.parser_type)
            _row("Header hex", p.header.hex(" ").upper() if p.header else "(none)")
            _row("Footer hex", p.footer.hex(" ").upper() if p.footer else "(none)")
            _row("Frame ID size", f"{p.frame_id_size} byte(s), {p.frame_id_byte_order}-endian")
            _row("Length size", f"{p.length_size} byte(s) ({p.length_meaning})")
            _row("CRC type", f"{p.crc_type} ({p.crc_size} bytes, {p.crc_byte_order})")
            _row("Escape mode", p.escape_mode)
            _row("Inter-frame delay", f"{p.inter_frame_delay_ms} ms")
            _row("TX pad length", f"{p.tx_pad_length} bytes" if p.tx_pad_length else "(disabled)")
            _row("Frames loaded", str(len(self._config.frames)))
            _row("Signals loaded", str(len(self._config.all_signals)))
            _row("Calculations", str(len(self._config.calc_groups)))
            _row("TX commands", str(len(self._config.tx_commands)))
            _row("Polling schedules", str(len(self._config.polling_schedules)))

        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        root.addWidget(buttons)

        dlg.exec()

    def _on_load_config(self) -> None:
        self._log_activity("[ACTION] Load config (file dialog)")
        # Start picker at the directory of the currently-loaded config, or current working dir.
        start_dir = ""
        if self._config_path and Path(self._config_path).is_file():
            start_dir = str(Path(self._config_path).parent)

        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Configuration",
            start_dir,
            "Config Files (*.xlsx *.xlsm *.json protocol.csv);;Excel Files (*.xlsx *.xlsm);;JSON (*.json);;CSV Files (protocol.csv);;All Files (*.*)",
        )
        if not path_str:
            return

        chosen = Path(path_str)
        suffix = chosen.suffix.lower()
        if suffix in {".xlsx", ".xlsm", ".json"}:
            path = chosen
        elif suffix == ".csv":
            path = chosen.parent
        else:
            self._popup_warning("Config error", f"Unsupported config selection: {chosen.name}")
            return

        progress = QProgressDialog(
            "Importing configuration — please wait…",
            None,
            0,
            0,
            self,
        )
        progress.setWindowTitle("Importing")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        try:
            candidate = prepare_candidate(path, self._config)
        finally:
            progress.close()
        self._review_and_activate(candidate, path)

    # -- lifecycle (Part C4): candidate -> preview -> confirm -> activate ----

    def _import_config_interactive(self, path: Path, *, remember: bool = True) -> bool:
        """Import ``path`` as a candidate, preview it, activate on confirm."""
        return self._review_and_activate(prepare_candidate(path, self._config), path, remember=remember)

    def _review_and_activate(self, candidate: Candidate, path: Path, *, remember: bool = True) -> bool:
        self._log_activity(
            f"[CONFIG] Candidate {Path(path).name}: {len(candidate.report.errors)} error(s), "
            f"{len(candidate.report.warnings)} warning(s)"
        )
        if not self._confirm_candidate(candidate, path):
            self._log_activity("[CONFIG] Import not activated; the active configuration is unchanged")
            return False
        self._activate_candidate(candidate, path, remember=remember)
        return True

    def _connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @staticmethod
    def candidate_preview_text(candidate: Candidate, has_active: bool) -> str:
        report = candidate.report
        lines = []
        if report.errors:
            lines.append(f"{len(report.errors)} error(s) - this configuration cannot be activated:")
            lines += [f"  {i}" for i in report.errors]
            lines.append("")
        if report.warnings:
            lines.append(f"{len(report.warnings)} warning(s) (it can still be activated):")
            lines += [f"  {i}" for i in report.warnings]
            lines.append("")
        if candidate.diff is not None:
            lines.append("Changes against the active configuration:" if has_active else "Contents:")
            lines += [f"  {line}" for line in candidate.diff.summary_lines()]
            if has_active:
                lines += [f"    {line}" for line in candidate.diff.detail_lines()]
        return "\n".join(lines)

    def _confirm_candidate(self, candidate: Candidate, path: Path) -> bool:
        """Preview dialog: errors block, warnings and the change list inform,
        and nothing is applied without an explicit Activate."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Import Configuration")
        dlg.setMinimumSize(640, 420)
        root = QVBoxLayout(dlg)
        head = f"<b>{Path(path).name}</b>"
        if candidate.fingerprint:
            head += f"<br>Fingerprint: <code>{candidate.fingerprint[:16]}</code>"
        root.addWidget(QLabel(head))
        text = QPlainTextEdit(self.candidate_preview_text(candidate, self._config is not None))
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        root.addWidget(text, 1)
        if candidate.can_activate and self._connected():
            note = "ByteHound will reconnect with the new configuration."
            if getattr(self, "_logging", False):
                note += " Logging continues: a short gap is recorded and a new segment starts."
            root.addWidget(QLabel(note))
        buttons = QDialogButtonBox(dlg)
        if candidate.can_activate:
            activate = QPushButton("Activate")
            activate.setDefault(True)
            buttons.addButton(activate, QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        else:
            buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        root.addWidget(buttons)
        return bool(candidate.can_activate and dlg.exec() == QDialog.DialogCode.Accepted)

    def _config_history(self) -> ConfigHistory:
        return ConfigHistory(config_history_dir())

    def _activate_candidate(self, candidate: Candidate, path: Path, *, remember: bool = True) -> None:
        """Make ``candidate`` the active configuration. While connected, the
        capture worker is restarted with it (decision 3): the worker holds
        the configuration it was started with. While logging, the session
        records a gap and continues in a new segment with the new
        configuration."""
        assert candidate.config is not None
        settings = getattr(self, "_saved_settings", None)
        reconnect = self._connected() and settings is not None
        logging_on = bool(getattr(self, "_logging", False) and getattr(self, "_session_log", None) is not None)
        if reconnect:
            self._resume_polling = self._polling_action.isChecked()
            self._disconnect(reason="Reconnecting with the new configuration", keep_logging=True)
        self._load_config_from_path(path, config=candidate.config, remember=remember)
        self._config_fingerprint = candidate.fingerprint
        if logging_on and self._session_log is not None:
            try:
                cid = self._session_log.change_config(self._config, Path(path))
                self._log_activity(f"[SESSION] Configuration changed; new segments use {cid}")
            except Exception as exc:
                _LOG.exception("Session configuration change failed")
                self._log_activity(f"[ERROR] Session could not switch configuration: {exc}")
        if candidate.doc is not None:
            try:
                self._config_history().record(candidate.doc)
            except Exception as exc:
                # The configuration is active; only the rollback copy is missing.
                _LOG.warning("Configuration history not updated", exc_info=True)
                self._log_activity(f"[WARN] Configuration history not updated: {exc}")
        if reconnect:
            if self._attempt_connect(settings, is_retry=True):
                self._log_activity("[CONFIG] Reconnected with the new configuration")
            else:
                self._log_activity("[WARN] Reconnect with the new configuration failed; retrying")
                self._reconnect_attempts = 0
                self._reconnect_timer.start(1000)

    def _on_restore_config(self) -> None:
        """File > Restore Previous Configuration... (rollback, Part C4)."""
        self._log_activity("[ACTION] Restore previous configuration")
        current = getattr(self, "_config_fingerprint", None)
        entries = [e for e in self._config_history().entries() if e.fingerprint != current]
        if not entries:
            self._popup_information("Restore Configuration", "No earlier configuration is stored yet.")
            return
        labels = [e.label for e in entries]
        choice, ok = QInputDialog.getItem(self, "Restore Configuration",
                                          "Configuration to restore (newest first):", labels, 0, False)
        if not ok:
            return
        self._import_config_interactive(entries[labels.index(choice)].path, remember=False)

    def _load_config_from_path(self, path: Path, suppress_popups: bool = False, *,
                               config=None, remember: bool = True) -> None:
        # Keep a snapshot so we can revert on failure
        _prev_config = self._config
        _prev_config_path = self._config_path
        _prev_parser = self._parser
        try:
            self._config = config if config is not None else load_config(path)
        except Exception as exc:  # ConfigError or unexpected
            self._config = _prev_config
            self._config_path = _prev_config_path
            self._parser = _prev_parser
            if not suppress_popups:
                self._popup_critical("Config error", str(exc))
            raise
        self._config_path = path
        self._parser = create_parser(self._config.protocol)
        self._tx_logger_parser = create_parser(self._config.protocol)
        self._reset_session_clock()
        self._apply_plot_time_mode(self._plot_time_mode, persist=False)
        self._plot_history.clear()
        if hasattr(self, "_tx_frame_payload_cache"):
            self._tx_frame_payload_cache.clear()
        if hasattr(self, "_latest_payload_by_frame"):
            self._latest_payload_by_frame.clear()
        self._seen_decode_warnings.clear()
        self._unsolicited_detected = False
        self._packet_count = 0
        self._error_count = 0
        self._timeouts = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._delta_t_ms = 0.0
        self._last_packet_perf = None
        if self._serial is not None:
            self._serial.reset_metrics()
        self._console.clear()
        self._populate_table_from_config()
        self._populate_group_selector()
        self._plot_keys.clear()
        # Clear panel assignments — old signals may not exist in the new config.
        # Curves must be removed from the legend and right_vb too, or the
        # next config's signals will show stacked-on-top legend rows and
        # ghost dual-axis links (same root cause as _remove_signal_from_panel).
        for panel in self._plot_panels:
            panel.assigned_keys.clear()
            for curve in panel.curves.values():
                panel.plot_item.removeItem(curve)
                if panel.right_vb is not None:
                    panel.right_vb.removeItem(curve)
                if panel.legend is not None:
                    panel.legend.removeItem(curve)
            panel.curves.clear()
            # Reset unit tracking so the right-axis decision is recomputed
            # from scratch on the new config's first redraw.
            panel.left_unit = None
            panel.right_unit = None
        # Hover-readout cache holds (xs, ys) snapshots keyed by old (frame_id,
        # signal_name) tuples — drop it so a stale cursor read doesn't
        # surface values for signals the new config no longer has.
        if hasattr(self, "_hover_cache"):
            self._hover_cache.clear()
        self._rebuild_panel_strips()   # once after the loop, not N times
        self._persist_panel_assignments()
        self._populate_tx_commands()
        self._update_poll_status_sidebar()
        self._populate_editor_table()
        self._refresh_config_status()
        if hasattr(self, "_cards_view") and self._cards_view is not None:
            self._cards_view.rebuild_from_config(self._config)
        if hasattr(self._config, "serial_defaults") and self._config.serial_defaults:
            baud = self._config.serial_defaults.baud_rate
            if baud:
                self._settings.setValue("conn/baud", str(baud))
                if hasattr(self, "_welcome_dashboard") and self._welcome_dashboard is not None:
                    self._welcome_dashboard.set_baud(baud)
        self._apply_config_logging_defaults()
        self._install_rate_monitor()
        if remember:
            self._remember_config(path)
        self._refresh_action_state()
        self._set_status(f"Loaded config from {path}")
        self._log_activity(f"Loaded config: {path}")
        # Long-lived objects (UI, configuration) out of the collector's
        # reach; the previous configuration is freed first (app/gc_tuning).
        from ..gc_tuning import refreeze
        refreeze()

    def _apply_config_logging_defaults(self) -> None:
        """The configuration's ``logging`` sheet sets Logging Settings (a
        blank cell keeps the user's value); applies to the next session."""
        d = getattr(self._config, "logging", None)
        if d is None:
            return
        s = self._settings
        if d.segment_minutes is not None:
            s.setValue("logging/segment_minutes", d.segment_minutes)
        if d.event_log is not None:
            s.setValue("logging/event_log", "true" if d.event_log else "false")
        if d.fixed_step_s is not None:
            s.setValue("logging/fixed_step_enabled", "true" if d.fixed_step_s else "false")
            if d.fixed_step_s:
                s.setValue("logging/fixed_step_s", d.fixed_step_s)
        if d.stale_steps is not None:
            s.setValue("logging/stale_steps", d.stale_steps)
        if d.stale_values is not None:
            s.setValue("logging/stale_policy", d.stale_values)
        if d.merge_on_stop is not None:
            s.setValue("logging/merge_on_stop", d.merge_on_stop)
        if d.merge_keep_csv is not None:
            s.setValue("logging/merge_keep_csv", "true" if d.merge_keep_csv else "false")
        summary = d.summary()
        if summary:
            note = " (from the next session)" if getattr(self, "_logging", False) else ""
            self._log_activity(f"[CONFIG] Logging settings from the configuration{note}: {summary}")

    def _install_rate_monitor(self) -> None:
        """Frames with ``expected_period_ms`` are watched: the Activity Log
        says once when one stops or slows down and once when it is back."""
        from PySide6.QtCore import QTimer

        from ..decoder.rate_monitor import FrameRateMonitor

        self._rate_monitor = FrameRateMonitor.from_config(self._config)
        timer = getattr(self, "_rate_timer", None)
        if timer is None:
            timer = self._rate_timer = QTimer(self)
            timer.setInterval(500)
            timer.timeout.connect(self._check_frame_rates)
        if self._rate_monitor:
            timer.start()
        else:
            timer.stop()

    def _check_frame_rates(self) -> None:
        import time

        monitor = getattr(self, "_rate_monitor", None)
        if not monitor or self._serial is None:
            return
        for _fid, state, message in monitor.check(time.perf_counter()):
            tag = "[INFO]" if state == "ok" else "[WARN]"
            self._log_activity(f"{tag} [RATE] {message}")

    def _on_load_recent_config(self) -> None:
        path_text = self._recent_config_combo.currentText()
        if not path_text:
            return
        self._log_activity(f"[ACTION] Load recent config: {path_text}")
        self._import_config_interactive(Path(path_text))

    def _recent_paths(self) -> list[str]:
        value = self._settings.value("recent_configs", [])
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value if str(item)]

    def _remember_config(self, path: Path | str | dict) -> None:
        if isinstance(path, dict):
            return
        path_text = str(path)
        recent = [item for item in self._recent_paths() if item != path_text]
        recent.insert(0, path_text)
        self._settings.setValue("recent_configs", recent[:8])
        self._populate_recent_selector()
        if hasattr(self, "_welcome_dashboard") and self._welcome_dashboard is not None:
            self._welcome_dashboard.set_recent_configs(self._recent_paths())

    def _populate_recent_selector(self) -> None:
        if not hasattr(self, "_recent_config_combo"):
            return
        current = self._recent_config_combo.currentText()
        self._recent_config_combo.clear()
        self._recent_config_combo.addItems(self._recent_paths())
        index = self._recent_config_combo.findText(current)
        if index >= 0:
            self._recent_config_combo.setCurrentIndex(index)

    def _populate_table_from_config(self) -> None:
        if self._config is None:
            return
        self._row_index.clear()
        rows = []
        self._signal_unit_map.clear()
        for frame_id, signals in self._config.signals_by_frame.items():
            for signal in signals:
                key = (frame_id, signal.signal_name)
                self._signal_unit_map[key] = signal.unit
                rows.append({
                    "key": key,
                    "Frame": f"0x{frame_id:04X}",
                    "Group": signal.group or "-",
                    "Variable": signal.signal_name,
                    "Start B.": str(signal.start_byte),
                    "Data Type": format_display_data_type(signal.data_type, signal.byte_length, signal.is_boolean),
                    "Raw": "-",
                    "Value": "-",
                    "Unit": signal.unit,
                    "Status": "-",
                    "Updated": "-",
                    "is_calculated": False,
                })
        self._table_model.reset_from_config(rows)

    def _refresh_config_status(self) -> None:
        if self._config is None:
            return
        protocol = self._config.protocol
        signal_count = len(self._config.all_signals)
        self._config_label.setText(f"Config: {self._config_path}")
        self._protocol_label.setText(
            f"Protocol: header {protocol.header.hex(' ').upper()}, CRC {protocol.crc_type}"
        )
        self._frames_label.setText(
            f"Frames: {len(self._config.signals_by_frame)}   Variables: {signal_count}   TX: {len(self._config.tx_commands)}"
        )

    def _load_default_config(self) -> None:
        recents = self._recent_paths()
        if recents:
            first_path = Path(recents[0])
            if first_path.exists():
                try:
                    self._load_config_from_path(first_path, suppress_popups=True)
                    return
                except Exception:
                    pass
        from ..decoder.template_io import get_bundled_template_dir
        bundled = get_bundled_template_dir()
        if bundled.exists():
            try:
                self._load_config_from_path(bundled, suppress_popups=True)
            except Exception:
                pass
