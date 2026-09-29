"""Remote Webhook Settings Modal Dialog (IMP-13)."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...comm.webhook_notifier import WebhookNotifier, WebhookSettings

logger = logging.getLogger("SingleCellCycler.WebhookDialog")


class WebhookSettingsDialog(QDialog):
    """Configuration modal for Discord, Slack, and Teams lab notifications."""

    def __init__(self, notifier: WebhookNotifier, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.notifier = notifier
        self.settings = notifier.settings

        self.setWindowTitle("Remote Lab Notifications (Webhook)")
        self.resize(560, 360)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #e2e8f0;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QLabel {
                color: #e2e8f0;
            }
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                color: #f8fafc;
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
            QCheckBox {
                color: #f8fafc;
                font-size: 12px;
                spacing: 8px;
            }
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #475569;
                color: #f8fafc;
                padding: 6px 14px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Title
        lbl_title = QLabel("Remote Lab Notifications")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #38bdf8;")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Configure incoming webhooks for Discord, Slack, or Microsoft Teams to receive "
            "unattended lab alerts during overnight qualification tests."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px; margin-bottom: 6px;")
        layout.addWidget(lbl_desc)

        # Form layout
        form = QFormLayout()
        form.setSpacing(10)

        self.chk_enable = QCheckBox("Enable remote webhook notifications")
        self.chk_enable.setStyleSheet("font-weight: 700; color: #34d399;")
        form.addRow("Status:", self.chk_enable)

        self.edit_url = QLineEdit()
        self.edit_url.setPlaceholderText("https://discord.com/api/webhooks/... or https://hooks.slack.com/...")
        form.addRow("Webhook URL:", self.edit_url)

        self.edit_operator = QLineEdit()
        self.edit_operator.setPlaceholderText("e.g. Lead Metrologist / Station A")
        form.addRow("Operator Tag:", self.edit_operator)

        layout.addLayout(form)

        # Event checkboxes
        layout.addWidget(QLabel("Notify on Events:"))
        self.chk_start = QCheckBox("Test Commenced (Recipe, Chemistry, Steps)")
        self.chk_step = QCheckBox("Step Completed (Capacity mAh, Energy Wh, Next Step, Cutoff)")
        self.chk_cycle = QCheckBox("Cycle Summary (Coulombic/Energy Efficiency, Capacity)")
        self.chk_pause = QCheckBox("Test Paused / Resumed Events")
        self.chk_estop = QCheckBox("Manual Emergency Stop (Instant Disconnect)")
        self.chk_trip = QCheckBox("Safety Interlock Trips (Immediate Voltage/Temp Alert)")
        self.chk_done = QCheckBox("Test Completed (Final Capacity, Energy Wh, Duration)")
        layout.addWidget(self.chk_start)
        layout.addWidget(self.chk_step)
        layout.addWidget(self.chk_cycle)
        layout.addWidget(self.chk_pause)
        layout.addWidget(self.chk_estop)
        layout.addWidget(self.chk_trip)
        layout.addWidget(self.chk_done)

        # Status feedback pill
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("font-size: 11px; padding: 4px; border-radius: 4px;")
        layout.addWidget(self.lbl_status)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_ping = QPushButton("🔔 Test Webhook Ping")
        self.btn_ping.setToolTip("Dispatch an immediate test ping to the entered webhook URL")
        self.btn_ping.clicked.connect(self._on_ping)
        btn_layout.addWidget(self.btn_ping)

        btn_layout.addStretch()

        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #0369a1;
                border: 1px solid #0284c7;
                color: #f0f9ff;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #0284c7;
            }
        """)
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _load_settings(self) -> None:
        s = self.settings
        self.chk_enable.setChecked(s.enabled)
        self.edit_url.setText(s.url)
        self.edit_operator.setText(s.operator_tag)
        self.chk_start.setChecked(s.notify_test_started)
        self.chk_step.setChecked(s.notify_step_completed)
        self.chk_cycle.setChecked(s.notify_cycle_completed)
        self.chk_pause.setChecked(s.notify_test_paused_resumed)
        self.chk_estop.setChecked(s.notify_emergency_stop)
        self.chk_trip.setChecked(s.notify_safety_trip)
        self.chk_done.setChecked(s.notify_test_completed)

    def _on_ping(self) -> None:
        url = self.edit_url.text().strip()
        if not url:
            self.lbl_status.setText("✕ Error: Please enter a Webhook URL first.")
            self.lbl_status.setStyleSheet("color: #f87171; background-color: #450a0a; padding: 4px;")
            return

        self.lbl_status.setText("⏳ Dispatching test ping...")
        self.lbl_status.setStyleSheet("color: #38bdf8; background-color: #0c4a6e; padding: 4px;")
        self.repaint()

        # Temporarily use entered URL
        old_url = self.settings.url
        self.settings.url = url
        success, msg = self.notifier.send_ping()
        self.settings.url = old_url

        if success:
            self.lbl_status.setText(f"✓ Success: {msg} — Notification received!")
            self.lbl_status.setStyleSheet("color: #34d399; background-color: #064e3b; padding: 4px;")
        else:
            self.lbl_status.setText(f"✕ Dispatch Failed: {msg}")
            self.lbl_status.setStyleSheet("color: #f87171; background-color: #450a0a; padding: 4px;")

    def _on_save(self) -> None:
        self.settings.enabled = self.chk_enable.isChecked()
        self.settings.url = self.edit_url.text().strip()
        self.settings.operator_tag = self.edit_operator.text().strip()
        self.settings.notify_test_started = self.chk_start.isChecked()
        self.settings.notify_step_completed = self.chk_step.isChecked()
        self.settings.notify_cycle_completed = self.chk_cycle.isChecked()
        self.settings.notify_test_paused_resumed = self.chk_pause.isChecked()
        self.settings.notify_emergency_stop = self.chk_estop.isChecked()
        self.settings.notify_safety_trip = self.chk_trip.isChecked()
        self.settings.notify_test_completed = self.chk_done.isChecked()
        self.settings.save()
        self.accept()
