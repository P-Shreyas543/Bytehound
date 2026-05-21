"""Configuration loading / recent-files logic extracted from MainWindow.

ConfigLoaderMixin holds the 10 methods that read FrameConfig from disk,
wire it into MainWindow state (parser, plot history, table model, recent
selector), and handle the file-picker / recent-config UX. Designed to be
mixed into MainWindow.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..decoder.config_loader import ConfigError, load_config
from ..protocol.packet_parser import create_parser


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
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(lbl, v)

        _row("Config file:", self._config_label.text())
        _row("Protocol:", self._protocol_label.text())
        _row("Frames:", self._frames_label.text())
        _row("Logging:", self._logging_label.text())

        root.addLayout(form)

        btn_row = QDialogButtonBox()
        open_log_btn = QPushButton("📂  Open Log Folder")
        open_log_btn.clicked.connect(self._on_open_log_folder)
        btn_row.addButton(open_log_btn, QDialogButtonBox.ButtonRole.ActionRole)
        btn_row.addButton(QDialogButtonBox.StandardButton.Close)
        btn_row.rejected.connect(dlg.reject)
        root.addWidget(btn_row)

        dlg.exec()

    def _load_default_config(self) -> None:
        self._populate_recent_selector()
        recent = self._recent_paths()
        for item in recent:
            path = Path(item)
            if path.exists():
                try:
                    self._load_config_from_path(path)
                    return
                except ConfigError:
                    continue
        resources_dir = Path(__file__).resolve().parents[1] / "resources"
        default_path = resources_dir / "config_template"
        try:
            self._load_config_from_path(default_path)
        except ConfigError as exc:
            self._set_status(f"Default config failed: {exc}")

    def _on_load_config(self) -> None:
        self._log_activity("[ACTION] Load configuration (dialog opened)")
        start_dir = str(Path(__file__).resolve().parents[1] / "resources")
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select configuration (Excel workbook or any CSV in a config folder)",
            start_dir,
            "Config (*.xlsx *.xlsm *.csv);;Excel workbook (*.xlsx *.xlsm);;CSV files (*.csv);;All files (*)",
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

        try:
            self._load_config_from_path(path)
        except ConfigError as exc:
            self._popup_critical("Config error", str(exc))
            return

        # The running PollingWorker captured its protocol/parser/schedules at
        # construction time. Loading a new config replaces self._config and
        # self._parser, but the worker keeps decoding live bytes with the OLD
        # rules until it is restarted. Tell the user.
        if self._serial is not None and self._serial.is_open:
            self._popup_information(
                "Reconnect required",
                "The new configuration is loaded for the UI, but the live "
                "serial connection is still using the previous protocol and "
                "polling schedule. Disconnect and reconnect to apply the new "
                "settings on the wire.",
            )

    def _load_config_from_path(self, path: Path) -> None:
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
            self._popup_critical("Config error", str(exc))
            return
        self._config_path = path
        self._parser = create_parser(self._config.protocol)
        self._session_started = datetime.now()
        self._apply_plot_time_mode(self._plot_time_mode, persist=False)
        self._plot_history.clear()
        self._seen_decode_warnings.clear()
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
        # Clear panel assignments — old signals may not exist in the new config
        for panel in self._plot_panels:
            panel.assigned_keys.clear()
            for curve in panel.curves.values():
                panel.plot_item.removeItem(curve)
            panel.curves.clear()
        self._rebuild_panel_strips()   # once after the loop, not N times
        self._persist_panel_assignments()
        self._populate_tx_commands()
        self._update_poll_status_sidebar()
        self._populate_editor_table()
        self._refresh_config_status()
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
        except ConfigError as exc:
            self._popup_critical("Config error", str(exc))

    def _recent_paths(self) -> list[str]:
        value = self._settings.value("recent_configs", [])
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value if str(item)]

    def _remember_config(self, path: Path) -> None:
        path_text = str(path)
        recent = [item for item in self._recent_paths() if item != path_text]
        recent.insert(0, path_text)
        self._settings.setValue("recent_configs", recent[:8])
        self._populate_recent_selector()

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
        assert self._config is not None
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
                    "Data Type": signal.data_type or "-",
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

