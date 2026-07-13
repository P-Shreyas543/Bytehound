"""Configuration dialogs for the Serial monitor app."""

from typing import Tuple
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget, QStackedWidget
)

from ..decoder.types import SerialDefaults
from ..serial_io.serial_worker import (
    POLL_PIPELINE_TX_GAP_FLOOR_MS,
    SerialSettings,
    available_ports,
)


class ConnectionDialog(QDialog):
    """Modal dialog for configuring and opening a connection (Serial, TCP, or UDP).

    Field-priority order on open is QSettings → loaded config's
    ``SerialDefaults`` → hard-coded fallback. That means the user's
    explicit last-used choice always wins, but a freshly loaded config
    with bespoke serial defaults pre-populates the dialog on first open.

    On Accept the chosen values are persisted back to ``QSettings`` and
    exposed via ``get_settings()``.
    """

    def __init__(
        self,
        settings: QSettings,
        parent=None,
        *,
        config_defaults: SerialDefaults | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.setMinimumWidth(380)
        self._settings = settings
        self._config_defaults = config_defaults or SerialDefaults()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Connection Type Row
        type_row = QWidget(self)
        type_hl = QHBoxLayout(type_row)
        type_hl.setContentsMargins(0, 0, 0, 0)
        self._type_combo = QComboBox(type_row)
        self._type_combo.addItem("Serial", "serial")
        self._type_combo.addItem("TCP Client", "tcp")
        self._type_combo.addItem("UDP Client", "udp")
        type_hl.addWidget(QLabel("Connection Type:", type_row))
        type_hl.addWidget(self._type_combo, 1)
        layout.addWidget(type_row)

        # 2. Stacked Widget for settings
        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack)

        # -- Page 0: Serial Settings
        self._serial_page = QWidget(self)
        serial_form = QFormLayout(self._serial_page)
        serial_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        serial_form.setContentsMargins(0, 0, 0, 0)

        # Port row with inline Refresh button
        port_row = QWidget(self)
        port_hl = QHBoxLayout(port_row)
        port_hl.setContentsMargins(0, 0, 0, 0)
        self._port_combo = QComboBox(port_row)
        self._port_combo.setMinimumWidth(180)
        refresh_btn = QPushButton("⟳", port_row)
        refresh_btn.setStyleSheet("padding: 0px;")
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh port list")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_hl.addWidget(self._port_combo, 1)
        port_hl.addWidget(refresh_btn)

        self._baud_combo = QComboBox(self)
        self._baud_combo.addItems(["9600", "19200", "38400", "57600", "115200",
                                    "230400", "460800", "921600", "1000000", "2000000"])

        self._data_bits_combo = QComboBox(self)
        self._data_bits_combo.addItems(["8", "7"])

        self._stop_bits_combo = QComboBox(self)
        self._stop_bits_combo.addItems(["1", "1.5", "2"])

        self._parity_combo = QComboBox(self)
        self._parity_combo.addItems(["N", "E", "O"])

        serial_form.addRow("Port", port_row)
        serial_form.addRow("Baud rate", self._baud_combo)
        serial_form.addRow("Data bits", self._data_bits_combo)
        serial_form.addRow("Stop bits", self._stop_bits_combo)
        serial_form.addRow("Parity", self._parity_combo)
        self._stack.addWidget(self._serial_page)

        # -- Page 1: TCP Settings
        self._tcp_page = QWidget(self)
        tcp_form = QFormLayout(self._tcp_page)
        tcp_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        tcp_form.setContentsMargins(0, 0, 0, 0)

        self._tcp_host = QLineEdit(self)
        self._tcp_host.setPlaceholderText("127.0.0.1")
        self._tcp_port = QSpinBox(self)
        self._tcp_port.setRange(1, 65535)
        self._tcp_port.setValue(8000)

        tcp_form.addRow("Host / IP", self._tcp_host)
        tcp_form.addRow("Port", self._tcp_port)
        self._stack.addWidget(self._tcp_page)

        # -- Page 2: UDP Settings
        self._udp_page = QWidget(self)
        udp_form = QFormLayout(self._udp_page)
        udp_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        udp_form.setContentsMargins(0, 0, 0, 0)

        self._udp_host = QLineEdit(self)
        self._udp_host.setPlaceholderText("127.0.0.1")
        self._udp_port = QSpinBox(self)
        self._udp_port.setRange(1, 65535)
        self._udp_port.setValue(8000)
        self._udp_local_port = QSpinBox(self)
        self._udp_local_port.setRange(0, 65535)
        self._udp_local_port.setValue(0)
        self._udp_local_port.setToolTip("Optional local bind port (0 for auto)")

        udp_form.addRow("Host / IP", self._udp_host)
        udp_form.addRow("Remote Port", self._udp_port)
        udp_form.addRow("Local Port", self._udp_local_port)
        self._stack.addWidget(self._udp_page)

        # Connect Type Combo index change to QStackedWidget
        self._type_combo.currentIndexChanged.connect(self._stack.setCurrentIndex)

        # 3. Common Settings Form (Timeout & Auto-reconnect)
        common_form = QFormLayout()
        common_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        common_form.setContentsMargins(0, 0, 0, 0)

        self._timeout_combo = QComboBox(self)
        self._timeout_combo.addItems(["20", "50", "100", "250", "500", "1000"])

        self._auto_reconnect_chk = QCheckBox("Auto-reconnect on disconnect", self)

        common_form.addRow("Timeout (ms)", self._timeout_combo)
        common_form.addRow("", self._auto_reconnect_chk)
        layout.addLayout(common_form)

        # 4. Action Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_ports()
        self._restore_from_settings()

        self._port_timer = QTimer(self)
        self._port_timer.setInterval(1000)
        self._port_timer.timeout.connect(self._auto_refresh_ports)
        self._port_timer.start()

    # ------------------------------------------------------------------
    def _refresh_ports(self) -> None:
        current = self._port_combo.currentData(Qt.ItemDataRole.UserRole) or ""
        ports = list(available_ports())
        self._port_combo.clear()
        if ports:
            for device, description in ports:
                label = description if device in description else f"{device} \u2013 {description}"
                self._port_combo.addItem(label, userData=device)
            for i in range(self._port_combo.count()):
                if self._port_combo.itemData(i, Qt.ItemDataRole.UserRole) == current:
                    self._port_combo.setCurrentIndex(i)
                    break
        else:
            self._port_combo.addItem("No ports found", userData="")

    def _auto_refresh_ports(self) -> None:
        if self._stack.currentIndex() != 0:
            return
        ports = list(available_ports())
        combo_ports = []
        for i in range(self._port_combo.count()):
            user_data = self._port_combo.itemData(i, Qt.ItemDataRole.UserRole)
            if user_data:
                combo_ports.append(user_data)
        current_ports = [p[0] for p in ports]
        if set(combo_ports) != set(current_ports):
            self._refresh_ports()

    def _restore_from_settings(self) -> None:
        s = self._settings

        # Connection type
        saved_type = s.value("conn/type", "serial")
        type_idx = self._type_combo.findData(saved_type)
        if type_idx >= 0:
            self._type_combo.setCurrentIndex(type_idx)
            self._stack.setCurrentIndex(type_idx)

        # Serial settings
        saved_port = s.value("conn/port", "")
        for i in range(self._port_combo.count()):
            if self._port_combo.itemData(i, Qt.ItemDataRole.UserRole) == saved_port:
                self._port_combo.setCurrentIndex(i)
                break
        cd = self._config_defaults
        self._baud_combo.setCurrentText(str(s.value("conn/baud", str(cd.baud_rate))))
        self._data_bits_combo.setCurrentText(str(s.value("conn/data_bits", str(cd.data_bits))))
        self._stop_bits_combo.setCurrentText(str(s.value("conn/stop_bits", f"{cd.stop_bits:g}")))
        self._parity_combo.setCurrentText(str(s.value("conn/parity", cd.parity)))

        # TCP Settings
        self._tcp_host.setText(str(s.value("conn/tcp_host", "127.0.0.1")))
        self._tcp_port.setValue(int(s.value("conn/tcp_port", 8000)))

        # UDP Settings
        self._udp_host.setText(str(s.value("conn/udp_host", "127.0.0.1")))
        self._udp_port.setValue(int(s.value("conn/udp_port", 8000)))
        self._udp_local_port.setValue(int(s.value("conn/udp_local_port", 0)))

        # Common settings
        self._timeout_combo.setCurrentText(str(s.value("conn/timeout_ms", str(cd.timeout_ms))))
        auto_rec_val = s.value("conn/auto_reconnect", "false")
        self._auto_reconnect_chk.setChecked(str(auto_rec_val).lower() == "true")

    def _on_accept(self) -> None:
        s = self._settings
        s.setValue("conn/type",           self._type_combo.currentData())

        # Serial settings
        s.setValue("conn/port",           self._port_combo.currentData(Qt.ItemDataRole.UserRole) or "")
        s.setValue("conn/baud",           self._baud_combo.currentText())
        s.setValue("conn/data_bits",      self._data_bits_combo.currentText())
        s.setValue("conn/stop_bits",      self._stop_bits_combo.currentText())
        s.setValue("conn/parity",         self._parity_combo.currentText())

        # TCP Settings
        s.setValue("conn/tcp_host",       self._tcp_host.text().strip())
        s.setValue("conn/tcp_port",       self._tcp_port.value())

        # UDP Settings
        s.setValue("conn/udp_host",       self._udp_host.text().strip())
        s.setValue("conn/udp_port",       self._udp_port.value())
        s.setValue("conn/udp_local_port", self._udp_local_port.value())

        # Common settings
        s.setValue("conn/timeout_ms",     self._timeout_combo.currentText())
        s.setValue("conn/auto_reconnect", "true" if self._auto_reconnect_chk.isChecked() else "false")
        self.accept()

    def get_settings(self) -> "SerialSettings":
        conn_type = self._type_combo.currentData()
        if conn_type == "tcp":
            return SerialSettings(
                connection_type="tcp",
                port=f"{self._tcp_host.text().strip()}:{self._tcp_port.value()}",
                host=self._tcp_host.text().strip(),
                port_num=self._tcp_port.value(),
                timeout_ms=int(self._timeout_combo.currentText()),
                auto_reconnect=self._auto_reconnect_chk.isChecked(),
            )
        elif conn_type == "udp":
            return SerialSettings(
                connection_type="udp",
                port=f"{self._udp_host.text().strip()}:{self._udp_port.value()}",
                host=self._udp_host.text().strip(),
                port_num=self._udp_port.value(),
                local_port=self._udp_local_port.value(),
                timeout_ms=int(self._timeout_combo.currentText()),
                auto_reconnect=self._auto_reconnect_chk.isChecked(),
            )
        else:
            return SerialSettings(
                connection_type="serial",
                port=self._port_combo.currentData(Qt.ItemDataRole.UserRole) or self._port_combo.currentText(),
                baud_rate=int(self._baud_combo.currentText()),
                data_bits=int(self._data_bits_combo.currentText()),
                stop_bits=float(self._stop_bits_combo.currentText()),
                parity=self._parity_combo.currentText(),
                timeout_ms=int(self._timeout_combo.currentText()),
                auto_reconnect=self._auto_reconnect_chk.isChecked(),
            )


class PollingConfigDialog(QDialog):
    """Modal dialog for selecting which polling targets are active.

    Each target from the loaded ``FrameConfig.polling_schedules`` is shown
    as a labelled checkbox.  Selections are persisted per ``target_id`` in
    ``QSettings`` so they survive between sessions.
    """

    def __init__(self, schedules, settings: QSettings, parent=None, is_modbus: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Poll Schedule")
        self.setMinimumWidth(320)
        self._settings = settings
        self._schedules = schedules
        self._is_modbus = is_modbus

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel("Select which targets to poll automatically:", self)
        header.setWordWrap(True)
        layout.addWidget(header)

        self._list = QListWidget(self)
        for sched in schedules:
            key = f"poll/enabled/0x{sched.target_id:04X}"
            # Default to whatever the config says, but QSettings overrides it.
            default_checked = sched.enabled
            checked = settings.value(key, default_checked, type=bool)
            label = f"0x{sched.target_id:04X}  —  every {sched.interval_ms} ms"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, sched.target_id)
            self._list.addItem(item)
        layout.addWidget(self._list)

        # Select-all / none shortcuts
        btn_row = QHBoxLayout()
        all_btn = QPushButton("Select All", self)
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn = QPushButton("Select None", self)
        none_btn.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        layout.addLayout(btn_row)

        # Pipelining is useful only for devices that explicitly tolerate
        # multiple outstanding poll requests. Hardware that processes one
        # command at a time can drop or delay overlapped requests, so the
        # default is the safer sequential mode.
        self._pipeline_chk = QCheckBox("Pipeline poll requests", self)
        self._pipeline_chk.setToolTip(
            "Send up to N polls without waiting for each response. Replies "
            "are matched by frame_id. Disable if the device drops or "
            "corrupts overlapping requests. Not available for Modbus RTU."
        )
        self._pipeline_chk.setChecked(
            settings.value("poll/pipelining", False, type=bool)
        )

        self._pipeline_depth = QSpinBox(self)
        self._pipeline_depth.setRange(1, 16)
        self._pipeline_depth.setValue(int(settings.value("poll/pipeline_depth", 1)))
        self._pipeline_depth.setToolTip("Max number of in-flight poll requests.")
        self._pipeline_depth.setEnabled(self._pipeline_chk.isChecked())
        self._pipeline_chk.toggled.connect(self._pipeline_depth.setEnabled)

        if self._is_modbus:
            self._pipeline_chk.setChecked(False)
            self._pipeline_chk.setEnabled(False)
            self._pipeline_chk.setToolTip(
                "Pipelined polling is disabled for Modbus RTU. Modbus RTU "
                "responses do not carry transaction tags to match them back to "
                "requests, requiring strictly sequential polling."
            )
            self._pipeline_depth.setEnabled(False)
            self._pipeline_depth.setValue(1)
            self._pipeline_depth.setToolTip(
                "Modbus RTU requires sequential polling (max 1 in-flight)."
            )

        # Per-TX spacing floor — applies to BOTH sequential and pipelined
        # polling. Default 100 ms because real-hardware testing on a
        # multi-target BMS showed anything smaller (25-75 ms) caused the
        # device to drop polls fired too soon after its previous response.
        # Some devices may tolerate less; tune downward if your hardware
        # is reliable at faster cadence.
        self._pipeline_gap_ms = QSpinBox(self)
        self._pipeline_gap_ms.setRange(0, 500)
        self._pipeline_gap_ms.setSuffix(" ms")
        self._pipeline_gap_ms.setValue(int(settings.value(
            "poll/pipeline_tx_gap_ms", POLL_PIPELINE_TX_GAP_FLOOR_MS
        )))
        self._pipeline_gap_ms.setToolTip(
            "Minimum spacing between consecutive polls. Applies to both "
            "sequential and pipelined modes. 100 ms is the safe default; "
            "tune down only if your device tolerates faster cadence."
        )

        pipe_row = QHBoxLayout()
        pipe_row.setSpacing(8)
        pipe_row.addWidget(self._pipeline_chk)
        pipe_row.addStretch(1)
        pipe_row.addWidget(QLabel("Max in-flight:", self))
        pipe_row.addWidget(self._pipeline_depth)
        pipe_row.addWidget(QLabel("TX gap:", self))
        pipe_row.addWidget(self._pipeline_gap_ms)
        layout.addLayout(pipe_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start Polling")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(state)

    def _on_accept(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            target_id = item.data(Qt.ItemDataRole.UserRole)
            key = f"poll/enabled/0x{target_id:04X}"
            self._settings.setValue(key, item.checkState() == Qt.CheckState.Checked)
        self._settings.setValue("poll/pipelining", self._pipeline_chk.isChecked())
        self._settings.setValue("poll/pipeline_depth", int(self._pipeline_depth.value()))
        self._settings.setValue("poll/pipeline_tx_gap_ms", int(self._pipeline_gap_ms.value()))
        self.accept()

    def get_enabled_ids(self) -> set:
        """Return the set of target_ids whose checkbox is checked."""
        result = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.add(item.data(Qt.ItemDataRole.UserRole))
        return result

    def get_pipelining(self) -> Tuple[bool, int, int]:
        """Return (enabled, max_in_flight, tx_gap_ms) for pipelined polling."""
        gap_ms = int(self._pipeline_gap_ms.value())
        if self._is_modbus:
            return False, 1, gap_ms
        depth = int(self._pipeline_depth.value())
        return self._pipeline_chk.isChecked() and depth > 1, depth, gap_ms


class LoggingSettingsDialog(QDialog):
    """Modal dialog for configuring logging level and CSV flush interval."""

    _LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

    def __init__(self, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Logging Settings")
        self.setMinimumWidth(320)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel("Configure application logging output:", self)
        header.setWordWrap(True)
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._level_combo = QComboBox(self)
        self._level_combo.addItems(list(self._LEVELS))

        self._flush_spin = QDoubleSpinBox(self)
        self._flush_spin.setRange(0.0, 10.0)
        self._flush_spin.setDecimals(2)
        self._flush_spin.setSingleStep(0.1)
        self._flush_spin.setSuffix(" s")
        self._flush_spin.setToolTip("0.0 = flush every write")

        form.addRow("Log level", self._level_combo)
        form.addRow("Flush interval", self._flush_spin)
        layout.addLayout(form)

        note = QLabel(
            "Flush interval applies to the raw CSV logger. 0.0 flushes every write. (Decoded .xlsx logs are written on Stop.)",
            self,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._restore_from_settings()

    def _restore_from_settings(self) -> None:
        level = str(self._settings.value("logging/level", "INFO")).upper()
        if level not in self._LEVELS:
            level = "INFO"
        self._level_combo.setCurrentText(level)

        raw_interval = self._settings.value("logging/flush_interval_s", 0.5)
        try:
            interval = float(raw_interval)
        except (TypeError, ValueError):
            interval = 0.5
        if interval < 0:
            interval = 0.0
        self._flush_spin.setValue(interval)

    def _on_accept(self) -> None:
        self._settings.setValue("logging/level", self._level_combo.currentText())
        self._settings.setValue("logging/flush_interval_s", self._flush_spin.value())
        self.accept()

    def get_values(self) -> Tuple[str, float]:
        return self._level_combo.currentText(), float(self._flush_spin.value())


class YRangeDialog(QDialog):
    """Modal dialog to type a fixed Y-axis range for a plot panel.

    Used when a panel is in Manual Y-scale mode. Defaults to the panel's
    current view range so the user can tweak rather than start from zero.
    """

    def __init__(
        self,
        parent: QWidget | None,
        panel_label: str,
        current_min: float,
        current_max: float,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Set Y Range — {panel_label}")
        self.setModal(True)
        self.resize(280, 130)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel(
            "Locks the y-axis to a fixed range. Mouse pan/zoom still works "
            "and overrides what you type here.",
            self,
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Range chosen to cover BMS signal scales (mV cells through pack
        # voltage / temperatures) without being so wide that typo'd values
        # blow the axis off-screen.
        self._min_spin = QDoubleSpinBox(self)
        self._min_spin.setRange(-1e9, 1e9)
        self._min_spin.setDecimals(3)
        self._min_spin.setSingleStep(1.0)
        self._min_spin.setValue(float(current_min))

        self._max_spin = QDoubleSpinBox(self)
        self._max_spin.setRange(-1e9, 1e9)
        self._max_spin.setDecimals(3)
        self._max_spin.setSingleStep(1.0)
        self._max_spin.setValue(float(current_max))

        form.addRow("Y min", self._min_spin)
        form.addRow("Y max", self._max_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if self._max_spin.value() <= self._min_spin.value():
            # Reject silently rather than pop a second dialog — the spin
            # boxes are right there for the user to fix.
            self._max_spin.setFocus()
            self._max_spin.selectAll()
            return
        self.accept()

    def get_range(self) -> Tuple[float, float]:
        return float(self._min_spin.value()), float(self._max_spin.value())


class PlotTriggerDialog(QDialog):
    """Modal dialog to configure an auto-pause trigger for the live plot."""

    def __init__(self, signals: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Auto-Pause Trigger")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        desc = QLabel("Automatically trigger actions when a parameter crosses a threshold.", self)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        form = QFormLayout()

        self._param_combo = QComboBox(self)
        self._param_combo.addItems(sorted(signals))

        self._op_combo = QComboBox(self)
        self._op_combo.addItems([">", "<", "==", ">=", "<=", "!="])

        self._val_spin = QDoubleSpinBox(self)
        self._val_spin.setRange(-1e9, 1e9)
        self._val_spin.setDecimals(4)
        self._val_spin.setValue(0.0)

        form.addRow("Parameter:", self._param_combo)
        form.addRow("Operator:", self._op_combo)
        form.addRow("Threshold:", self._val_spin)

        self._action_pause = QCheckBox("Pause Live Plot", self)
        self._action_pause.setChecked(True)
        self._action_log = QCheckBox("Start Logging", self)

        form.addRow("Action:", self._action_pause)
        form.addRow("", self._action_log)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Arm Trigger")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_trigger(self) -> dict:
        return {
            "param": self._param_combo.currentText(),
            "op": self._op_combo.currentText(),
            "value": self._val_spin.value(),
            "pause": self._action_pause.isChecked(),
            "log": self._action_log.isChecked(),
        }


class PlotSettingsDialog(QDialog):
    """Modal dialog for configuring live plot memory history and defaults."""

    def __init__(self, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plot Settings")
        self.setMinimumWidth(340)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._cap_chk = QCheckBox("Cap live plot memory history", self)
        self._cap_spin = QSpinBox(self)
        self._cap_spin.setRange(1000, 10_000_000)
        self._cap_spin.setSingleStep(10000)
        self._cap_spin.setSuffix(" samples")

        # Link checkbox to spinbox enabled state
        self._cap_chk.toggled.connect(self._cap_spin.setEnabled)

        self._window_combo = QComboBox(self)
        self._window_combo.addItems([
            "30 seconds", "1 minute", "2 minutes", "5 minutes",
            "10 minutes", "30 minutes", "All session"
        ])

        form.addRow(self._cap_chk)
        form.addRow("Memory cap limit", self._cap_spin)
        form.addRow("Default display window", self._window_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._restore_from_settings()

    def _restore_from_settings(self) -> None:
        s = self._settings
        raw_cap = s.value("plot/history_max_samples", 0)
        try:
            cap_val = int(raw_cap)
        except (TypeError, ValueError):
            cap_val = 0

        if cap_val > 0:
            self._cap_chk.setChecked(True)
            self._cap_spin.setEnabled(True)
            self._cap_spin.setValue(cap_val)
        else:
            self._cap_chk.setChecked(False)
            self._cap_spin.setEnabled(False)
            self._cap_spin.setValue(100_000)

        window_s = s.value("plot/window_seconds", 300)
        try:
            w_val = int(window_s)
        except (TypeError, ValueError):
            w_val = 300

        mapping = {30: 0, 60: 1, 120: 2, 300: 3, 600: 4, 1800: 5, 0: 6}
        self._window_combo.setCurrentIndex(mapping.get(w_val, 3))

    def _on_accept(self) -> None:
        s = self._settings
        cap_val = self._cap_spin.value() if self._cap_chk.isChecked() else 0
        s.setValue("plot/history_max_samples", cap_val)

        window_mapping = {0: 30, 1: 60, 2: 120, 3: 300, 4: 600, 5: 1800, 6: 0}
        w_val = window_mapping.get(self._window_combo.currentIndex(), 300)
        s.setValue("plot/window_seconds", w_val)

        self.accept()

    def get_values(self) -> tuple[int, int]:
        cap_val = self._cap_spin.value() if self._cap_chk.isChecked() else 0
        window_mapping = {0: 30, 1: 60, 2: 120, 3: 300, 4: 600, 5: 1800, 6: 0}
        w_val = window_mapping.get(self._window_combo.currentIndex(), 300)
        return cap_val, w_val


class SchemaMapperDialog(QDialog):
    """Modal dialog for configuring sheet names and elapsed column mappings for log import."""

    def __init__(self, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Schema Mapper")
        self.setMinimumWidth(400)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QLabel(
            "Configure column/sheet headers for importing custom log files:",
            self
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._sheets_edit = QLineEdit(self)
        self._sheets_edit.setToolTip("Comma-separated list of sheet names to try first (e.g. Data,Record,Sheet1).")

        self._cols_edit = QLineEdit(self)
        self._cols_edit.setToolTip("Comma-separated list of elapsed time column names (e.g. Elapsed (s),elapsed_ms,.elapsed_ms).")

        self._scale_edit = QPlainTextEdit(self)
        self._scale_edit.setPlaceholderText("col_name_1: scale_1\ncol_name_2: scale_2")
        self._scale_edit.setMaximumHeight(80)
        self._scale_edit.setToolTip("Scale factor to seconds (e.g. elapsed_ms: 0.001 to convert ms to seconds).")

        form.addRow("Sheet Names", self._sheets_edit)
        form.addRow("Time Columns", self._cols_edit)
        form.addRow("Time Scale Mapping", self._scale_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._restore_from_settings()

    def _restore_from_settings(self) -> None:
        s = self._settings
        sheets = s.value("import/sheet_names", "Data,Record")
        self._sheets_edit.setText(str(sheets))

        cols = s.value("import/elapsed_cols", "Elapsed (s),elapsed_ms")
        self._cols_edit.setText(str(cols))

        scale_val = s.value("import/elapsed_scales", "Elapsed (s): 1.0\nelapsed_ms: 0.001")
        self._scale_edit.setPlainText(str(scale_val))

    def _on_accept(self) -> None:
        s = self._settings
        s.setValue("import/sheet_names", self._sheets_edit.text().strip())
        s.setValue("import/elapsed_cols", self._cols_edit.text().strip())
        s.setValue("import/elapsed_scales", self._scale_edit.toPlainText().strip())
        self.accept()


class AboutDialog(QDialog):
    """Industry-standard About dialog for Bytehound."""

    def __init__(self, version_info: dict, logo_path: str | Path | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Bytehound")
        self.setModal(True)
        self.setFixedSize(540, 270)

        # Remove help button from title bar
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Main horizontal layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(24)

        # Import PySide6 GUI / Utility classes locally
        from PySide6.QtGui import QPixmap, QDesktopServices
        from PySide6.QtCore import QUrl, QSize
        from PySide6.QtWidgets import QToolButton
        try:
            import qtawesome as qta
        except ImportError:
            qta = None

        # Resolve Theme and Colors for qtawesome icons
        from .theming import resolve_theme
        theme = str(QSettings("Bytehound", "Bytehound").value("ui/theme", "dark"))
        is_dark = (resolve_theme(theme) == "dark")
        icon_color = "#CBD5E1" if is_dark else "#475569"
        accent_color = "#38BDF8" if is_dark else "#2563EB"

        # Left Column: Logo & Homepage Button
        left_column = QWidget(self)
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        logo_label = QLabel(left_column)
        if logo_path:
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                logo_label.setPixmap(pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                logo_label.setText("🐶")
                logo_label.setStyleSheet("font-size: 48px;")
        else:
            logo_label.setText("🐶")
            logo_label.setStyleSheet("font-size: 48px;")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(logo_label)

        # Homepage / GitHub Repository Button
        homepage = version_info.get("homepage", "https://bytehound.shreyasp182002.workers.dev/")
        btn_repo = QPushButton("Visit Homepage", left_column)
        btn_repo.setCursor(Qt.PointingHandCursor)
        btn_repo.setToolTip("View project homepage")
        btn_repo.setStyleSheet("font-size: 9pt; font-weight: bold; padding: 4px 8px;")
        if qta:
            btn_repo.setIcon(qta.icon("mdi6.earth", color=icon_color))
        btn_repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(homepage)))
        left_layout.addWidget(btn_repo)
        left_layout.addStretch(1)

        main_layout.addWidget(left_column)

        # Right Column: Details
        details_widget = QWidget(self)
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(6)

        # App Name & version
        app_name = QLabel("Bytehound", self)
        app_name.setStyleSheet("font-size: 16pt; font-weight: bold;")
        details_layout.addWidget(app_name)

        version = version_info.get("version", "0.0.0")
        build_date = version_info.get("build_date", "")
        version_text = f"Version {version}"
        if build_date:
            version_text += f" ({build_date})"
        version_label = QLabel(version_text, self)
        version_label.setStyleSheet("font-size: 9.5pt; color: gray;")
        details_layout.addWidget(version_label)

        # Description / Tagline
        desc_label = QLabel("Serial Data Logger, Parser and Visualizer.", self)
        desc_label.setStyleSheet("font-size: 9.5pt; color: gray; font-style: italic;")
        details_layout.addWidget(desc_label)

        # Thin divider
        divider = QWidget(self)
        divider.setFixedHeight(1)
        divider_color = "#334155" if is_dark else "#E5E7EB"
        divider.setStyleSheet(f"background-color: {divider_color};")
        details_layout.addWidget(divider)

        # Publisher section (name and webpage link)
        publisher = version_info.get("publisher", "DECIBELS LAB PRIVATE LIMITED")
        pub_webpage = version_info.get("publisher_webpage", "https://lms.decibelslab.com/")
        publisher_label = QLabel(self)
        publisher_label.setText(f"Publisher: <b>{publisher}</b> &nbsp;(<a href='{pub_webpage}'>Website</a>)")
        publisher_label.setOpenExternalLinks(True)
        publisher_label.setWordWrap(True)
        publisher_label.setStyleSheet("font-size: 9.5pt;")
        details_layout.addWidget(publisher_label)

        # Developer Section with Inline GitHub Icon Button
        dev = version_info.get("Developer", "Shreyas P")
        dev_github = version_info.get("developer_github", "https://github.com/P-Shreyas543")

        dev_widget = QWidget(self)
        dev_hl = QHBoxLayout(dev_widget)
        dev_hl.setContentsMargins(0, 0, 0, 0)
        dev_hl.setSpacing(4)

        dev_label = QLabel(f"Developer: <a href='{dev_github}'><b>{dev}</b></a>", dev_widget)
        dev_label.setOpenExternalLinks(True)
        dev_label.setStyleSheet("font-size: 9.5pt;")
        dev_hl.addWidget(dev_label)

        if dev_github:
            btn_dev_git = QToolButton(dev_widget)
            btn_dev_git.setCursor(Qt.PointingHandCursor)
            btn_dev_git.setToolTip("Developer GitHub Profile")
            btn_dev_git.setStyleSheet("QToolButton { border: none; background: transparent; padding: 0; }")
            btn_dev_git.setFixedSize(18, 18)
            btn_dev_git.setIconSize(QSize(16, 16))
            if qta:
                btn_dev_git.setIcon(qta.icon("mdi6.github", color=accent_color))
            else:
                btn_dev_git.setText("🔗")
            btn_dev_git.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(dev_github)))
            dev_hl.addWidget(btn_dev_git)
        dev_hl.addStretch(1)
        details_layout.addWidget(dev_widget)

        # License Section (clickable hyperlink)
        lic = version_info.get("license", "MIT")
        lic_url = version_info.get("license_url", "https://bytehound.shreyasp182002.workers.dev/LICENSE")
        lic_text = f"<a href='{lic_url}'><b>{lic}</b></a>" if lic_url else f"<b>{lic}</b>"

        license_label = QLabel(self)
        license_label.setText(f"License: {lic_text}")
        license_label.setOpenExternalLinks(True)
        license_label.setStyleSheet("font-size: 9.5pt;")
        details_layout.addWidget(license_label)

        details_layout.addStretch()

        # OK button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        button_box.accepted.connect(self.accept)
        details_layout.addWidget(button_box)

        main_layout.addWidget(details_widget, 1)


from PySide6.QtCore import Signal

class GithubDescriptionEdit(QPlainTextEdit):
    file_dropped = Signal(str)
    image_pasted = Signal(bytes, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText(
            "Please describe the issue in detail, including steps to reproduce...\n"
            "Attach files by dragging & dropping, selecting or pasting them."
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path:
                    self.file_dropped.emit(file_path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def insertFromMimeData(self, source):
        if source.hasImage():
            image = source.imageData()
            from PySide6.QtCore import QBuffer, QByteArray
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.OpenModeFlag.WriteOnly)
            if image.save(buf, "PNG"):
                self.image_pasted.emit(ba.data(), "PNG")
                self.insertPlainText("\n[Pasted Image Attachment]\n")
                return
        super().insertFromMimeData(source)


class ReportIssueDialog(QDialog):
    """Modal dialog for submitting a bug report or issue to the developers."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Report Issue")
        self.setMinimumWidth(500)
        self._attachments: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._title_input = QLineEdit(self)
        self._title_input.setPlaceholderText("Brief summary of the issue")

        self._desc_input = GithubDescriptionEdit(self)
        self._desc_input.setMinimumHeight(150)
        self._desc_input.file_dropped.connect(self._add_attachment)
        self._desc_input.image_pasted.connect(self._add_pasted_image)

        form.addRow("Title", self._title_input)
        form.addRow("Description", self._desc_input)

        # Attachment row controls
        attach_control_row = QWidget(self)
        attach_hl = QHBoxLayout(attach_control_row)
        attach_hl.setContentsMargins(0, 0, 0, 0)

        self._btn_attach = QPushButton("📎 Attach files / images...", attach_control_row)
        self._btn_attach.clicked.connect(self._browse_attachments)
        attach_hl.addWidget(self._btn_attach)

        hint = QLabel("Pasting images or dragging & dropping files also works.", attach_control_row)
        hint.setStyleSheet("color: gray; font-size: 9pt;")
        attach_hl.addWidget(hint)
        attach_hl.addStretch(1)

        form.addRow("", attach_control_row)

        # List of attached files
        list_container = QWidget(self)
        list_vl = QVBoxLayout(list_container)
        list_vl.setContentsMargins(0, 0, 0, 0)
        list_vl.setSpacing(4)

        self._list_widget = QListWidget(list_container)
        self._list_widget.setMaximumHeight(80)
        self._list_widget.setVisible(False)
        list_vl.addWidget(self._list_widget)

        self._btn_remove = QPushButton("Remove Selected Attachment", list_container)
        self._btn_remove.clicked.connect(self._remove_selected_attachment)
        self._btn_remove.setVisible(False)
        list_vl.addWidget(self._btn_remove)

        form.addRow("Attachments", list_container)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Submit")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_attachments(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files or Images to Attach",
            "",
            "All Files (*.*);;Images (*.png *.jpg *.jpeg *.gif *.bmp);;Logs/Data (*.csv *.txt *.log *.xlsx)"
        )
        for f in files:
            self._add_attachment(f)

    def _add_attachment(self, file_path: str) -> None:
        from datetime import datetime
        import base64
        path = Path(file_path)
        if not path.is_file():
            return

        size = path.stat().st_size
        if size > 2 * 1024 * 1024:
            QMessageBox.warning(
                self,
                "File Too Large",
                f"The file '{path.name}' is {size / 1024 / 1024:.1f}MB.\n"
                "Please attach files smaller than 2MB to keep report submission reliable."
            )
            return

        total_size = sum(att['size'] for att in self._attachments) + size
        if total_size > 5 * 1024 * 1024:
            QMessageBox.warning(
                self,
                "Attachment Limit Exceeded",
                "Total size of all attachments exceeds 5MB."
            )
            return

        try:
            with path.open("rb") as f:
                data = f.read()
        except Exception as e:
            QMessageBox.warning(self, "Read Error", f"Could not read '{path.name}':\n{e}")
            return

        is_image = path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
        b64_data = base64.b64encode(data).decode('utf-8')

        name = path.name
        if any(att['name'] == name for att in self._attachments):
            name = f"{path.stem}_{datetime.now().strftime('%M%S')}{path.suffix}"

        self._attachments.append({
            'name': name,
            'data': data,
            'b64_data': b64_data,
            'is_image': is_image,
            'size': size
        })
        self._update_attachments_list()

    def _add_pasted_image(self, data: bytes, format_name: str) -> None:
        from datetime import datetime
        import base64
        size = len(data)
        if size > 2 * 1024 * 1024:
            QMessageBox.warning(self, "Image Too Large", "Pasted image is too large.")
            return

        total_size = sum(att['size'] for att in self._attachments) + size
        if total_size > 5 * 1024 * 1024:
            QMessageBox.warning(self, "Attachment Limit Exceeded", "Total size of all attachments exceeds 5MB.")
            return

        b64_data = base64.b64encode(data).decode('utf-8')
        name = f"pasted_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        self._attachments.append({
            'name': name,
            'data': data,
            'b64_data': b64_data,
            'is_image': True,
            'size': size
        })
        self._update_attachments_list()

    def _update_attachments_list(self) -> None:
        self._list_widget.clear()
        for att in self._attachments:
            size_kb = att['size'] / 1024
            self._list_widget.addItem(f"{att['name']} ({size_kb:.1f} KB)")

        has_items = len(self._attachments) > 0
        self._list_widget.setVisible(has_items)
        self._btn_remove.setVisible(has_items)

    def _remove_selected_attachment(self) -> None:
        row = self._list_widget.currentRow()
        if row >= 0 and row < len(self._attachments):
            del self._attachments[row]
            self._update_attachments_list()

    def _on_accept(self) -> None:
        if not self._title_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Title is required.")
            return
        if not self._desc_input.toPlainText().strip():
            QMessageBox.warning(self, "Validation Error", "Description is required.")
            return
        self.accept()

    def get_data(self) -> tuple[str, str, list[dict]]:
        return (
            self._title_input.text().strip(),
            self._desc_input.toPlainText().strip(),
            self._attachments,
        )


