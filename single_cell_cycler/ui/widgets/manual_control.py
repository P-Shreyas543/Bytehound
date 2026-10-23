"""Manual hardware control and switch override panel widget with live readback telemetry."""

from __future__ import annotations

from typing import Callable, Dict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ...comm.packet_codec import CommandEchoTelemetry
from ...comm.protocol_defs import (
    DISCHARGE_TABLE,
    ChargeControlBits,
    ChargeSelectBits,
    DischargeControlBits,
    DischargeSelectBits,
    FRAME_CHARGE_CTRL,
    FRAME_CHARGE_SEL,
    FRAME_DISCHARGE_CTRL,
    FRAME_DISCHARGE_SEL,
    FRAME_RELAY_CTRL,
    RelayControlBits,
    discharge_decimal_to_current,
)


class ManualControlWidget(QWidget):
    """Direct interactive overrides and live readback monitoring for 0x6000 - 0x6004 registers."""

    def __init__(self, command_sender: Callable[[int, int, int], None], parent: QWidget | None = None):
        super().__init__(parent)
        self._command_sender = command_sender
        self._syncing_loads = False

        # Cache of latest hardware read-back bytes
        self.control_readbacks: Dict[int, int] = {
            FRAME_RELAY_CTRL: 0x00,
            FRAME_CHARGE_SEL: 0x00,
            FRAME_CHARGE_CTRL: 0x00,
            FRAME_DISCHARGE_CTRL: 0x00,
            FRAME_DISCHARGE_SEL: 0x00,
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ----------------------------------------------------------------------
        # Top Card: Live Hardware Control Registers Overview
        # ----------------------------------------------------------------------
        top_frame = QFrame()
        top_frame.setStyleSheet("""
            QFrame {
                background-color: #1a2035;
                border: 1px solid #2d3748;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        top_layout = QVBoxLayout(top_frame)
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_layout.setSpacing(6)

        hdr_row = QHBoxLayout()
        lbl_hdr = QLabel("LIVE HARDWARE CONTROL REGISTERS READBACK (0x6000 - 0x6004)")
        lbl_hdr.setStyleSheet("color: #64ffda; font-weight: 800; font-size: 12px; letter-spacing: 0.5px;")
        hdr_row.addWidget(lbl_hdr)
        hdr_row.addStretch()

        self.lbl_connection_state = QLabel("Manual commands unavailable: connect to hardware")
        self.lbl_connection_state.setStyleSheet("color:#fbbf24; font-weight:700; font-size:11px;")
        hdr_row.addWidget(self.lbl_connection_state)

        btn_clear_unwanted = QPushButton("🧹 All Controls to Zero (Safe Idle)")
        btn_clear_unwanted.setToolTip("Sets all 5 control registers (0x6000 - 0x6004) to zero, clears loads, and disconnects cell relay")
        btn_clear_unwanted.setStyleSheet("background-color: #3b82f6; color: white; font-weight: bold; padding: 4px 10px;")
        btn_clear_unwanted.clicked.connect(self._clear_unwanted_flags)
        hdr_row.addWidget(btn_clear_unwanted)
        top_layout.addLayout(hdr_row)

        # 5 register indicator badges
        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(8)

        self.badge_relay = QLabel("0x6000 Relay: --")
        self.badge_chg_sel = QLabel("0x6001 Chg Sel: --")
        self.badge_chg_ctrl = QLabel("0x6002 Chg Ctrl: --")
        self.badge_dis_ctrl = QLabel("0x6003 Dis Ctrl: --")
        self.badge_dis_sel = QLabel("0x6004 Loads: --")

        badge_style = """
            QLabel {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                color: #e2e8f0;
            }
        """
        for badge in (self.badge_relay, self.badge_chg_sel, self.badge_chg_ctrl, self.badge_dis_ctrl, self.badge_dis_sel):
            badge.setStyleSheet(badge_style)
            badges_layout.addWidget(badge)

        top_layout.addLayout(badges_layout)
        layout.addWidget(top_frame)

        # ----------------------------------------------------------------------
        # Control Grid (0x6000 - 0x6004)
        # ----------------------------------------------------------------------
        grid = QGridLayout()
        grid.setSpacing(12)

        # 1. 0x6000 Cell Relay Control
        box_relay = QGroupBox("Cell Relay Control (0x6000)")
        l_relay = QVBoxLayout(box_relay)
        self.chk_relay_en = QCheckBox("Cell Enable (Bit 0: Connect Cell)")
        self.chk_relay_en.setToolTip("0 = Disconnected from test circuit, 1 = Connected to relay")

        row_cell = QHBoxLayout()
        row_cell.addWidget(QLabel("Cell Select:"))
        self.combo_cell_sel = QComboBox()
        self.combo_cell_sel.addItem("Cell 1 (Bit 1 = 0)", 0)
        self.combo_cell_sel.addItem("Cell 2 (Bit 1 = 1)", 1)
        row_cell.addWidget(self.combo_cell_sel)
        l_relay.addWidget(self.chk_relay_en)
        l_relay.addLayout(row_cell)

        self.lbl_relay_summary = QLabel("Wire: 0x00 (Cell Disconnected)")
        self.lbl_relay_summary.setStyleSheet("color: #8892b0; font-size: 11px;")
        l_relay.addWidget(self.lbl_relay_summary)

        self.lbl_relay_rb = QLabel("Readback: [Not received]")
        self.lbl_relay_rb.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
        l_relay.addWidget(self.lbl_relay_rb)

        btn_send_relay = QPushButton("Send Relay (0x6000)")
        btn_send_relay.clicked.connect(self._send_relay)
        l_relay.addWidget(btn_send_relay)
        grid.addWidget(box_relay, 0, 0)

        self.chk_relay_en.stateChanged.connect(self._update_relay_summary)
        self.combo_cell_sel.currentIndexChanged.connect(self._update_relay_summary)

        # 2. 0x6001 Cell Charge Select
        box_chg_sel = QGroupBox("Charge Select (0x6001)")
        l_chg_sel = QVBoxLayout(box_chg_sel)

        row_v = QHBoxLayout()
        row_v.addWidget(QLabel("Max Voltage:"))
        self.combo_chg_voltage = QComboBox()
        self.combo_chg_voltage.addItem("4.2 V (Bit 0 = 1, NMC/LCO)", 1)
        self.combo_chg_voltage.addItem("3.6 V (Bit 0 = 0, LFP)", 0)
        row_v.addWidget(self.combo_chg_voltage)
        l_chg_sel.addLayout(row_v)

        self.chk_curr_1 = QCheckBox("Current 1: +0.5 A (Bit 1)")
        self.chk_curr_2 = QCheckBox("Current 2: +1.0 A (Bit 2)")
        l_chg_sel.addWidget(self.chk_curr_1)
        l_chg_sel.addWidget(self.chk_curr_2)

        self.lbl_chg_sel_summary = QLabel("Target: 4.2V @ 0.0 A (Wire: 0x01)")
        self.lbl_chg_sel_summary.setStyleSheet("color: #00d2ff; font-weight: bold; font-size: 11px;")
        l_chg_sel.addWidget(self.lbl_chg_sel_summary)

        self.lbl_chg_sel_rb = QLabel("Readback: [Not received]")
        self.lbl_chg_sel_rb.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
        l_chg_sel.addWidget(self.lbl_chg_sel_rb)

        btn_send_chg_sel = QPushButton("Send Charge Sel (0x6001)")
        btn_send_chg_sel.clicked.connect(self._send_chg_sel)
        l_chg_sel.addWidget(btn_send_chg_sel)
        grid.addWidget(box_chg_sel, 0, 1)

        self.combo_chg_voltage.currentIndexChanged.connect(self._update_chg_sel_summary)
        self.chk_curr_1.stateChanged.connect(self._update_chg_sel_summary)
        self.chk_curr_2.stateChanged.connect(self._update_chg_sel_summary)

        # 3. 0x6002 Cell Charge Control
        box_chg_ctrl = QGroupBox("Charge Control (0x6002)")
        l_chg_ctrl = QVBoxLayout(box_chg_ctrl)
        self.chk_chg_en = QCheckBox("Charge Enable (Bit 0)")
        btn_reset_chg_comp = QPushButton("Pulse Comparator Reset (Bit 1)")
        btn_reset_chg_comp.clicked.connect(self._pulse_chg_comp)
        btn_send_chg_ctrl = QPushButton("Send Charge Ctrl (0x6002)")
        btn_send_chg_ctrl.clicked.connect(self._send_chg_ctrl)
        l_chg_ctrl.addWidget(self.chk_chg_en)
        l_chg_ctrl.addWidget(btn_reset_chg_comp)

        self.lbl_chg_ctrl_rb = QLabel("Readback: [Not received]")
        self.lbl_chg_ctrl_rb.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
        l_chg_ctrl.addWidget(self.lbl_chg_ctrl_rb)

        l_chg_ctrl.addWidget(btn_send_chg_ctrl)
        grid.addWidget(box_chg_ctrl, 0, 2)

        # 4. 0x6003 Cell Discharge Control
        box_dis_ctrl = QGroupBox("Discharge Control (0x6003)")
        l_dis_ctrl = QVBoxLayout(box_dis_ctrl)
        self.chk_dis_en = QCheckBox("Discharge Enable (Bit 0)")
        btn_reset_dis_comp = QPushButton("Pulse Comparator Reset (Bit 1)")
        btn_reset_dis_comp.clicked.connect(self._pulse_dis_comp)
        btn_send_dis_ctrl = QPushButton("Send Discharge Ctrl (0x6003)")
        btn_send_dis_ctrl.clicked.connect(self._send_dis_ctrl)
        l_dis_ctrl.addWidget(self.chk_dis_en)
        l_dis_ctrl.addWidget(btn_reset_dis_comp)

        self.lbl_dis_ctrl_rb = QLabel("Readback: [Not received]")
        self.lbl_dis_ctrl_rb.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
        l_dis_ctrl.addWidget(self.lbl_dis_ctrl_rb)

        l_dis_ctrl.addWidget(btn_send_dis_ctrl)
        grid.addWidget(box_dis_ctrl, 1, 0)

        # 5. 0x6004 Cell Discharge Select (16 Discrete Binary States)
        box_dis_sel = QGroupBox("Discharge Load Bank Select (0x6004)")
        l_dis_sel = QVBoxLayout(box_dis_sel)

        row_preset = QHBoxLayout()
        row_preset.addWidget(QLabel("Target Load State:"))
        self.combo_dis_preset = QComboBox()
        for dec in range(16):
            l1, l2, l3, l4, num_on, current_a = DISCHARGE_TABLE[dec]
            switches = []
            if l1: switches.append("L1")
            if l2: switches.append("L2")
            if l3: switches.append("L3")
            if l4: switches.append("L4")
            sw_str = "+".join(switches) if switches else "All OFF"
            text = f"Dec {dec:2d}: {sw_str:11s} -> {current_a:.1f} A"
            self.combo_dis_preset.addItem(text, dec)
        row_preset.addWidget(self.combo_dis_preset)
        l_dis_sel.addLayout(row_preset)

        loads_row = QHBoxLayout()
        self.chk_load_1 = QCheckBox("L1 (0.2 A)")
        self.chk_load_2 = QCheckBox("L2 (0.4 A)")
        self.chk_load_3 = QCheckBox("L3 (0.8 A)")
        self.chk_load_4 = QCheckBox("L4 (1.6 A)")
        loads_row.addWidget(self.chk_load_1)
        loads_row.addWidget(self.chk_load_2)
        loads_row.addWidget(self.chk_load_3)
        loads_row.addWidget(self.chk_load_4)
        l_dis_sel.addLayout(loads_row)

        self.lbl_dis_sel_summary = QLabel("Total Current: 0.0 A | Active: 0 | Value: 0x00")
        self.lbl_dis_sel_summary.setStyleSheet("color: #ff9800; font-weight: bold; font-size: 11px;")
        l_dis_sel.addWidget(self.lbl_dis_sel_summary)

        self.lbl_dis_sel_rb = QLabel("Readback: [Not received]")
        self.lbl_dis_sel_rb.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: bold;")
        l_dis_sel.addWidget(self.lbl_dis_sel_rb)

        btn_send_dis_sel = QPushButton("Send Load Select (0x6004)")
        btn_send_dis_sel.clicked.connect(self._send_dis_sel)
        l_dis_sel.addWidget(btn_send_dis_sel)
        grid.addWidget(box_dis_sel, 1, 1, 1, 2)

        self.combo_dis_preset.currentIndexChanged.connect(self._on_dis_preset_changed)
        self.chk_load_1.stateChanged.connect(self._on_dis_checkbox_changed)
        self.chk_load_2.stateChanged.connect(self._on_dis_checkbox_changed)
        self.chk_load_3.stateChanged.connect(self._on_dis_checkbox_changed)
        self.chk_load_4.stateChanged.connect(self._on_dis_checkbox_changed)

        layout.addLayout(grid)
        layout.addStretch()

        # Initial summaries
        self._update_relay_summary()
        self._update_chg_sel_summary()
        self.set_connection_available(False)

    def set_connection_available(self, connected: bool) -> None:
        """Gate manual commands while preserving readback/status labels."""
        connected = bool(connected)
        self.lbl_connection_state.setText(
            "Manual commands available" if connected else "Manual commands unavailable: connect to hardware"
        )
        self.lbl_connection_state.setStyleSheet(
            f"color: {'#86efac' if connected else '#fbbf24'}; font-weight:700; font-size:11px;"
        )
        for widget in [
            *self.findChildren(QPushButton),
            *self.findChildren(QCheckBox),
            *self.findChildren(QComboBox),
        ]:
            if widget is self.lbl_connection_state:
                continue
            widget.setEnabled(connected)

    # --------------------------------------------------------------------------
    # Live Readback Handler (CommandEchoTelemetry)
    # --------------------------------------------------------------------------
    def on_command_echo(self, echo: CommandEchoTelemetry) -> None:
        """Handle incoming 0x6000 - 0x6004 readback from hardware."""
        self.control_readbacks[echo.frame_id] = echo.payload_byte
        val = echo.payload_byte

        if echo.frame_id == FRAME_RELAY_CTRL:
            cell_str = "Cell 2" if (val & RelayControlBits.CELL_SELECT) else "Cell 1"
            en_str = "CONNECTED" if (val & RelayControlBits.CELL_ENABLE) else "DISCONNECTED"
            color = "#10b981" if (val & RelayControlBits.CELL_ENABLE) else "#94a3b8"
            self.lbl_relay_rb.setText(f"Readback: 0x{val:02X} [{cell_str}, {en_str}]")
            self.lbl_relay_rb.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            self.badge_relay.setText(f"0x6000 Relay: 0x{val:02X} ({cell_str} {en_str})")
            self.badge_relay.setStyleSheet(f"background-color: #0f172a; border: 1px solid {color}; border-radius: 6px; padding: 6px 10px; font-family: 'Consolas', monospace; font-size: 11px; color: {color};")

        elif echo.frame_id == FRAME_CHARGE_SEL:
            v_val = 4.2 if (val & ChargeSelectBits.MAX_CHARGE_VOLTAGE) else 3.6
            c_val = 0.0
            if val & ChargeSelectBits.MAX_CHARGE_CURRENT_1: c_val += 0.5
            if val & ChargeSelectBits.MAX_CHARGE_CURRENT_2: c_val += 1.0
            self.lbl_chg_sel_rb.setText(f"Readback: 0x{val:02X} [{v_val:.1f}V, {c_val:.1f}A]")
            self.lbl_chg_sel_rb.setStyleSheet("color: #00d2ff; font-size: 11px; font-weight: bold;")
            self.badge_chg_sel.setText(f"0x6001 Chg Sel: 0x{val:02X} ({v_val:.1f}V, {c_val:.1f}A)")

        elif echo.frame_id == FRAME_CHARGE_CTRL:
            en = bool(val & ChargeControlBits.CHARGE_ENABLE)
            rst = bool(val & ChargeControlBits.CHARGE_COMPARATOR_RESET)
            en_txt = "ON" if en else "OFF"
            color = "#10b981" if en else "#94a3b8"
            self.lbl_chg_ctrl_rb.setText(f"Readback: 0x{val:02X} [EN={en_txt}, Reset={int(rst)}]")
            self.lbl_chg_ctrl_rb.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            self.badge_chg_ctrl.setText(f"0x6002 Chg: 0x{val:02X} (EN={en_txt}, Rst={int(rst)})")
            self.badge_chg_ctrl.setStyleSheet(f"background-color: #0f172a; border: 1px solid {color}; border-radius: 6px; padding: 6px 10px; font-family: 'Consolas', monospace; font-size: 11px; color: {color};")

        elif echo.frame_id == FRAME_DISCHARGE_CTRL:
            en = bool(val & DischargeControlBits.DISCHARGE_ENABLE)
            rst = bool(val & DischargeControlBits.DISCHARGE_COMPARATOR_RESET)
            en_txt = "ON" if en else "OFF"
            color = "#f97316" if en else "#94a3b8"
            self.lbl_dis_ctrl_rb.setText(f"Readback: 0x{val:02X} [EN={en_txt}, Reset={int(rst)}]")
            self.lbl_dis_ctrl_rb.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            self.badge_dis_ctrl.setText(f"0x6003 Dis: 0x{val:02X} (EN={en_txt}, Rst={int(rst)})")
            self.badge_dis_ctrl.setStyleSheet(f"background-color: #0f172a; border: 1px solid {color}; border-radius: 6px; padding: 6px 10px; font-family: 'Consolas', monospace; font-size: 11px; color: {color};")

        elif echo.frame_id == FRAME_DISCHARGE_SEL:
            dec = val & 0x0F
            current_a = discharge_decimal_to_current(dec)
            switches = []
            if dec & 1: switches.append("L1")
            if dec & 2: switches.append("L2")
            if dec & 4: switches.append("L3")
            if dec & 8: switches.append("L4")
            sw_str = "+".join(switches) if switches else "None"
            color = "#f97316" if dec > 0 else "#94a3b8"
            self.lbl_dis_sel_rb.setText(f"Readback: 0x{dec:02X} [{sw_str} -> {current_a:.1f}A]")
            self.lbl_dis_sel_rb.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            self.badge_dis_sel.setText(f"0x6004 Loads: 0x{dec:02X} ({current_a:.1f}A)")
            self.badge_dis_sel.setStyleSheet(f"background-color: #0f172a; border: 1px solid {color}; border-radius: 6px; padding: 6px 10px; font-family: 'Consolas', monospace; font-size: 11px; color: {color};")

    def _clear_unwanted_flags(self) -> None:
        """Immediately clear all 5 control registers to zero (Safe Idle)."""
        # 1. Disable active drives
        self._command_sender(FRAME_CHARGE_CTRL, 0x00, 0)
        self._command_sender(FRAME_DISCHARGE_CTRL, 0x00, 0)
        # 2. De-select parameters & load switches
        self._command_sender(FRAME_CHARGE_SEL, 0x00, 0)
        self._command_sender(FRAME_DISCHARGE_SEL, 0x00, 0)
        # 3. Disconnect cell relay
        self._command_sender(FRAME_RELAY_CTRL, 0x00, 0)

        # Synchronize UI widgets
        self.chk_chg_en.setChecked(False)
        self.chk_dis_en.setChecked(False)
        self.chk_relay_en.setChecked(False)
        self.combo_dis_preset.setCurrentIndex(0)
        self.chk_curr_1.setChecked(False)
        self.chk_curr_2.setChecked(False)

    # --- Relay Helpers ---
    def _update_relay_summary(self) -> None:
        val = 0
        if self.chk_relay_en.isChecked():
            val |= RelayControlBits.CELL_ENABLE
        if self.combo_cell_sel.currentData() == 1:
            val |= RelayControlBits.CELL_SELECT

        cell_str = "Cell 2" if (val & RelayControlBits.CELL_SELECT) else "Cell 1"
        en_str = "Connected" if (val & RelayControlBits.CELL_ENABLE) else "Disconnected"
        self.lbl_relay_summary.setText(f"Wire: 0x{val:02X} ({cell_str} {en_str})")

    def _send_relay(self) -> None:
        val = 0
        if self.chk_relay_en.isChecked():
            val |= RelayControlBits.CELL_ENABLE
        if self.combo_cell_sel.currentData() == 1:
            val |= RelayControlBits.CELL_SELECT
        if val & RelayControlBits.CELL_ENABLE and not self._confirm_energy_action("connect the selected cell relay"):
            return
        self._command_sender(FRAME_RELAY_CTRL, val, 1)

    def _confirm_energy_action(self, action: str) -> bool:
        choice = QMessageBox.question(
            self,
            "Confirm Manual Hardware Action",
            f"This will {action}. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

    # --- Charge Select Helpers ---
    def _update_chg_sel_summary(self) -> None:
        val = 0
        if self.combo_chg_voltage.currentData() == 1:
            val |= ChargeSelectBits.MAX_CHARGE_VOLTAGE
        if self.chk_curr_1.isChecked():
            val |= ChargeSelectBits.MAX_CHARGE_CURRENT_1
        if self.chk_curr_2.isChecked():
            val |= ChargeSelectBits.MAX_CHARGE_CURRENT_2

        v_val = 4.2 if (val & ChargeSelectBits.MAX_CHARGE_VOLTAGE) else 3.6
        c_val = 0.0
        if val & ChargeSelectBits.MAX_CHARGE_CURRENT_1:
            c_val += 0.5
        if val & ChargeSelectBits.MAX_CHARGE_CURRENT_2:
            c_val += 1.0

        self.lbl_chg_sel_summary.setText(f"Target: {v_val:.1f}V @ {c_val:.1f} A (Wire: 0x{val:02X})")

    def _send_chg_sel(self) -> None:
        val = 0
        if self.combo_chg_voltage.currentData() == 1:
            val |= ChargeSelectBits.MAX_CHARGE_VOLTAGE
        if self.chk_curr_1.isChecked():
            val |= ChargeSelectBits.MAX_CHARGE_CURRENT_1
        if self.chk_curr_2.isChecked():
            val |= ChargeSelectBits.MAX_CHARGE_CURRENT_2
        self._command_sender(FRAME_CHARGE_SEL, val, 1)

    def _send_chg_ctrl(self) -> None:
        val = ChargeControlBits.CHARGE_ENABLE if self.chk_chg_en.isChecked() else 0
        if val and not self._confirm_energy_action("energize the charge control"):
            return
        self._command_sender(FRAME_CHARGE_CTRL, val, 1)

    def _pulse_chg_comp(self) -> None:
        """Pulse charge comparator reset high, then low (0 -> 1 -> 0)."""
        val_high = ChargeControlBits.CHARGE_COMPARATOR_RESET
        if self.chk_chg_en.isChecked():
            val_high |= ChargeControlBits.CHARGE_ENABLE
        if self.chk_chg_en.isChecked() and not self._confirm_energy_action("energize the charge comparator"):
            return
        self._command_sender(FRAME_CHARGE_CTRL, val_high, 0)
        # 50ms pulse duration before returning low
        val_low = ChargeControlBits.CHARGE_ENABLE if self.chk_chg_en.isChecked() else 0
        QTimer.singleShot(50, lambda: self._command_sender(FRAME_CHARGE_CTRL, val_low, 1))

    def _send_dis_ctrl(self) -> None:
        val = DischargeControlBits.DISCHARGE_ENABLE if self.chk_dis_en.isChecked() else 0
        if val and not self._confirm_energy_action("energize the discharge control"):
            return
        self._command_sender(FRAME_DISCHARGE_CTRL, val, 1)

    def _pulse_dis_comp(self) -> None:
        """Pulse discharge comparator reset high, then low (0 -> 1 -> 0)."""
        val_high = DischargeControlBits.DISCHARGE_COMPARATOR_RESET
        if self.chk_dis_en.isChecked():
            val_high |= DischargeControlBits.DISCHARGE_ENABLE
        if self.chk_dis_en.isChecked() and not self._confirm_energy_action("energize the discharge comparator"):
            return
        self._command_sender(FRAME_DISCHARGE_CTRL, val_high, 0)
        val_low = DischargeControlBits.DISCHARGE_ENABLE if self.chk_dis_en.isChecked() else 0
        QTimer.singleShot(50, lambda: self._command_sender(FRAME_DISCHARGE_CTRL, val_low, 1))

    # --- Discharge Load Bank Helpers ---
    def _on_dis_preset_changed(self, index: int) -> None:
        if self._syncing_loads:
            return
        self._syncing_loads = True
        dec = self.combo_dis_preset.currentData()
        if dec is not None:
            self.chk_load_1.setChecked(bool(dec & 1))
            self.chk_load_2.setChecked(bool(dec & 2))
            self.chk_load_3.setChecked(bool(dec & 4))
            self.chk_load_4.setChecked(bool(dec & 8))
            self._update_dis_summary(dec)
        self._syncing_loads = False

    def _on_dis_checkbox_changed(self) -> None:
        if self._syncing_loads:
            return
        self._syncing_loads = True
        dec = 0
        if self.chk_load_1.isChecked(): dec |= 1
        if self.chk_load_2.isChecked(): dec |= 2
        if self.chk_load_3.isChecked(): dec |= 4
        if self.chk_load_4.isChecked(): dec |= 8

        self.combo_dis_preset.setCurrentIndex(dec)
        self._update_dis_summary(dec)
        self._syncing_loads = False

    def _update_dis_summary(self, dec: int) -> None:
        current_a = discharge_decimal_to_current(dec)
        num_on = bin(dec).count("1")
        self.lbl_dis_sel_summary.setText(
            f"Total Current: {current_a:.1f} A | Active Switches: {num_on} | Decimal: {dec} (Wire: 0x{dec:02X})"
        )

    def _send_dis_sel(self) -> None:
        val = 0
        if self.chk_load_1.isChecked(): val |= DischargeSelectBits.LOAD_1
        if self.chk_load_2.isChecked(): val |= DischargeSelectBits.LOAD_2
        if self.chk_load_3.isChecked(): val |= DischargeSelectBits.LOAD_3
        if self.chk_load_4.isChecked(): val |= DischargeSelectBits.LOAD_4
        if val and not self._confirm_energy_action("enable discharge loads"):
            return
        self._command_sender(FRAME_DISCHARGE_SEL, val, 1)
