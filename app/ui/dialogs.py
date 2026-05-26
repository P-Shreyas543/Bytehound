"""Configuration dialogs for the Serial monitor app."""

from typing import Tuple

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSpinBox,
    QVBoxLayout, QWidget
)

from ..decoder.types import SerialDefaults
from ..serial_io.serial_worker import (
    POLL_PIPELINE_TX_GAP_FLOOR_MS,
    SerialSettings,
    available_ports,
)


class ConnectionDialog(QDialog):
    """Modal dialog for configuring and opening a serial connection.

    Field-priority order on open is QSettings → loaded config's
    ``SerialDefaults`` → hard-coded fallback. That means the user's
    explicit last-used choice always wins, but a freshly loaded config
    with bespoke serial defaults (say, 9600 / E / 2 stop bits for a
    Modbus device) pre-populates the dialog on first open instead of
    showing the generic 115200 / N / 1 fallback.

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
        self.setWindowTitle("Serial Connection Settings")
        self.setMinimumWidth(360)
        self._settings = settings
        self._config_defaults = config_defaults or SerialDefaults()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Port row with inline Refresh button
        port_row = QWidget(self)
        port_hl = QHBoxLayout(port_row)
        port_hl.setContentsMargins(0, 0, 0, 0)
        self._port_combo = QComboBox(port_row)
        self._port_combo.setMinimumWidth(180)
        refresh_btn = QPushButton("⟳", port_row)
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh port list")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_hl.addWidget(self._port_combo, 1)
        port_hl.addWidget(refresh_btn)

        self._baud_combo = QComboBox(self)
        self._baud_combo.addItems(["9600", "19200", "38400", "57600", "115200",
                                    "230400", "460800", "921600"])

        self._data_bits_combo = QComboBox(self)
        self._data_bits_combo.addItems(["8", "7"])

        self._stop_bits_combo = QComboBox(self)
        self._stop_bits_combo.addItems(["1", "1.5", "2"])

        self._parity_combo = QComboBox(self)
        self._parity_combo.addItems(["N", "E", "O"])

        self._timeout_combo = QComboBox(self)
        self._timeout_combo.addItems(["20", "50", "100", "250", "500", "1000"])

        form.addRow("Port", port_row)
        form.addRow("Baud rate", self._baud_combo)
        form.addRow("Data bits", self._data_bits_combo)
        form.addRow("Stop bits", self._stop_bits_combo)
        form.addRow("Parity", self._parity_combo)
        form.addRow("Timeout (ms)", self._timeout_combo)
        layout.addLayout(form)

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

    def _restore_from_settings(self) -> None:
        s = self._settings
        saved_port = s.value("conn/port", "")
        for i in range(self._port_combo.count()):
            if self._port_combo.itemData(i, Qt.ItemDataRole.UserRole) == saved_port:
                self._port_combo.setCurrentIndex(i)
                break
        # The config's SerialDefaults becomes the per-key fallback when
        # QSettings has no stored value yet. Stop_bits uses ``%g`` so 1.0
        # renders as "1" and matches the combo items "1", "1.5", "2".
        cd = self._config_defaults
        self._baud_combo.setCurrentText(str(s.value("conn/baud", str(cd.baud_rate))))
        self._data_bits_combo.setCurrentText(str(s.value("conn/data_bits", str(cd.data_bits))))
        self._stop_bits_combo.setCurrentText(str(s.value("conn/stop_bits", f"{cd.stop_bits:g}")))
        self._parity_combo.setCurrentText(str(s.value("conn/parity", cd.parity)))
        self._timeout_combo.setCurrentText(str(s.value("conn/timeout_ms", str(cd.timeout_ms))))

    def _on_accept(self) -> None:
        s = self._settings
        s.setValue("conn/port",       self._port_combo.currentData(Qt.ItemDataRole.UserRole) or "")
        s.setValue("conn/baud",       self._baud_combo.currentText())
        s.setValue("conn/data_bits",  self._data_bits_combo.currentText())
        s.setValue("conn/stop_bits",  self._stop_bits_combo.currentText())
        s.setValue("conn/parity",     self._parity_combo.currentText())
        s.setValue("conn/timeout_ms", self._timeout_combo.currentText())
        self.accept()

    def get_settings(self) -> "SerialSettings":
        return SerialSettings(
            port=self._port_combo.currentData(Qt.ItemDataRole.UserRole) or self._port_combo.currentText(),
            baud_rate=int(self._baud_combo.currentText()),
            data_bits=int(self._data_bits_combo.currentText()),
            stop_bits=float(self._stop_bits_combo.currentText()),
            parity=self._parity_combo.currentText(),
            timeout_ms=int(self._timeout_combo.currentText()),
        )


class PollingConfigDialog(QDialog):
    """Modal dialog for selecting which polling targets are active.

    Each target from the loaded ``FrameConfig.polling_schedules`` is shown
    as a labelled checkbox.  Selections are persisted per ``target_id`` in
    ``QSettings`` so they survive between sessions.
    """

    def __init__(self, schedules, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Poll Schedule")
        self.setMinimumWidth(320)
        self._settings = settings
        self._schedules = schedules

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
        depth = int(self._pipeline_depth.value())
        gap_ms = int(self._pipeline_gap_ms.value())
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
