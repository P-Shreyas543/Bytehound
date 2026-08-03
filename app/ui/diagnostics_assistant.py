"""Diagnostic Assistant and Toast Notification system for Bytehound."""

from __future__ import annotations

from typing import Optional, List
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QListWidget, QListWidgetItem, QGraphicsDropShadowEffect
)

from ..serial_io.serial_worker import list_available_ports
from ..decoder.types import FrameConfig


class SystemDiagnosticDialog(QDialog):
    """Integrated System Diagnostic Checkup Dialog."""

    def __init__(self, config: Optional[FrameConfig] = None, active_port: str = "", active_baud: int = 115200, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 Bytehound System Diagnostic Checkup")
        self.resize(650, 500)
        self.config = config
        self.active_port = active_port
        self.active_baud = active_baud
        self._init_ui()
        self._run_diagnostics()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("System & Hardware Diagnostics")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #38bdf8;")

        desc = QLabel("Automated diagnostic check of serial hardware, COM ports, framing configuration, and decoder parameters.")
        desc.setStyleSheet("color: #94a3b8;")

        self.results_list = QListWidget()
        self.results_list.setStyleSheet("""
            QListWidget { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 6px; color: #f8fafc; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #1e293b; }
        """)

        self.advice_box = QTextEdit()
        self.advice_box.setReadOnly(True)
        self.advice_box.setStyleSheet("QTextEdit { background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; font-family: Consolas; }")
        self.advice_box.setFixedHeight(120)

        btn_layout = QHBoxLayout()
        recheck_btn = QPushButton("🔄 Re-Run Checkup")
        recheck_btn.setStyleSheet("QPushButton { background-color: #2563eb; color: white; border-radius: 4px; padding: 6px 12px; } QPushButton:hover { background-color: #3b82f6; }")
        recheck_btn.clicked.connect(self._run_diagnostics)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_layout.addWidget(recheck_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self.results_list, 1)
        layout.addWidget(QLabel("Troubleshooting Guidance:"))
        layout.addWidget(self.advice_box)
        layout.addLayout(btn_layout)

    def _run_diagnostics(self) -> None:
        self.results_list.clear()
        advice: List[str] = []

        # 1. Check Ports
        ports = list_available_ports()
        if not ports:
            self._add_item("❌ Serial Ports", "No active COM ports detected on host system.", False)
            advice.append("• Connect your USB-to-Serial / UART adapter or BMS fixture into a USB port.")
        else:
            self._add_item("✅ Serial Ports", f"Detected {len(ports)} COM port(s): {', '.join(ports)}", True)

        # 2. Active Port Selection
        if self.active_port and self.active_port in ports:
            self._add_item("✅ Active Port Selection", f"Selected COM port '{self.active_port}' is present and ready.", True)
        elif self.active_port:
            self._add_item("⚠️ Active Port Selection", f"Selected port '{self.active_port}' was unplugged or disconnected.", False)
            advice.append("• Select an available COM port from the toolbar dropdown.")
        else:
            self._add_item("ℹ️ Active Port Selection", "No COM port currently selected for connection.", True)

        # 3. Protocol Config Schema
        if self.config is not None:
            frames_cnt = len(self.config.frames)
            sig_cnt = len(self.config.all_signals)
            tx_cnt = len(self.config.tx_commands)
            self._add_item("✅ Protocol Configuration", f"Loaded profile '{self.config.protocol.profile_name}': {frames_cnt} frames, {sig_cnt} signals, {tx_cnt} TX commands.", True)
        else:
            self._add_item("⚠️ Protocol Configuration", "No custom protocol workbook loaded (using default fallback).", False)
            advice.append("• Import a valid frame configuration workbook via File -> Import Config or use a starter preset.")

        # 4. Baud Rate Check
        if self.active_baud in (9600, 115200, 230400, 460800, 921600):
            self._add_item("✅ Baud Rate Alignment", f"Baud rate configured to standard value ({self.active_baud} bps).", True)
        else:
            self._add_item("ℹ️ Baud Rate Alignment", f"Using non-standard baud rate ({self.active_baud} bps). Ensure MCU matches exact rate.", True)

        if not advice:
            advice.append("✅ All system and protocol checks passed cleanly! System ready for telemetry data streaming.")

        self.advice_box.setText("\n".join(advice))

    def _add_item(self, title: str, details: str, passed: bool) -> None:
        item = QListWidgetItem(f"{title}\n   {details}")
        if passed:
            item.setForeground(QColor("#10b981"))
        elif "⚠️" in title:
            item.setForeground(QColor("#f59e0b"))
        else:
            item.setForeground(QColor("#ef4444"))
        self.results_list.addItem(item)


class ToastNotification(QFrame):
    """Floating non-intrusive notification toast banner."""

    def __init__(self, message: str, level: str = "info", duration_ms: int = 3500, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        bg_color = "#1e293b"
        border_color = "#3b82f6"
        icon = "ℹ️"
        if level == "success":
            border_color = "#10b981"
            icon = "✅"
        elif level == "warning":
            border_color = "#f59e0b"
            icon = "⚠️"
        elif level == "error":
            border_color = "#ef4444"
            icon = "❌"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 8px;
                padding: 10px 16px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffsetY(4)
        self.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self)
        lbl = QLabel(f"{icon}  {message}")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #f8fafc;")
        layout.addWidget(lbl)

        QTimer.singleShot(duration_ms, self.close)
