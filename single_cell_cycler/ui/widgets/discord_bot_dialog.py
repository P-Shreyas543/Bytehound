"""Discord Bot Settings Dialog (IMP-14).

Provides a configuration UI for the Discord Bot remote command & control system.
Allows the operator to enter the bot token, enable/disable commands, and
check bot connectivity status in real-time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ...comm.discord_bot import DiscordBotRunner, DiscordBotSettings

logger = logging.getLogger("SingleCellCycler.DiscordBotDialog")

_DIALOG_STYLE = """
QDialog {
    background-color: #0f172a;
    color: #e2e8f0;
    font-family: 'Segoe UI', Inter, sans-serif;
}
QLabel {
    color: #cbd5e1;
    font-size: 12px;
}
QLineEdit {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
    font-family: 'Consolas', 'Courier New', monospace;
}
QLineEdit:focus {
    border-color: #5865F2;
}
QCheckBox {
    color: #cbd5e1;
    font-size: 12px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #475569;
    background: #1e293b;
}
QCheckBox::indicator:checked {
    background-color: #5865F2;
    border-color: #5865F2;
}
QGroupBox {
    color: #94a3b8;
    border: 1px solid #1e293b;
    border-radius: 8px;
    margin-top: 10px;
    padding: 10px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #5865F2;
}
QPushButton {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #334155;
    color: #e2e8f0;
}
"""


class DiscordBotDialog(QDialog):
    """Configuration and status dialog for the Discord Bot (IMP-14)."""

    def __init__(self, bot_runner: "DiscordBotRunner", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bot_runner = bot_runner
        self.settings = bot_runner.settings

        self.setWindowTitle("🤖 Discord Bot — Remote Command & Control (IMP-14)")
        self.setMinimumWidth(560)
        self.setMinimumHeight(640)
        self.setStyleSheet(_DIALOG_STYLE)

        self._build_ui()
        self._load_settings()

        # Poll bot status every 2s while dialog is open
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(2000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Header
        hdr = QLabel("🤖  Discord Bot — Remote Command & Control")
        hdr.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #5865F2; "
            "border-bottom: 1px solid #1e293b; padding-bottom: 8px;"
        )
        layout.addWidget(hdr)

        sub = QLabel(
            "Run slash commands from any Discord channel to query live telemetry,\n"
            "pause/resume/stop tests, and trigger exports — even when away from the lab."
        )
        sub.setStyleSheet("color: #64748b; font-size: 11px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # --- Status Badge ---
        self.lbl_status = QLabel("● Status: Checking...")
        self.lbl_status.setStyleSheet(
            "background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; "
            "padding: 6px 10px; color: #94a3b8; font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self.lbl_status)

        # --- Core Settings ---
        core_group = QGroupBox("Bot Configuration")
        core_form = QFormLayout(core_group)
        core_form.setSpacing(10)

        self.chk_enable = QCheckBox("Enable Discord Bot")
        self.chk_enable.setStyleSheet("font-weight: 700; color: #e2e8f0;")
        core_form.addRow("", self.chk_enable)

        self.edit_token = QLineEdit()
        self.edit_token.setPlaceholderText("Paste your Discord Bot Token here…")
        self.edit_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_show_token = QPushButton("👁 Show")
        self.btn_show_token.setFixedWidth(70)
        self.btn_show_token.clicked.connect(self._toggle_token_visibility)
        token_row = QHBoxLayout()
        token_row.addWidget(self.edit_token)
        token_row.addWidget(self.btn_show_token)
        core_form.addRow("Bot Token:", token_row)

        self.edit_operator = QLineEdit()
        self.edit_operator.setPlaceholderText("e.g. Shreyas P")
        core_form.addRow("Operator Name:", self.edit_operator)

        layout.addWidget(core_group)

        # --- Command Permissions ---
        perm_group = QGroupBox("Allowed Commands")
        perm_layout = QVBoxLayout(perm_group)

        self.chk_status    = QCheckBox("/status   — Query live voltage, current, temperature, SoC")
        self.chk_pause     = QCheckBox("/pause    — Pause the active test step")
        self.chk_resume    = QCheckBox("/resume   — Resume a paused test")
        self.chk_stop      = QCheckBox("/stop     — Emergency stop (safe de-energization)")
        self.chk_export    = QCheckBox("/export   — Generate & export diagnostic run package")
        self.chk_report    = QCheckBox("/report   — Generate HTML certification report")
        self.chk_preflight = QCheckBox("/preflight — Run hardware sanity pre-flight checks")

        self.chk_stop.setStyleSheet("color: #fca5a5;")  # Red tint for danger command

        for chk in [self.chk_status, self.chk_pause, self.chk_resume,
                    self.chk_stop, self.chk_export, self.chk_report, self.chk_preflight]:
            perm_layout.addWidget(chk)

        layout.addWidget(perm_group)

        # --- Setup Guide ---
        guide_group = QGroupBox("📖  Quick Setup Guide")
        guide_layout = QVBoxLayout(guide_group)

        guide_text = QLabel(
            "<b>Step 1:</b> Go to <a href='https://discord.com/developers/applications' style='color:#5865F2;'>discord.com/developers/applications</a><br>"
            "<b>Step 2:</b> Click <b>New Application</b> → name it <i>Bytehound Cycler</i><br>"
            "<b>Step 3:</b> Go to <b>Bot</b> → click <b>Add Bot</b> → <b>Reset Token</b> → copy token<br>"
            "<b>Step 4:</b> Under <b>OAuth2 → URL Generator</b>, tick <b>bot</b> + <b>applications.commands</b><br>"
            "<b>Step 5:</b> Set permissions: <b>Send Messages</b>, <b>Use Slash Commands</b><br>"
            "<b>Step 6:</b> Copy the generated URL → open in browser → invite bot to your server<br>"
            "<b>Step 7:</b> Paste your token above, enable the bot, click <b>Save & Start</b>"
        )
        guide_text.setOpenExternalLinks(True)
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.6;")
        guide_layout.addWidget(guide_text)
        layout.addWidget(guide_group)

        # --- Buttons ---
        btn_row = QHBoxLayout()

        self.btn_start_stop = QPushButton("🚀 Save & Start Bot")
        self.btn_start_stop.setStyleSheet(
            "background-color: #5865F2; color: #ffffff; font-weight: 700; "
            "border: none; border-radius: 6px; padding: 8px 16px; font-size: 12px;"
        )
        self.btn_start_stop.clicked.connect(self._on_save_and_start)

        self.btn_stop_bot = QPushButton("⏹ Stop Bot")
        self.btn_stop_bot.setStyleSheet(
            "background-color: #1e293b; color: #f87171; border: 1px solid #ef4444; "
            "border-radius: 6px; padding: 8px 14px; font-size: 12px;"
        )
        self.btn_stop_bot.clicked.connect(self._on_stop_bot)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)

        btn_row.addWidget(self.btn_start_stop)
        btn_row.addWidget(self.btn_stop_bot)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        s = self.settings
        self.chk_enable.setChecked(s.enabled)
        self.edit_token.setText(s.token)
        self.edit_operator.setText(s.operator_tag)
        self.chk_status.setChecked(s.allow_status)
        self.chk_pause.setChecked(s.allow_pause)
        self.chk_resume.setChecked(s.allow_resume)
        self.chk_stop.setChecked(s.allow_stop)
        self.chk_export.setChecked(s.allow_export)
        self.chk_report.setChecked(s.allow_report)
        self.chk_preflight.setChecked(s.allow_preflight)
        self._refresh_status()

    def _save_settings(self) -> None:
        s = self.settings
        s.enabled = self.chk_enable.isChecked()
        s.token = self.edit_token.text().strip()
        s.operator_tag = self.edit_operator.text().strip() or "Shreyas P"
        s.allow_status = self.chk_status.isChecked()
        s.allow_pause = self.chk_pause.isChecked()
        s.allow_resume = self.chk_resume.isChecked()
        s.allow_stop = self.chk_stop.isChecked()
        s.allow_export = self.chk_export.isChecked()
        s.allow_report = self.chk_report.isChecked()
        s.allow_preflight = self.chk_preflight.isChecked()
        s.save()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_save_and_start(self) -> None:
        self._save_settings()
        self.bot_runner.stop()
        started = self.bot_runner.start()
        if started:
            self.lbl_status.setText("● Status: Connecting to Discord...")
            self.lbl_status.setStyleSheet(
                "background-color: #1c3a5e; border: 1px solid #38bdf8; border-radius: 6px; "
                "padding: 6px 10px; color: #38bdf8; font-size: 12px; font-weight: 600;"
            )
        else:
            self.lbl_status.setText(f"● Status: {self.bot_runner.status_message}")
            self.lbl_status.setStyleSheet(
                "background-color: #450a0a; border: 1px solid #ef4444; border-radius: 6px; "
                "padding: 6px 10px; color: #f87171; font-size: 12px; font-weight: 600;"
            )

    def _on_stop_bot(self) -> None:
        self.bot_runner.stop()
        self._refresh_status()

    def _toggle_token_visibility(self) -> None:
        if self.edit_token.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_token.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_show_token.setText("🙈 Hide")
        else:
            self.edit_token.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_show_token.setText("👁 Show")

    def _refresh_status(self) -> None:
        msg = self.bot_runner.status_message
        is_online = "online" in msg.lower() or "logged in" in msg.lower()
        is_starting = "starting" in msg.lower() or "connecting" in msg.lower()
        is_error = "error" in msg.lower() or "failed" in msg.lower() or "offline" in msg.lower()

        if is_online:
            self.lbl_status.setText(f"● Status: {msg}")
            self.lbl_status.setStyleSheet(
                "background-color: #052e16; border: 1px solid #22c55e; border-radius: 6px; "
                "padding: 6px 10px; color: #4ade80; font-size: 12px; font-weight: 600;"
            )
        elif is_starting:
            self.lbl_status.setText(f"● Status: {msg}")
            self.lbl_status.setStyleSheet(
                "background-color: #1c3a5e; border: 1px solid #38bdf8; border-radius: 6px; "
                "padding: 6px 10px; color: #38bdf8; font-size: 12px; font-weight: 600;"
            )
        elif is_error:
            self.lbl_status.setText(f"● Status: {msg}")
            self.lbl_status.setStyleSheet(
                "background-color: #450a0a; border: 1px solid #ef4444; border-radius: 6px; "
                "padding: 6px 10px; color: #f87171; font-size: 12px; font-weight: 600;"
            )
        else:
            self.lbl_status.setText(f"● Status: {msg}")
            self.lbl_status.setStyleSheet(
                "background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; "
                "padding: 6px 10px; color: #94a3b8; font-size: 12px; font-weight: 600;"
            )

    def closeEvent(self, event):
        self._status_timer.stop()
        super().closeEvent(event)
