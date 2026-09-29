"""Pre-Flight Hardware Sanity Handshake Diagnostic Dialog (IMP-10)."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.preflight_checker import CheckStatus, PreflightReport

logger = logging.getLogger("SingleCellCycler.PreflightDialog")


class PreflightDialog(QDialog):
    """High-contrast diagnostic modal displaying hardware sanity check results."""

    def __init__(
        self,
        report: PreflightReport,
        rerun_callback: Optional[Callable[[], PreflightReport]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.report = report
        self.rerun_callback = rerun_callback
        self.proceed_confirmed = False

        self.setWindowTitle("Pre-Flight Hardware Sanity Handshake")
        self.resize(760, 480)
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
            QTableWidget {
                background-color: #1e293b;
                border: 1px solid #334155;
                gridline-color: #334155;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #94a3b8;
                font-weight: 700;
                padding: 6px;
                border: 1px solid #334155;
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
        self._populate_report(self.report)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header with Title and Pill Badge
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        lbl_title = QLabel("Hardware Sanity Handshake")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #38bdf8;")
        title_box.addWidget(lbl_title)

        self.lbl_subtitle = QLabel(f"Pre-flight verification for Cell {self.report.cell_id}")
        self.lbl_subtitle.setStyleSheet("font-size: 11px; color: #94a3b8;")
        title_box.addWidget(self.lbl_subtitle)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        self.lbl_badge = QLabel(self.report.summary_text)
        self.lbl_badge.setStyleSheet(self.report.summary_badge_style)
        header_layout.addWidget(self.lbl_badge)
        layout.addLayout(header_layout)

        # Results Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Status",
            "Subsystem / Check",
            "Measured",
            "Requirement",
            "Diagnostic Guidance",
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 85)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 185)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 120)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 130)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Diagnostic Summary Banner
        self.banner = QFrame()
        self.banner.setFrameShape(QFrame.Shape.StyledPanel)
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        self.lbl_banner = QLabel()
        self.lbl_banner.setWordWrap(True)
        self.lbl_banner.setStyleSheet("font-size: 11px; line-height: 1.4;")
        banner_layout.addWidget(self.lbl_banner)
        layout.addWidget(self.banner)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_rerun = QPushButton("↻ Re-Run Sanity Check")
        self.btn_rerun.setToolTip("Sample fresh telemetry and re-run all 4 diagnostic checks")
        self.btn_rerun.clicked.connect(self._on_rerun)
        btn_layout.addWidget(self.btn_rerun)

        btn_layout.addStretch()

        self.btn_proceed = QPushButton("Proceed With Test")
        self.btn_proceed.setStyleSheet("""
            QPushButton {
                background-color: #065f46;
                border: 1px solid #10b981;
                color: #ecfdf5;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_proceed.clicked.connect(self._on_proceed)
        btn_layout.addWidget(self.btn_proceed)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _populate_report(self, report: PreflightReport) -> None:
        self.report = report
        self.lbl_subtitle.setText(f"Pre-flight verification for Cell {report.cell_id}")
        self.lbl_badge.setText(report.summary_text)
        self.lbl_badge.setStyleSheet(report.summary_badge_style)

        self.table.setRowCount(len(report.checks))
        for row, check in enumerate(report.checks):
            # Status icon & text
            if check.status == CheckStatus.PASS:
                status_item = QTableWidgetItem("● PASS")
                status_item.setForeground(QColor("#34d399"))
            elif check.status == CheckStatus.WARN:
                status_item = QTableWidgetItem("▲ WARN")
                status_item.setForeground(QColor("#fbbf24"))
            else:
                status_item = QTableWidgetItem("✕ FAIL")
                status_item.setForeground(QColor("#f87171"))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = status_item.font()
            font.setBold(True)
            status_item.setFont(font)
            self.table.setItem(row, 0, status_item)

            name_item = QTableWidgetItem(check.name)
            name_item.setFont(font)
            self.table.setItem(row, 1, name_item)

            meas_item = QTableWidgetItem(check.measured)
            meas_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, meas_item)

            exp_item = QTableWidgetItem(check.expected)
            exp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            exp_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 3, exp_item)

            msg_item = QTableWidgetItem(check.message)
            self.table.setItem(row, 4, msg_item)

        # Update diagnostic summary banner
        if report.passed and not report.has_warnings:
            self.banner.setStyleSheet("""
                QFrame {
                    background-color: #064e3b;
                    border: 1px solid #10b981;
                    border-radius: 6px;
                }
            """)
            self.lbl_banner.setText(
                "✓ ALL SANITY CHECKS PASSED: Hardware communication is synchronized, sense leads are active, "
                "thermal probes are calibrated, and zero quiescent leakage confirmed. Safe to commence test cycling."
            )
            self.lbl_banner.setStyleSheet("color: #a7f3d0; font-weight: 600;")
            self.btn_proceed.setText("Start Test Now")
            self.btn_proceed.setEnabled(True)
        elif report.passed and report.has_warnings:
            self.banner.setStyleSheet("""
                QFrame {
                    background-color: #78350f;
                    border: 1px solid #f59e0b;
                    border-radius: 6px;
                }
            """)
            self.lbl_banner.setText(
                "⚠ ADVISORY WARNINGS DETECTED: Hardware is operational, but one or more parameters are near envelope limits. "
                "Review the diagnostic remarks above before proceeding."
            )
            self.lbl_banner.setStyleSheet("color: #fde68a; font-weight: 600;")
            self.btn_proceed.setText("Proceed Anyway")
            self.btn_proceed.setEnabled(True)
        else:
            self.banner.setStyleSheet("""
                QFrame {
                    background-color: #7f1d1d;
                    border: 1px solid #ef4444;
                    border-radius: 6px;
                }
            """)
            self.lbl_banner.setText(
                "✕ CRITICAL HARDWARE FAULTS DETECTED: Automated test start is blocked. "
                "Operating the cycler with detached sense leads or thermal faults may cause battery damage or safety trips. "
                "Correct the highlighted issues and click 'Re-Run Sanity Check'."
            )
            self.lbl_banner.setStyleSheet("color: #fecaca; font-weight: 600;")
            self.btn_proceed.setText("Override & Start (Not Recommended)")
            self.btn_proceed.setEnabled(False)  # Disabled by default on critical failures

    def _on_rerun(self) -> None:
        if self.rerun_callback:
            new_report = self.rerun_callback()
            self._populate_report(new_report)

    def _on_proceed(self) -> None:
        self.proceed_confirmed = True
        self.accept()
