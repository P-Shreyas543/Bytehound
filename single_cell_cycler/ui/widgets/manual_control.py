"""Manual hardware control and switch override panel widget."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
    """Direct interactive overrides for 0x6000 - 0x6004 TX commands according to hardware spec."""

    def __init__(self, command_sender: Callable[[int, int, int], None], parent: QWidget | None = None):
        super().__init__(parent)
        self._command_sender = command_sender
        self._syncing_loads = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(12)

        # ----------------------------------------------------------------------
        # 1. 0x6000 Cell Relay Control
        # ----------------------------------------------------------------------
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

        btn_send_relay = QPushButton("Send Relay (0x6000)")
        btn_send_relay.clicked.connect(self._send_relay)
        l_relay.addWidget(btn_send_relay)
        grid.addWidget(box_relay, 0, 0)

        self.chk_relay_en.stateChanged.connect(self._update_relay_summary)
        self.combo_cell_sel.currentIndexChanged.connect(self._update_relay_summary)

        # ----------------------------------------------------------------------
        # 2. 0x6001 Cell Charge Select
        # ----------------------------------------------------------------------
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

        btn_send_chg_sel = QPushButton("Send Charge Sel (0x6001)")
        btn_send_chg_sel.clicked.connect(self._send_chg_sel)
        l_chg_sel.addWidget(btn_send_chg_sel)
        grid.addWidget(box_chg_sel, 0, 1)

        self.combo_chg_voltage.currentIndexChanged.connect(self._update_chg_sel_summary)
        self.chk_curr_1.stateChanged.connect(self._update_chg_sel_summary)
        self.chk_curr_2.stateChanged.connect(self._update_chg_sel_summary)

        # ----------------------------------------------------------------------
        # 3. 0x6002 Cell Charge Control
        # ----------------------------------------------------------------------
        box_chg_ctrl = QGroupBox("Charge Control (0x6002)")
        l_chg_ctrl = QVBoxLayout(box_chg_ctrl)
        self.chk_chg_en = QCheckBox("Charge Enable (Bit 0)")
        btn_reset_chg_comp = QPushButton("Pulse Comparator Reset (Bit 1)")
        btn_reset_chg_comp.clicked.connect(self._pulse_chg_comp)
        btn_send_chg_ctrl = QPushButton("Send Charge Ctrl (0x6002)")
        btn_send_chg_ctrl.clicked.connect(self._send_chg_ctrl)
        l_chg_ctrl.addWidget(self.chk_chg_en)
        l_chg_ctrl.addWidget(btn_reset_chg_comp)
        l_chg_ctrl.addWidget(btn_send_chg_ctrl)
        grid.addWidget(box_chg_ctrl, 0, 2)

        # ----------------------------------------------------------------------
        # 4. 0x6003 Cell Discharge Control
        # ----------------------------------------------------------------------
        box_dis_ctrl = QGroupBox("Discharge Control (0x6003)")
        l_dis_ctrl = QVBoxLayout(box_dis_ctrl)
        self.chk_dis_en = QCheckBox("Discharge Enable (Bit 0)")
        btn_reset_dis_comp = QPushButton("Pulse Comparator Reset (Bit 1)")
        btn_reset_dis_comp.clicked.connect(self._pulse_dis_comp)
        btn_send_dis_ctrl = QPushButton("Send Discharge Ctrl (0x6003)")
        btn_send_dis_ctrl.clicked.connect(self._send_dis_ctrl)
        l_dis_ctrl.addWidget(self.chk_dis_en)
        l_dis_ctrl.addWidget(btn_reset_dis_comp)
        l_dis_ctrl.addWidget(btn_send_dis_ctrl)
        grid.addWidget(box_dis_ctrl, 1, 0)

        # ----------------------------------------------------------------------
        # 5. 0x6004 Cell Discharge Select (16 Discrete Binary States)
        # ----------------------------------------------------------------------
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
        self._command_sender(FRAME_RELAY_CTRL, val, 1)

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
        self._command_sender(FRAME_CHARGE_CTRL, val, 1)

    def _pulse_chg_comp(self) -> None:
        val = ChargeControlBits.CHARGE_COMPARATOR_RESET
        if self.chk_chg_en.isChecked():
            val |= ChargeControlBits.CHARGE_ENABLE
        self._command_sender(FRAME_CHARGE_CTRL, val, 0)
        # Pulse low
        val_norm = ChargeControlBits.CHARGE_ENABLE if self.chk_chg_en.isChecked() else 0
        self._command_sender(FRAME_CHARGE_CTRL, val_norm, 1)

    def _send_dis_ctrl(self) -> None:
        val = DischargeControlBits.DISCHARGE_ENABLE if self.chk_dis_en.isChecked() else 0
        self._command_sender(FRAME_DISCHARGE_CTRL, val, 1)

    def _pulse_dis_comp(self) -> None:
        val = DischargeControlBits.DISCHARGE_COMPARATOR_RESET
        if self.chk_dis_en.isChecked():
            val |= DischargeControlBits.DISCHARGE_ENABLE
        self._command_sender(FRAME_DISCHARGE_CTRL, val, 0)
        val_norm = DischargeControlBits.DISCHARGE_ENABLE if self.chk_dis_en.isChecked() else 0
        self._command_sender(FRAME_DISCHARGE_CTRL, val_norm, 1)

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
        self._command_sender(FRAME_DISCHARGE_SEL, val, 1)
