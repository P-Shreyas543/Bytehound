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
        header.setStyleSheet("QFrame { background-color: #1e293b; border-radius: 12px; padding: 16px; }")
        header_layout = QHBoxLayout(header)

        title_v = QVBoxLayout()
        app_title = QLabel("🐾 Bytehound Telemetry & Control Suite")
        app_title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        app_title.setStyleSheet("color: #38bdf8;")

        app_subtitle = QLabel("Framed Serial Telemetry Logger, Command Controller & Multi-Grid Oscilloscope")
        app_subtitle.setFont(QFont("Segoe UI", 10))
        app_subtitle.setStyleSheet("color: #94a3b8;")

        title_v.addWidget(app_title)
        title_v.addWidget(app_subtitle)
        header_layout.addLayout(title_v)
        header_layout.addStretch()

        help_btn = QPushButton("📚 Open User Guide")
        help_btn.setStyleSheet("""
            QPushButton { background-color: #0f766e; color: white; font-weight: bold; border-radius: 6px; padding: 8px 16px; }
            QPushButton:hover { background-color: #14b8a6; }
        """)
        help_btn.clicked.connect(self.open_manual_requested.emit)
        header_layout.addWidget(help_btn)

        main_layout.addWidget(header)

        # 3-Step Guided Grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(16)

        # Step 1: Hardware Connection Card
        step1_box = QGroupBox("1. Hardware Connection")
        step1_box.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        step1_box.setStyleSheet("QGroupBox { border: 1px solid #334155; border-radius: 8px; margin-top: 12px; padding: 16px; } QGroupBox::title { color: #f8fafc; subcontrol-origin: margin; left: 12px; padding: 0 4px; }")
        s1_layout = QVBoxLayout(step1_box)

        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.baud_combo.setCurrentText("115200")

        self.refresh_ports_btn = QPushButton("🔄 Refresh Ports")
        self.refresh_ports_btn.setStyleSheet("QPushButton { background-color: #334155; color: white; border-radius: 4px; padding: 6px; } QPushButton:hover { background-color: #475569; }")

        port_h = QHBoxLayout()
        port_h.addWidget(QLabel("COM Port:"))
        port_h.addWidget(self.port_combo, 1)
        port_h.addWidget(self.refresh_ports_btn)

        baud_h = QHBoxLayout()
        baud_h.addWidget(QLabel("Baud Rate:"))
        baud_h.addWidget(self.baud_combo, 1)

        self.connect_btn = QPushButton("⚡ Connect Serial Device")
        self.connect_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.connect_btn.setStyleSheet("""
            QPushButton { background-color: #16a34a; color: white; border-radius: 6px; padding: 10px; }
            QPushButton:hover { background-color: #22c55e; }
        """)
        self.connect_btn.clicked.connect(self._on_connect_clicked)

        s1_layout.addLayout(port_h)
        s1_layout.addLayout(baud_h)
        s1_layout.addSpacing(10)
        s1_layout.addWidget(self.connect_btn)

        # Step 2: Protocol Selection Card
        step2_box = QGroupBox("2. Protocol Configuration")
        step2_box.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        step2_box.setStyleSheet("QGroupBox { border: 1px solid #334155; border-radius: 8px; margin-top: 12px; padding: 16px; } QGroupBox::title { color: #f8fafc; subcontrol-origin: margin; left: 12px; padding: 0 4px; }")
        s2_layout = QVBoxLayout(step2_box)

        s2_desc = QLabel("Select a preset protocol template or load your custom configuration file:")
        s2_desc.setStyleSheet("color: #cbd5e1;")

        self.preset_combo = QComboBox()
        for p_name in BUILTIN_PRESETS.keys():
            self.preset_combo.addItem(f"Preset: {p_name}", p_name)

        apply_preset_btn = QPushButton("✓ Use Selected Preset")
        apply_preset_btn.setStyleSheet("QPushButton { background-color: #2563eb; color: white; font-weight: bold; border-radius: 4px; padding: 6px; } QPushButton:hover { background-color: #3b82f6; }")
        apply_preset_btn.clicked.connect(self._on_preset_applied)

        load_file_btn = QPushButton("📂 Load Config (.xlsx / CSV)")
        load_file_btn.setStyleSheet("QPushButton { background-color: #475569; color: white; border-radius: 4px; padding: 6px; } QPushButton:hover { background-color: #64748b; }")
        load_file_btn.clicked.connect(self.load_config_requested.emit)

        wizard_btn = QPushButton("🪄 Open Visual Protocol Wizard")
        wizard_btn.setStyleSheet("QPushButton { background-color: #d97706; color: white; font-weight: bold; border-radius: 4px; padding: 8px; } QPushButton:hover { background-color: #f59e0b; }")
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
        step3_box.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        step3_box.setStyleSheet("QGroupBox { border: 1px solid #334155; border-radius: 8px; margin-top: 12px; padding: 16px; } QGroupBox::title { color: #f8fafc; subcontrol-origin: margin; left: 12px; padding: 0 4px; }")
        s3_layout = QVBoxLayout(step3_box)

        self.recent_list = QListWidget()
        self.recent_list.setStyleSheet("QListWidget { background-color: #0f172a; border: 1px solid #334155; border-radius: 4px; color: #e2e8f0; padding: 4px; } QListWidget::item:hover { background-color: #1e293b; }")
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
