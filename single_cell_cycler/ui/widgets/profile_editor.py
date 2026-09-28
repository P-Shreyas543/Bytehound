"""Interactive Test Profile and Recipe Editor widget."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
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
from ...core.profile_model import CutoffCondition, CutoffType, StepType, TestRecipe, TestStep
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


class ProfileEditorWidget(QWidget):
    """Interactive recipe step table and profile management widget."""

    recipe_loaded = Signal(object)  # TestRecipe

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.current_recipe: Optional[TestRecipe] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Top bar: Presets, Load, Save, New
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Test Recipe:"))
        self.combo_presets = QComboBox()
        self.combo_presets.setMinimumWidth(220)
        top_bar.addWidget(self.combo_presets)

        self.btn_load_file = QPushButton("Browse...")
        self.btn_load_file.clicked.connect(self._browse_recipe)
        top_bar.addWidget(self.btn_load_file)

        self.btn_save_file = QPushButton("Save Recipe")
        self.btn_save_file.clicked.connect(self._save_recipe)
        top_bar.addWidget(self.btn_save_file)

        self.btn_new = QPushButton("New Recipe")
        self.btn_new.clicked.connect(self._new_recipe)
        top_bar.addWidget(self.btn_new)

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

        # 3. Step control buttons
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

        # Populate built-in presets
        self._refresh_presets()
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        if self.combo_presets.count() > 0:
            self._on_preset_selected(0)

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
        self._render_table()
        self.recipe_loaded.emit(recipe)

    def _render_table(self) -> None:
        self.table_steps.setRowCount(0)
        if not self.current_recipe:
            return

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
        self.current_recipe = TestRecipe(
            recipe_name="Custom Test Recipe",
            steps=[
                TestStep(
                    step_index=1,
                    name="CC Charge",
                    step_type=StepType.CHARGE,
                    cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MAX, 4.20, True, "4.20V Cut-off")],
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
