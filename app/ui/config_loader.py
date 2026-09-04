"""Configuration loading / recent-files logic extracted from MainWindow.

ConfigLoaderMixin holds the 10 methods that read FrameConfig from disk,
wire it into MainWindow state (parser, plot history, table model, recent
selector), and handle the file-picker / recent-config UX. Designed to be
mixed into MainWindow.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from ..decoder.config_loader import ConfigError, load_config
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

    def _on_export_excel_template(self) -> None:
        """File → Export Config Template (Excel)…"""
        from ..decoder.template_io import export_excel_template

        self._log_activity("[ACTION] Export Excel template")
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Bytehound Config Template",
            "bytehound_config_template.xlsx",
            "Excel Workbook (*.xlsx);;All Files (*.*)",
        )
        if not target_path:
            return

        try:
            export_excel_template(None, target_path)
            self._popup_info("Template Exported", f"Successfully created template at:\n{target_path}")
            self._log_activity(f"Exported template to: {target_path}")
        except Exception as exc:
            self._popup_critical("Export Failed", f"Could not create template: {exc}")
            self._log_activity(f"Failed to export template: {exc}")

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
            "Config Files (*.xlsx *.xlsm protocol.csv);;Excel Files (*.xlsx *.xlsm);;CSV Files (protocol.csv);;All Files (*.*)",
        )
        if not path_str:
            return

        chosen = Path(path_str)
        suffix = chosen.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
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
            self._load_config_from_path(path)
        except ConfigError:
            return
        finally:
            progress.close()

        # The running PollingWorker captured its protocol/parser/schedules at
        # construction time. Loading a new config replaces self._config and
        # self._parser, but the worker keeps decoding live bytes with the OLD
        # rules until it is restarted. Tell the user via status/toast.
        if self._serial is not None and self._serial.is_open:
            if hasattr(self, "_toast"):
                self._toast("Reconnect required to apply new config on live serial worker.")

    def _load_config_from_path(self, path: Path, suppress_popups: bool = False) -> None:
        # Keep a snapshot so we can revert on failure
        _prev_config = self._config
        _prev_config_path = self._config_path
        _prev_parser = self._parser
        try:
            self._config = load_config(path)
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
        self._session_started = datetime.now()
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
        self._remember_config(path)
        self._refresh_action_state()
        self._set_status(f"Loaded config from {path}")
        self._log_activity(f"Loaded config: {path}")

    def _on_load_recent_config(self) -> None:
        path_text = self._recent_config_combo.currentText()
        if not path_text:
            return
        self._log_activity(f"[ACTION] Load recent config: {path_text}")
        try:
            self._load_config_from_path(Path(path_text))
        except ConfigError:
            pass

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
