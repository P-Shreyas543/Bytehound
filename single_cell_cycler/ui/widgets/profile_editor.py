"""Interactive Test Profile and Recipe Editor widget."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...comm.protocol_defs import DISCHARGE_TABLE, discharge_decimal_to_current
from ...config.cycler_config import RECIPES_DIR
from ...core.profile_model import (
    CHEMISTRY_PRESETS,
    ChemistryDef,
    CutoffCondition,
    CutoffType,
    StepType,
    TestRecipe,
    TestStep,
)
from ..theme import BG_CARD, BORDER_COLOR, COLOR_ACCENT


class CutoffEditDialog(QDialog):
    """Dialog for editing cutoffs on a single step."""

    def __init__(self, step: TestStep, parent: QWidget | None = None):
        super().__init__(parent)
        self.step = step
        self.setWindowTitle(f"Edit Cut-off Conditions: {step.name}")
        self.resize(520, 360)

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Cut-off Type", "Threshold", "Enabled", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Buttons row
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("+ Add Condition")
        self.btn_add.clicked.connect(self._add_row)
        btn_row.addWidget(self.btn_add)

        self.btn_del = QPushButton("- Remove Selected")
        self.btn_del.clicked.connect(self._delete_row)
        btn_row.addWidget(self.btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Dialog controls
        ctrl_row = QHBoxLayout()
        ctrl_row.addStretch()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.clicked.connect(self._save_and_accept)
        ctrl_row.addWidget(self.btn_ok)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        ctrl_row.addWidget(self.btn_cancel)
        layout.addLayout(ctrl_row)

        self._populate_table()

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for cond in self.step.cutoffs:
            self._insert_cutoff_row(cond)

    def _insert_cutoff_row(self, cond: CutoffCondition) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        combo = QComboBox()
        for ct in CutoffType:
            combo.addItem(ct.value)
        combo.setCurrentText(cond.cutoff_type.value)
        self.table.setCellWidget(row, 0, combo)

        spin = QDoubleSpinBox()
        spin.setRange(-1000.0, 100000.0)
        spin.setDecimals(3)
        spin.setValue(cond.threshold)
        self.table.setCellWidget(row, 1, spin)

        chk = QTableWidgetItem()
        chk.setCheckState(Qt.CheckState.Checked if cond.enabled else Qt.CheckState.Unchecked)
        self.table.setItem(row, 2, chk)

        desc_item = QTableWidgetItem(cond.description)
        self.table.setItem(row, 3, desc_item)

    def _add_row(self) -> None:
        new_cond = CutoffCondition(CutoffType.VOLTAGE_MAX, 4.20, True, "Voltage cut-off")
        self._insert_cutoff_row(new_cond)

    def _delete_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _save_and_accept(self) -> None:
        updated_cutoffs = []
        for r in range(self.table.rowCount()):
            combo = self.table.cellWidget(r, 0)
            spin = self.table.cellWidget(r, 1)
            chk = self.table.item(r, 2)
            desc_item = self.table.item(r, 3)

            ctype = CutoffType(combo.currentText())
            thresh = float(spin.value())
            enabled = chk.checkState() == Qt.CheckState.Checked
            desc = desc_item.text() if desc_item else ""

            updated_cutoffs.append(CutoffCondition(ctype, thresh, enabled, desc))

        self.step.cutoffs = updated_cutoffs
        self.accept()


class StepHardwareDialog(QDialog):
    """Dialog for configuring Step Voltage, Current, and Load Setpoints according to hardware spec."""

    def __init__(self, step: TestStep, parent: QWidget | None = None):
        super().__init__(parent)
        self.step = step
        self.setWindowTitle(f"Configure Hardware Setpoints: {step.name}")
        self.resize(460, 320)
        self._syncing_loads = False

        layout = QVBoxLayout(self)

        # Step Type & Cell
        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Step Type:"))
        self.lbl_type = QLabel(f"<b>{step.step_type.value}</b>")
        row_type.addWidget(self.lbl_type)
        row_type.addStretch()
        row_type.addWidget(QLabel("Target Cell:"))
        self.combo_cell = QComboBox()
        self.combo_cell.addItem("Cell 1 (Bit 1 = 0)", 1)
        self.combo_cell.addItem("Cell 2 (Bit 1 = 1)", 2)
        cur_cell = getattr(step, "cell_select", 1)
        self.combo_cell.setCurrentIndex(0 if cur_cell == 1 else 1)
        row_type.addWidget(self.combo_cell)
        layout.addLayout(row_type)

        # Charge Group (0x6001)
        self.grp_charge = QGroupBox("Charge Setpoints (0x6001)")
        l_chg = QVBoxLayout(self.grp_charge)
        row_cv = QHBoxLayout()
        row_cv.addWidget(QLabel("Max Voltage (Bit 0):"))
        self.combo_v = QComboBox()
        self.combo_v.addItem("4.2 V (Bit 0 = 1, NMC/LCO)", 1)
        self.combo_v.addItem("3.6 V (Bit 0 = 0, LFP)", 0)
        self.combo_v.setCurrentIndex(0 if step.max_charge_voltage else 1)
        row_cv.addWidget(self.combo_v)
        l_chg.addLayout(row_cv)

        row_ci = QHBoxLayout()
        row_ci.addWidget(QLabel("Charge Current (Bits 1, 2):"))
        self.combo_i = QComboBox()
        self.combo_i.addItem("0.5 A (Curr 1 = 1)", 0.5)
        self.combo_i.addItem("1.0 A (Curr 2 = 1)", 1.0)
        self.combo_i.addItem("1.5 A (Curr 1+2 = 1)", 1.5)
        self.combo_i.addItem("0.0 A (Both = 0)", 0.0)
        target_c = step.charge_current_target
        idx = self.combo_i.findData(target_c)
        if idx >= 0:
            self.combo_i.setCurrentIndex(idx)
        row_ci.addWidget(self.combo_i)
        l_chg.addLayout(row_ci)
        layout.addWidget(self.grp_charge)

        # Discharge Group (0x6004)
        self.grp_discharge = QGroupBox("Discharge Load Bank Setpoints (0x6004)")
        l_dis = QVBoxLayout(self.grp_discharge)
        row_dis_combo = QHBoxLayout()
        row_dis_combo.addWidget(QLabel("Target Load State:"))
        self.combo_dis = QComboBox()
        for dec in range(16):
            l1, l2, l3, l4, _, cur = DISCHARGE_TABLE[dec]
            switches = []
            if l1: switches.append("L1")
            if l2: switches.append("L2")
            if l3: switches.append("L3")
            if l4: switches.append("L4")
            s_txt = "+".join(switches) if switches else "OFF"
            self.combo_dis.addItem(f"{cur:.1f} A ({s_txt}) [Dec {dec}]", dec)
        self.combo_dis.setCurrentIndex(step.discharge_load_decimal)
        row_dis_combo.addWidget(self.combo_dis)
        l_dis.addLayout(row_dis_combo)

        row_switches = QHBoxLayout()
        self.chk_l1 = QCheckBox("L1 (0.2A)")
        self.chk_l2 = QCheckBox("L2 (0.4A)")
        self.chk_l3 = QCheckBox("L3 (0.8A)")
        self.chk_l4 = QCheckBox("L4 (1.6A)")
        dec = step.discharge_load_decimal
        self.chk_l1.setChecked(bool(dec & 1))
        self.chk_l2.setChecked(bool(dec & 2))
        self.chk_l3.setChecked(bool(dec & 4))
        self.chk_l4.setChecked(bool(dec & 8))
        row_switches.addWidget(self.chk_l1)
        row_switches.addWidget(self.chk_l2)
        row_switches.addWidget(self.chk_l3)
        row_switches.addWidget(self.chk_l4)
        l_dis.addLayout(row_switches)
        layout.addWidget(self.grp_discharge)

        # Enable/disable based on step type
        if step.step_type == StepType.CHARGE:
            self.grp_charge.setEnabled(True)
            self.grp_discharge.setEnabled(False)
        elif step.step_type == StepType.DISCHARGE:
            self.grp_charge.setEnabled(False)
            self.grp_discharge.setEnabled(True)
        else:
            self.grp_charge.setEnabled(False)
            self.grp_discharge.setEnabled(False)

        # Wire sync
        self.combo_dis.currentIndexChanged.connect(self._on_combo_dis_changed)
        self.chk_l1.stateChanged.connect(self._on_chk_dis_changed)
        self.chk_l2.stateChanged.connect(self._on_chk_dis_changed)
        self.chk_l3.stateChanged.connect(self._on_chk_dis_changed)
        self.chk_l4.stateChanged.connect(self._on_chk_dis_changed)

        # Dialog Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_ok = QPushButton("Save Setpoints")
        btn_ok.clicked.connect(self._save_and_accept)
        btn_box.addWidget(btn_ok)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _on_combo_dis_changed(self, idx: int) -> None:
        if self._syncing_loads:
            return
        self._syncing_loads = True
        dec = self.combo_dis.currentData()
        if dec is not None:
            self.chk_l1.setChecked(bool(dec & 1))
            self.chk_l2.setChecked(bool(dec & 2))
            self.chk_l3.setChecked(bool(dec & 4))
            self.chk_l4.setChecked(bool(dec & 8))
        self._syncing_loads = False

    def _on_chk_dis_changed(self) -> None:
        if self._syncing_loads:
            return
        self._syncing_loads = True
        dec = (
            (1 if self.chk_l1.isChecked() else 0)
            | (2 if self.chk_l2.isChecked() else 0)
            | (4 if self.chk_l3.isChecked() else 0)
            | (8 if self.chk_l4.isChecked() else 0)
        )
        self.combo_dis.setCurrentIndex(dec)
        self._syncing_loads = False

    def _save_and_accept(self) -> None:
        self.step.cell_select = self.combo_cell.currentData()
        if self.step.step_type == StepType.CHARGE:
            v_val = 4.2 if self.combo_v.currentData() == 1 else 3.6
            c_val = float(self.combo_i.currentData())
            self.step.set_charge_setpoints(v_val, c_val)
        elif self.step.step_type == StepType.DISCHARGE:
            dec = self.combo_dis.currentData()
            self.step.discharge_load_1 = bool(dec & 1)
            self.step.discharge_load_2 = bool(dec & 2)
            self.step.discharge_load_3 = bool(dec & 4)
            self.step.discharge_load_4 = bool(dec & 8)
        self.accept()


class RecipeTimelinePreview(QWidget):
    """Miniature visual timeline preview showing planned voltage & current schedules."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        # Header bar with title and inline color-coded legends
        hdr = QHBoxLayout()
        hdr.setContentsMargins(4, 2, 4, 2)
        lbl_title = QLabel("📊 Planned Profile Schedule Preview")
        lbl_title.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 11px;")
        hdr.addWidget(lbl_title)

        hdr.addSpacing(16)
        lbl_v = QLabel("■ Planned Voltage V(t)")
        lbl_v.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 11px;")
        hdr.addWidget(lbl_v)

        lbl_i = QLabel("■ Planned Current I(t)")
        lbl_i.setStyleSheet("color: #10b981; font-weight: 600; font-size: 11px;")
        hdr.addWidget(lbl_i)

        lbl_note = QLabel("(Simulated Progression)")
        lbl_note.setStyleSheet("color: #64748b; font-size: 10px; font-style: italic;")
        hdr.addWidget(lbl_note)

        hdr.addStretch()
        layout.addLayout(hdr)

        # Main PyQtGraph PlotWidget
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel("bottom", "<span style='color:#94a3b8; font-weight:600; font-size:10px;'>Simulated Time (s)</span>")
        self.plot.setLabel("left", "<span style='color:#38bdf8; font-weight:bold; font-size:10px;'>Voltage (V)</span>")
        self.plot.plotItem.getAxis("bottom").setTickPen(pg.mkPen("#334155", width=1))
        self.plot.plotItem.getAxis("left").setTickPen(pg.mkPen("#334155", width=1))

        # Right axis for current
        self.view_i = pg.ViewBox()
        self.plot.plotItem.scene().addItem(self.view_i)
        ax_r = self.plot.plotItem.getAxis("right")
        ax_r.linkToView(self.view_i)
        self.plot.plotItem.showAxis("right")
        self.view_i.setXLink(self.plot.plotItem)
        ax_r.setLabel("<span style='color:#10b981; font-weight:bold; font-size:10px;'>Current (A)</span>")
        ax_r.setTickPen(pg.mkPen("#334155", width=1))
        self.view_i.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.view_i.setYRange(-3.5, 3.5, padding=0.0)

        # Plot curves
        self.curve_v = self.plot.plot(pen=pg.mkPen("#38bdf8", width=2.0))
        self.curve_i = pg.PlotDataItem(pen=pg.mkPen("#10b981", width=1.8))
        self.view_i.addItem(self.curve_i)

        self.step_lines: list[pg.InfiniteLine] = []
        self.step_labels: list[pg.TextItem] = []

        self.plot.plotItem.getViewBox().sigResized.connect(self._sync_view)
        layout.addWidget(self.plot)
        self.setMinimumHeight(140)
        self.setMaximumHeight(200)

    def _sync_view(self) -> None:
        self.view_i.setGeometry(self.plot.plotItem.getViewBox().sceneBoundingRect())
        self.view_i.linkedViewChanged(self.plot.plotItem.getViewBox(), self.view_i.XAxis)

    def update_preview(self, recipe: TestRecipe | None) -> None:
        """Simulate and plot the expected voltage and current trajectories for the recipe."""
        for line in self.step_lines:
            self.plot.removeItem(line)
        for label in self.step_labels:
            self.plot.removeItem(label)
        self.step_lines.clear()
        self.step_labels.clear()

        if not recipe or not recipe.steps:
            self.curve_v.setData([], [])
            self.curve_i.setData([], [])
            return

        chem = CHEMISTRY_PRESETS.get(recipe.chemistry, CHEMISTRY_PRESETS["CUSTOM"])

        all_t = [0.0]
        all_v = [chem.nominal_voltage]
        all_i = [0.0]

        cur_t = 0.0
        cur_v = chem.nominal_voltage

        # Expand loop steps up to max 2 iterations for preview
        expanded_steps: list[tuple[int, TestStep]] = []
        i = 0
        loop_counts: dict[int, int] = {}
        while i < len(recipe.steps) and len(expanded_steps) < 25:
            step = recipe.steps[i]
            if step.step_type == StepType.LOOP:
                rem = loop_counts.get(i, min(step.loop_count, 2))
                if rem > 1:
                    loop_counts[i] = rem - 1
                    target_idx = max(0, min(len(recipe.steps) - 1, step.loop_target_step - 1))
                    i = target_idx
                    continue
                else:
                    loop_counts[i] = min(step.loop_count, 2)
                    i += 1
                    continue
            expanded_steps.append((i + 1, step))
            i += 1

        for step_num, step in expanded_steps:
            step_start_t = cur_t

            # Step duration (seconds)
            duration = 180.0
            for c in step.cutoffs:
                if c.enabled and c.cutoff_type == CutoffType.DURATION_MAX and c.threshold > 0:
                    duration = min(c.threshold, 1800.0)
                    break

            if step.step_type == StepType.CHARGE:
                target_i = step.charge_current_target
                target_v = min(chem.max_voltage, step.charge_voltage_target)
                for c in step.cutoffs:
                    if c.enabled and c.cutoff_type == CutoffType.VOLTAGE_MAX:
                        target_v = c.threshold
                        break
            elif step.step_type == StepType.DISCHARGE:
                target_i = -step.discharge_current_target
                target_v = chem.min_voltage
                for c in step.cutoffs:
                    if c.enabled and c.cutoff_type == CutoffType.VOLTAGE_MIN:
                        target_v = c.threshold
                        break
            else:  # REST
                target_i = 0.0
                target_v = cur_v

            pts = 20
            t_seg = np.linspace(cur_t, cur_t + duration, pts)
            v_seg = np.linspace(cur_v, target_v, pts)
            i_seg = np.full(pts, target_i)

            all_t.extend(t_seg[1:])
            all_v.extend(v_seg[1:])
            all_i.extend(i_seg[1:])

            cur_t += duration
            cur_v = target_v

            # Step vertical boundary marker
            if step_start_t > 0:
                line = pg.InfiniteLine(
                    pos=step_start_t,
                    angle=90,
                    pen=pg.mkPen("#475569", width=1.0, style=Qt.PenStyle.DashLine),
                )
                self.plot.addItem(line)
                self.step_lines.append(line)

            txt = pg.TextItem(f"S{step_num}", color="#94a3b8", anchor=(0.0, 1.0))
            txt.setPos(step_start_t + 2.0, chem.max_voltage)
            self.plot.addItem(txt)
            self.step_labels.append(txt)

        self.curve_v.setData(all_t, all_v)
        self.curve_i.setData(all_t, all_i)

        max_t = max(10.0, cur_t)
        self.plot.setXRange(0.0, max_t, padding=0.02)
        y_min = max(0.0, chem.min_voltage - 0.5)
        y_max = chem.max_voltage + 0.4
        self.plot.setYRange(y_min, y_max, padding=0.0)
        self.view_i.setYRange(-3.5, 3.5, padding=0.0)
        self._sync_view()


class ProfileEditorWidget(QWidget):
    """Interactive recipe step table and profile management widget."""

    recipe_loaded = Signal(object)  # TestRecipe
    validation_changed = Signal(bool, list)  # is_valid, list of error messages

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.current_recipe: Optional[TestRecipe] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Top bar: Recipe controls & Cell Chemistry Selector (IMP-03)
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Recipe:"))
        self.combo_presets = QComboBox()
        self.combo_presets.setMinimumWidth(180)
        top_bar.addWidget(self.combo_presets)

        self.btn_load_file = QPushButton("Browse...")
        self.btn_load_file.clicked.connect(self._browse_recipe)
        top_bar.addWidget(self.btn_load_file)

        self.btn_save_file = QPushButton("Save Recipe")
        self.btn_save_file.clicked.connect(self._save_recipe)
        top_bar.addWidget(self.btn_save_file)

        self.btn_new = QPushButton("New")
        self.btn_new.clicked.connect(self._new_recipe)
        top_bar.addWidget(self.btn_new)

        top_bar.addSpacing(12)

        # Cell Chemistry Selector & Safety Guardrail Badge (IMP-03)
        lbl_chem = QLabel("Cell Chemistry:")
        lbl_chem.setStyleSheet("font-weight: 600; color: #f8fafc;")
        top_bar.addWidget(lbl_chem)

        self.combo_chemistry = QComboBox()
        self.combo_chemistry.setMinimumWidth(190)
        for code, chem in CHEMISTRY_PRESETS.items():
            self.combo_chemistry.addItem(chem.name, code)
        self.combo_chemistry.currentIndexChanged.connect(self._on_chemistry_changed)
        top_bar.addWidget(self.combo_chemistry)

        self.lbl_chem_info = QLabel()
        self.lbl_chem_info.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #0284c7; color: #38bdf8; "
            "border-radius: 4px; padding: 2px 7px; font-weight: 600; font-size: 11px;"
        )
        top_bar.addWidget(self.lbl_chem_info)

        top_bar.addStretch()
        layout.addLayout(top_bar)

        # 2. Step Table
        self.table_steps = QTableWidget(0, 7)
        self.table_steps.setHorizontalHeaderLabels([
            "Step #",
            "Name",
            "Type",
            "Hardware Setpoints",
            "Cut-offs Summary",
            "Loop Target",
            "Loop Count",
        ])
        self.table_steps.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_steps.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table_steps.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table_steps)

        # 3. Chemistry Validation Warning Banner (IMP-03)
        self.lbl_validation_banner = QLabel()
        self.lbl_validation_banner.setWordWrap(True)
        self.lbl_validation_banner.setStyleSheet(
            "background-color: #451a03; border: 1px solid #f97316; color: #fed7aa; "
            "border-radius: 5px; padding: 6px 10px; font-size: 11px; font-weight: 600;"
        )
        self.lbl_validation_banner.setVisible(False)
        layout.addWidget(self.lbl_validation_banner)

        # 4. Step control buttons
        btn_bar = QHBoxLayout()
        self.btn_add_step = QPushButton("+ Add Step")
        self.btn_add_step.clicked.connect(self._add_step)
        btn_bar.addWidget(self.btn_add_step)

        self.btn_edit_hw = QPushButton("⚙ Configure Setpoints...")
        self.btn_edit_hw.clicked.connect(self._edit_hardware_setpoints)
        btn_bar.addWidget(self.btn_edit_hw)

        self.btn_edit_cutoffs = QPushButton("Edit Cut-offs...")
        self.btn_edit_cutoffs.clicked.connect(self._edit_cutoffs)
        btn_bar.addWidget(self.btn_edit_cutoffs)

        self.btn_del_step = QPushButton("- Delete Step")
        self.btn_del_step.clicked.connect(self._del_step)
        btn_bar.addWidget(self.btn_del_step)

        self.btn_move_up = QPushButton("▲ Move Up")
        self.btn_move_up.clicked.connect(lambda: self._move_step(-1))
        btn_bar.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton("▼ Move Down")
        self.btn_move_down.clicked.connect(lambda: self._move_step(1))
        btn_bar.addWidget(self.btn_move_down)

        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # 5. Recipe Timeline Schedule Preview (IMP-04)
        self.preview_widget = RecipeTimelinePreview()
        layout.addWidget(self.preview_widget)

        # Populate built-in presets
        self._refresh_presets()
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        # Select 15-cycle CCCV profile by default if present, otherwise first available
        default_idx = 0
        for i in range(self.combo_presets.count()):
            if "15" in self.combo_presets.itemText(i):
                default_idx = i
                break
        self.combo_presets.setCurrentIndex(default_idx)
        if self.combo_presets.count() > 0:
            self._on_preset_selected(default_idx)
        else:
            self._on_chemistry_changed(self.combo_chemistry.currentIndex())

    @property
    def active_chemistry(self) -> ChemistryDef:
        code = self.combo_chemistry.currentData() if hasattr(self, "combo_chemistry") else "NMC"
        return CHEMISTRY_PRESETS.get(code, CHEMISTRY_PRESETS["CUSTOM"])

    def _on_chemistry_changed(self, index: int) -> None:
        code = self.combo_chemistry.currentData()
        chem = CHEMISTRY_PRESETS.get(code, CHEMISTRY_PRESETS["CUSTOM"])
        self.lbl_chem_info.setText(
            f"Nominal: {chem.nominal_voltage:.1f}V | Safe Range: [{chem.min_voltage:.2f}V – {chem.max_voltage:.2f}V] | Max I: {chem.max_charge_current:.1f}A"
        )
        if self.current_recipe:
            self.current_recipe.chemistry = code
            self._render_table()
            self.recipe_loaded.emit(self.current_recipe)

    def get_validation_errors(self) -> List[str]:
        if not self.current_recipe:
            return []
        return self.current_recipe.validate_chemistry_limits()

    def _validate_and_render_status(self) -> List[str]:
        errors = self.get_validation_errors()
        if errors:
            err_html = "<br>• ".join(errors)
            self.lbl_validation_banner.setText(
                f"⚠️ <b>Chemistry Safety Guardrail Violations ({self.active_chemistry.code}):</b><br>• {err_html}"
            )
            self.lbl_validation_banner.setVisible(True)
        else:
            self.lbl_validation_banner.setVisible(False)
        self.validation_changed.emit(len(errors) == 0, errors)
        return errors

    def _refresh_presets(self) -> None:
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        if RECIPES_DIR.exists():
            for p in sorted(RECIPES_DIR.glob("*.json")):
                self.combo_presets.addItem(p.stem.replace("_", " ").title(), str(p))
        self.combo_presets.blockSignals(False)

    def _on_preset_selected(self, index: int) -> None:
        file_path = self.combo_presets.currentData()
        if file_path and Path(file_path).is_file():
            try:
                recipe = TestRecipe.load_json(file_path)
                self.set_recipe(recipe)
            except Exception as exc:
                QMessageBox.warning(self, "Load Error", f"Could not load recipe: {exc}")

    def set_recipe(self, recipe: TestRecipe) -> None:
        self.current_recipe = recipe
        chem_code = getattr(recipe, "chemistry", "NMC")
        idx = self.combo_chemistry.findData(chem_code)
        if idx >= 0 and idx != self.combo_chemistry.currentIndex():
            self.combo_chemistry.blockSignals(True)
            self.combo_chemistry.setCurrentIndex(idx)
            self.combo_chemistry.blockSignals(False)
        chem = CHEMISTRY_PRESETS.get(chem_code, CHEMISTRY_PRESETS["CUSTOM"])
        self.lbl_chem_info.setText(
            f"Nominal: {chem.nominal_voltage:.1f}V | Safe Range: [{chem.min_voltage:.2f}V – {chem.max_voltage:.2f}V] | Max I: {chem.max_charge_current:.1f}A"
        )
        self._render_table()
        self.recipe_loaded.emit(recipe)

    def _render_table(self) -> None:
        self.table_steps.setRowCount(0)
        if not self.current_recipe:
            return

        chem = self.active_chemistry

        for i, s in enumerate(self.current_recipe.steps):
            s.step_index = i + 1
            row = self.table_steps.rowCount()
            self.table_steps.insertRow(row)

            # Step #
            item_num = QTableWidgetItem(str(s.step_index))
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_steps.setItem(row, 0, item_num)

            # Name
            self.table_steps.setItem(row, 1, QTableWidgetItem(s.name))

            # Type combo
            combo_type = QComboBox()
            for st in StepType:
                combo_type.addItem(st.value)
            combo_type.setCurrentText(s.step_type.value)
            combo_type.currentTextChanged.connect(lambda val, stp=s: self._on_type_changed(stp, val))
            self.table_steps.setCellWidget(row, 2, combo_type)

            # Hardware Setpoints summary
            hw_summary = self._format_hw_summary(s)
            self.table_steps.setItem(row, 3, QTableWidgetItem(hw_summary))

            # Cutoffs Summary
            cutoff_summary = ", ".join(f"{c.cutoff_type.value}: {c.threshold:g}" for c in s.cutoffs if c.enabled)
            self.table_steps.setItem(row, 4, QTableWidgetItem(cutoff_summary or "--"))

            # Loop Target
            spin_target = QSpinBox()
            spin_target.setRange(1, max(1, len(self.current_recipe.steps)))
            spin_target.setValue(s.loop_target_step)
            spin_target.valueChanged.connect(lambda val, stp=s: setattr(stp, "loop_target_step", val))
            self.table_steps.setCellWidget(row, 5, spin_target)

            # Loop Count
            spin_count = QSpinBox()
            spin_count.setRange(1, 10000)
            spin_count.setValue(s.loop_count)
            spin_count.valueChanged.connect(lambda val, stp=s: setattr(stp, "loop_count", val))
            self.table_steps.setCellWidget(row, 6, spin_count)

            # Check if this step violates active chemistry guardrails
            has_error = False
            if s.step_type == StepType.CHARGE:
                if s.charge_voltage_target > chem.max_voltage or s.charge_current_target > chem.max_charge_current:
                    has_error = True
            elif s.step_type == StepType.DISCHARGE:
                if s.discharge_current_target > chem.max_discharge_current:
                    has_error = True
            for c in s.cutoffs:
                if c.enabled:
                    if c.cutoff_type == CutoffType.VOLTAGE_MAX and c.threshold > chem.max_voltage:
                        has_error = True
                    elif c.cutoff_type == CutoffType.VOLTAGE_MIN and c.threshold < chem.min_voltage:
                        has_error = True

            if has_error:
                for col in [0, 1, 3, 4]:
                    item = self.table_steps.item(row, col)
                    if item:
                        item.setBackground(QColor("#450a0a"))
                        item.setForeground(QColor("#fca5a5"))

        self._validate_and_render_status()
        if hasattr(self, "preview_widget"):
            self.preview_widget.update_preview(self.current_recipe)

    def _format_hw_summary(self, step: TestStep) -> str:
        cell_str = f"Cell {getattr(step, 'cell_select', 1)}"
        if step.step_type == StepType.CHARGE:
            v = step.charge_voltage_target
            c = step.charge_current_target
            return f"Charge: {v:.1f}V @ {c:.1f}A ({cell_str})"
        elif step.step_type == StepType.DISCHARGE:
            cur = step.discharge_current_target
            loads = []
            if step.discharge_load_1: loads.append("L1")
            if step.discharge_load_2: loads.append("L2")
            if step.discharge_load_3: loads.append("L3")
            if step.discharge_load_4: loads.append("L4")
            sw_str = "+".join(loads) if loads else "OFF"
            return f"Discharge: {cur:.1f}A [{sw_str}] ({cell_str})"
        elif step.step_type == StepType.REST:
            return f"OCV Rest ({cell_str})"
        elif step.step_type == StepType.LOOP:
            return f"Loop -> Step {step.loop_target_step} ({step.loop_count}x)"
        return "--"

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col == 4:
            self._edit_cutoffs()
        else:
            self._edit_hardware_setpoints()

    def _edit_hardware_setpoints(self) -> None:
        row = self.table_steps.currentRow()
        if row < 0 or not self.current_recipe:
            QMessageBox.information(self, "Select Step", "Please select a step to edit hardware setpoints.")
            return

        step = self.current_recipe.steps[row]
        dlg = StepHardwareDialog(step, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._render_table()
            self.recipe_loaded.emit(self.current_recipe)

    def _on_type_changed(self, step: TestStep, val: str) -> None:
        step.step_type = StepType(val)
        self._render_table()

    def _edit_cutoffs(self) -> None:
        row = self.table_steps.currentRow()
        if row < 0 or not self.current_recipe:
            QMessageBox.information(self, "Select Step", "Please select a step to edit cut-offs.")
            return

        step = self.current_recipe.steps[row]
        dlg = CutoffEditDialog(step, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._render_table()
            self.recipe_loaded.emit(self.current_recipe)

    def _add_step(self) -> None:
        if not self.current_recipe:
            self._new_recipe()

        assert self.current_recipe is not None
        idx = len(self.current_recipe.steps) + 1
        new_s = TestStep(
            step_index=idx,
            name=f"Step {idx}",
            step_type=StepType.REST,
            cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 60.0, True, "60s Rest")],
        )
        self.current_recipe.steps.append(new_s)
        self._render_table()
        self.recipe_loaded.emit(self.current_recipe)

    def _del_step(self) -> None:
        row = self.table_steps.currentRow()
        if row >= 0 and self.current_recipe and len(self.current_recipe.steps) > row:
            self.current_recipe.steps.pop(row)
            self._render_table()
            self.recipe_loaded.emit(self.current_recipe)

    def _move_step(self, direction: int) -> None:
        row = self.table_steps.currentRow()
        if row < 0 or not self.current_recipe:
            return
        new_row = row + direction
        if 0 <= new_row < len(self.current_recipe.steps):
            steps = self.current_recipe.steps
            steps[row], steps[new_row] = steps[new_row], steps[row]
            self._render_table()
            self.table_steps.selectRow(new_row)
            self.recipe_loaded.emit(self.current_recipe)

    def _new_recipe(self) -> None:
        chem_code = self.active_chemistry.code
        chem = self.active_chemistry
        cutoff_v = round(min(4.20, chem.max_voltage), 2)
        self.current_recipe = TestRecipe(
            recipe_name="Custom Test Recipe",
            chemistry=chem_code,
            steps=[
                TestStep(
                    step_index=1,
                    name="CC Charge",
                    step_type=StepType.CHARGE,
                    max_charge_voltage=(cutoff_v >= 4.0),
                    cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MAX, cutoff_v, True, f"{cutoff_v:.2f}V Cut-off")],
                ),
                TestStep(
                    step_index=2,
                    name="Rest",
                    step_type=StepType.REST,
                    cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 300.0, True, "5m Rest")],
                ),
            ],
        )
        self._render_table()
        self.recipe_loaded.emit(self.current_recipe)

    def _browse_recipe(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Test Recipe", str(RECIPES_DIR), "JSON Files (*.json)")
        if file_path:
            try:
                recipe = TestRecipe.load_json(file_path)
                self.set_recipe(recipe)
            except Exception as exc:
                QMessageBox.warning(self, "Load Error", f"Failed to load recipe: {exc}")

    def _save_recipe(self) -> None:
        if not self.current_recipe:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Recipe", str(RECIPES_DIR), "JSON Files (*.json)")
        if file_path:
            try:
                self.current_recipe.save_json(file_path)
                QMessageBox.information(self, "Saved", f"Recipe saved to {file_path}")
                self._refresh_presets()
            except Exception as exc:
                QMessageBox.warning(self, "Save Error", f"Failed to save recipe: {exc}")
