"""Interactive Welcome & Quick Launch Dashboard Widget for Bytehound."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QGroupBox, QFrame, QListWidget, QListWidgetItem, QSizePolicy, QGridLayout
)

from ..decoder.protocol_presets import BUILTIN_PRESETS


class WelcomeDashboardWidget(QWidget):
    """Sleek startup & disconnected dashboard providing guided steps and presets."""

    connect_requested = Signal(str, int)  # port, baud
    load_config_requested = Signal()
    preset_selected = Signal(str)  # preset name
    open_wizard_requested = Signal()
    open_manual_requested = Signal()
    recent_config_selected = Signal(str)  # path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # Header Banner
        header = QFrame()
        header.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QHBoxLayout(header)

        title_v = QVBoxLayout()
        app_title = QLabel("🐾 Bytehound Telemetry & Control Suite")
        
        app_subtitle = QLabel("Framed Serial Telemetry Logger, Command Controller & Multi-Grid Oscilloscope")

        title_v.addWidget(app_title)
        title_v.addWidget(app_subtitle)
        header_layout.addLayout(title_v)
        header_layout.addStretch()

        help_btn = QPushButton("📚 Open User Guide")
        help_btn.setAccessibleName("Open User Guide")
        help_btn.setAccessibleDescription("Opens the documentation for Bytehound in your default browser.")
        help_btn.clicked.connect(self.open_manual_requested.emit)
        header_layout.addWidget(help_btn)

        main_layout.addWidget(header)

        # 3-Step Guided Grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(16)

        # Step 1: Hardware Connection Card
        step1_box = QGroupBox("1. Hardware Connection")
        s1_layout = QVBoxLayout(step1_box)

        self.port_combo = QComboBox()
        self.port_combo.setAccessibleName("Serial Port Selection")
        self.port_combo.setAccessibleDescription("Select the COM port of the connected hardware.")
        
        self.baud_combo = QComboBox()
        self.baud_combo.setAccessibleName("Baud Rate Selection")
        self.baud_combo.setAccessibleDescription("Select the baud rate for the serial connection.")
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.baud_combo.setCurrentText("115200")

        self.refresh_ports_btn = QPushButton("🔄 Refresh Ports")
        self.refresh_ports_btn.setAccessibleName("Refresh Ports Button")

        port_h = QHBoxLayout()
        port_h.addWidget(QLabel("COM Port:"))
        port_h.addWidget(self.port_combo, 1)
        port_h.addWidget(self.refresh_ports_btn)

        baud_h = QHBoxLayout()
        baud_h.addWidget(QLabel("Baud Rate:"))
        baud_h.addWidget(self.baud_combo, 1)

        self.connect_btn = QPushButton("⚡ Connect Serial Device")
        self.connect_btn.setAccessibleName("Connect Serial Device Button")
        self.connect_btn.setAccessibleDescription("Initiates the serial connection using the selected port and baud rate.")
        self.connect_btn.clicked.connect(self._on_connect_clicked)

        s1_layout.addLayout(port_h)
        s1_layout.addLayout(baud_h)
        s1_layout.addSpacing(10)
        s1_layout.addWidget(self.connect_btn)

        # Step 2: Protocol Selection Card
        step2_box = QGroupBox("2. Protocol Configuration")
        s2_layout = QVBoxLayout(step2_box)

        s2_desc = QLabel("Select a preset protocol template or load your custom configuration file:")

        self.preset_combo = QComboBox()
        for p_name in BUILTIN_PRESETS.keys():
            self.preset_combo.addItem(f"Preset: {p_name}", p_name)

        apply_preset_btn = QPushButton("✓ Use Selected Preset")
        apply_preset_btn.setAccessibleName("Apply Preset Button")
        apply_preset_btn.clicked.connect(self._on_preset_applied)

        load_file_btn = QPushButton("📂 Load Config (.xlsx / CSV)")
        load_file_btn.setAccessibleName("Load Configuration File Button")
        load_file_btn.clicked.connect(self.load_config_requested.emit)

        wizard_btn = QPushButton("🪄 Open Visual Protocol Wizard")
        wizard_btn.setAccessibleName("Open Protocol Wizard Button")
        wizard_btn.clicked.connect(self.open_wizard_requested.emit)

        preset_h = QHBoxLayout()
        preset_h.addWidget(self.preset_combo, 1)
        preset_h.addWidget(apply_preset_btn)

        s2_layout.addWidget(s2_desc)
        s2_layout.addLayout(preset_h)
        s2_layout.addWidget(load_file_btn)
        s2_layout.addSpacing(6)
        s2_layout.addWidget(wizard_btn)

        # Step 3: Recent Configurations & Quick Launch Card
        step3_box = QGroupBox("3. Recent Profiles")
        s3_layout = QVBoxLayout(step3_box)

        self.recent_list = QListWidget()
        self.recent_list.setAccessibleName("Recent Profiles List")
        self.recent_list.setAccessibleDescription("Double click a recent profile to instantly connect and load its configuration.")
        self.recent_list.itemDoubleClicked.connect(self._on_recent_double_clicked)

        s3_layout.addWidget(self.recent_list)

        grid_layout.addWidget(step1_box, 0, 0)
        grid_layout.addWidget(step2_box, 0, 1)
        grid_layout.addWidget(step3_box, 1, 0, 1, 2)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch()

    def update_ports(self, ports: List[str]) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        if not ports:
            self.port_combo.addItem("No COM ports found")
            self.connect_btn.setEnabled(False)
        else:
            self.port_combo.addItems(ports)
            self.connect_btn.setEnabled(True)
            if current in ports:
                self.port_combo.setCurrentText(current)
            else:
                from ..serial_io.serial_worker import auto_detect_primary_port
                primary = auto_detect_primary_port()
                if primary and primary in ports:
                    self.port_combo.setCurrentText(primary)

    def set_recent_configs(self, paths: List[str]) -> None:
        self.recent_list.clear()
        for p in paths:
            if not p:
                continue
            item = QListWidgetItem(f"📄 {Path(p).name}  ({p})")
            item.setData(Qt.UserRole, p)
            self.recent_list.addItem(item)

    def _on_connect_clicked(self) -> None:
        port = self.port_combo.currentText()
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            baud = 115200
        if port and port != "No COM ports found":
            self.connect_requested.emit(port, baud)

    def _on_preset_applied(self) -> None:
        preset_key = self.preset_combo.currentData()
        if preset_key:
            self.preset_selected.emit(preset_key)

    def _on_recent_double_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self.recent_config_selected.emit(path)
