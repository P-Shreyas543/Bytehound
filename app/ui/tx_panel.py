"""TX-command panel methods, extracted from MainWindow as a mixin.

This module is *not* meant to be instantiated alone — :class:`TxPanelMixin`
relies on a host that provides the MainWindow attributes and helpers it
touches (``self._config``, ``self._serial``, ``self._raw_logger``,
``self._console``, ``self._tx_bytes``, ``self._popup_warning(...)``,
``self._update_counts()``, ``self._log_activity(...)``). Mixing it into
``MainWindow`` keeps the call sites identical to the pre-extraction file
while shrinking ``main_window.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..commands.tx_command_builder import CommandBuildError, build_tx_command


class TxPanelMixin:
    """MainWindow mixin holding the TX-command tab UI + send/preview logic."""

    def _build_tx_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        self._tx_command_combo = QComboBox(widget)
        self._tx_command_combo.currentIndexChanged.connect(self._rebuild_tx_fields)
        self._tx_fields_widget = QWidget(widget)
        self._tx_fields_form = QFormLayout(self._tx_fields_widget)
        self._tx_preview = QPlainTextEdit(widget)
        self._tx_preview.setReadOnly(True)
        self._tx_preview.setMaximumHeight(90)
        build_button = QPushButton("Build", widget)
        build_button.clicked.connect(self._preview_tx_command)
        send_button = QPushButton("Send", widget)
        send_button.clicked.connect(self._send_tx_command)
        buttons = QHBoxLayout()
        buttons.addWidget(build_button)
        buttons.addWidget(send_button)
        layout.addWidget(QLabel("Command"))
        layout.addWidget(self._tx_command_combo)
        layout.addWidget(self._tx_fields_widget)
        layout.addLayout(buttons)
        layout.addWidget(QLabel("Packet Preview"))
        layout.addWidget(self._tx_preview)
        layout.addStretch(1)
        return widget

    def _populate_tx_commands(self) -> None:
        self._tx_command_combo.clear()
        self._tx_field_inputs.clear()
        if self._config is None:
            return
        self._tx_command_combo.addItems(sorted(self._config.tx_commands))
        self._rebuild_tx_fields()

    def _rebuild_tx_fields(self) -> None:
        while self._tx_fields_form.rowCount():
            self._tx_fields_form.removeRow(0)
        self._tx_field_inputs.clear()
        if self._config is None:
            return
        command = self._config.tx_commands.get(self._tx_command_combo.currentText())
        if command is None:
            return
        for tx_field in command.fields:
            editor = QLineEdit(self._tx_fields_widget)
            if tx_field.default is not None:
                editor.setText(f"{tx_field.default:g}")
            suffix = f" ({tx_field.unit})" if tx_field.unit else ""
            self._tx_fields_form.addRow(f"{tx_field.field_name}{suffix}", editor)
            self._tx_field_inputs[tx_field.field_name] = editor
        self._preview_tx_command()

    def _tx_values(self) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for name, editor in self._tx_field_inputs.items():
            text = editor.text().strip()
            if text:
                values[name] = float(text)
        return values

    def _build_current_tx_packet(self) -> bytes:
        if self._config is None:
            raise CommandBuildError("No configuration loaded")
        return build_tx_command(
            self._config, self._tx_command_combo.currentText(), self._tx_values()
        )

    def _preview_tx_command(self) -> None:
        try:
            packet = self._build_current_tx_packet()
        except (CommandBuildError, ValueError) as exc:
            self._tx_preview.setPlainText(str(exc))
            return
        self._tx_preview.setPlainText(packet.hex(" ").upper())

    def _send_tx_command(self) -> None:
        try:
            packet = self._build_current_tx_packet()
        except (CommandBuildError, ValueError) as exc:
            self._popup_warning("TX command", str(exc))
            return
        if self._serial is None or not self._serial.is_open:
            self._popup_warning("TX command", "Connect a serial port before sending.")
            return
        self._serial.enqueue_priority_tx(packet)
        self._tx_bytes += len(packet)
        if self._raw_logger:
            self._raw_logger.log("TX", packet)
        self._console.appendPlainText(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, TX, {packet.hex(' ').upper()}")
        self._update_counts()
        self._log_activity(
            f"[ACTION] TX command sent: {self._tx_command_combo.currentText()} "
            f"(raw=0x{packet.hex().upper()})"
        )
