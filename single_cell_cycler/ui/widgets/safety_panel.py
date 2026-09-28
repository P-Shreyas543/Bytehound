"""BMS Safety and Fault Status LED panel widget."""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...comm.packet_codec import FaultSoCTelemetry
from ..theme import BG_CARD, BORDER_COLOR, COLOR_DANGER, COLOR_REST, TEXT_MUTED, TEXT_PRIMARY


class LEDIndicator(QFrame):
    """Circular LED-style status indicator with label."""

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.dot = QFrame()
        self.dot.setFixedSize(14, 14)
        layout.addWidget(self.dot)

        self.lbl_text = QLabel(label)
        self.lbl_text.setStyleSheet(f"font-size: 12px; color: {TEXT_PRIMARY}; font-weight: 500;")
        layout.addWidget(self.lbl_text)
        layout.addStretch()

        self.set_active(False)

    def set_active(self, is_active: bool) -> None:
        if is_active:
            # Bright flashing red
            self.dot.setStyleSheet(f"""
                background-color: {COLOR_DANGER};
                border-radius: 7px;
                border: 2px solid #fca5a5;
            """)
            self.lbl_text.setStyleSheet(f"font-size: 12px; color: {COLOR_DANGER}; font-weight: 700;")
        else:
            # Dim / OK green or gray
            self.dot.setStyleSheet(f"""
                background-color: #22c55e;
                border-radius: 7px;
                border: 1px solid #15803d;
            """)
            self.lbl_text.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; font-weight: 500;")


class SafetyPanelWidget(QWidget):
    """Panel displaying 6 hardware fault LEDs, comm heartbeat, and trip banner."""

    def __init__(self, reset_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self._reset_callback = reset_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 1. Fault Status Grid
        box_faults = QGroupBox("Hardware BMS Protection (Frame 0x3000)")
        g_layout = QGridLayout(box_faults)
        g_layout.setSpacing(6)

        self.led_cov = LEDIndicator("COV - Cell Over Voltage")
        self.led_cuv = LEDIndicator("CUV - Cell Under Voltage")
        self.led_occ = LEDIndicator("OCC - Over Current Charge")
        self.led_ocd = LEDIndicator("OCD - Over Current Discharge")
        self.led_cot = LEDIndicator("COT - Cell Over Temp")
        self.led_cut = LEDIndicator("CUT - Cell Under Temp")

        g_layout.addWidget(self.led_cov, 0, 0)
        g_layout.addWidget(self.led_cuv, 0, 1)
        g_layout.addWidget(self.led_occ, 1, 0)
        g_layout.addWidget(self.led_ocd, 1, 1)
        g_layout.addWidget(self.led_cot, 2, 0)
        g_layout.addWidget(self.led_cut, 2, 1)

        layout.addWidget(box_faults)

        # 2. Watchdog & Trip Banner
        self.trip_frame = QFrame()
        self.trip_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        tf_layout = QHBoxLayout(self.trip_frame)
        self.lbl_trip_status = QLabel("SAFETY STATUS: ALL SYSTEMS NOMINAL")
        self.lbl_trip_status.setStyleSheet("color: #22c55e; font-weight: 700; font-size: 13px;")
        tf_layout.addWidget(self.lbl_trip_status)
        tf_layout.addStretch()

        self.btn_reset = QPushButton("Reset Safety Interlock")
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        self.btn_reset.setEnabled(False)
        tf_layout.addWidget(self.btn_reset)
        layout.addWidget(self.trip_frame)

        layout.addStretch()

    def update_faults(self, fault_soc: FaultSoCTelemetry) -> None:
        self.led_cov.set_active(fault_soc.cov)
        self.led_cuv.set_active(fault_soc.cuv)
        self.led_occ.set_active(fault_soc.occ)
        self.led_ocd.set_active(fault_soc.ocd)
        self.led_cot.set_active(fault_soc.cot)
        self.led_cut.set_active(fault_soc.cut)

    def set_tripped(self, reason: str) -> None:
        self.lbl_trip_status.setText(f"SAFETY INTERLOCK TRIPPED: {reason}")
        self.lbl_trip_status.setStyleSheet(f"color: {COLOR_DANGER}; font-weight: 800; font-size: 13px;")
        self.trip_frame.setStyleSheet(f"background-color: #450a0a; border: 2px solid {COLOR_DANGER}; border-radius: 8px; padding: 10px;")
        self.btn_reset.setEnabled(True)

    def _on_reset_clicked(self) -> None:
        self._reset_callback()
        self.lbl_trip_status.setText("SAFETY STATUS: ALL SYSTEMS NOMINAL")
        self.lbl_trip_status.setStyleSheet("color: #22c55e; font-weight: 700; font-size: 13px;")
        self.trip_frame.setStyleSheet(f"background-color: {BG_CARD}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 10px;")
        self.btn_reset.setEnabled(False)
