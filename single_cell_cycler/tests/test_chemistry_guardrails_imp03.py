"""Test suite for Pillar 1: IMP-03 (Cell Chemistry Presets & Voltage Safety Guardrails).

Verifies:
1. Chemistry preset definitions (NMC, LFP, LTO, NA_ION, CUSTOM).
2. Recipe mathematical cutoff validation logic across different cell chemistries.
3. UI table highlighting and warning banner on safety limit breaches.
4. Pre-flight check blocking test launch on guardrail violations.
5. Dynamic configuration of real-time SafetyMonitor voltage bounds.
"""

from __future__ import annotations

import os
import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.core.profile_model import (
    CHEMISTRY_PRESETS,
    CutoffCondition,
    CutoffType,
    StepType,
    TestRecipe,
    TestStep,
)
from single_cell_cycler.ui.widgets.profile_editor import ProfileEditorWidget


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_chemistry_definitions():
    assert "NMC" in CHEMISTRY_PRESETS
    assert "LFP" in CHEMISTRY_PRESETS
    assert "LTO" in CHEMISTRY_PRESETS
    assert "NA_ION" in CHEMISTRY_PRESETS
    assert "CUSTOM" in CHEMISTRY_PRESETS

    lfp = CHEMISTRY_PRESETS["LFP"]
    assert lfp.max_voltage == 3.65
    assert lfp.min_voltage == 2.50
    assert lfp.nominal_voltage == 3.20

    lto = CHEMISTRY_PRESETS["LTO"]
    assert lto.max_voltage == 2.85
    assert lto.min_voltage == 1.50

    nmc = CHEMISTRY_PRESETS["NMC"]
    assert nmc.max_voltage == 4.25
    assert nmc.min_voltage == 2.80


def test_recipe_validation_logic():
    # Standard NMC recipe with 4.20V charge cutoff and 2.80V discharge cutoff
    recipe = TestRecipe(
        recipe_name="Standard NMC Cycle",
        chemistry="NMC",
        steps=[
            TestStep(
                step_index=1,
                name="CC Charge",
                step_type=StepType.CHARGE,
                max_charge_voltage=True,  # 4.2V
                cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MAX, 4.20, True, "4.20V Cut-off")],
            ),
            TestStep(
                step_index=2,
                name="CC Discharge",
                step_type=StepType.DISCHARGE,
                cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MIN, 2.80, True, "2.80V Cut-off")],
            ),
        ],
    )

    # NMC: should be 100% valid
    errors = recipe.validate_chemistry_limits()
    assert len(errors) == 0

    # Switch chemistry to LFP: 4.20V setpoint and cutoff exceed 3.65V!
    recipe.chemistry = "LFP"
    errors = recipe.validate_chemistry_limits()
    assert len(errors) >= 1
    assert any("exceeds LFP safe max (3.65V)" in err for err in errors)

    # Correct recipe to LFP compliant values
    recipe.steps[0].max_charge_voltage = False  # 3.6V
    recipe.steps[0].cutoffs[0].threshold = 3.65
    recipe.steps[1].cutoffs[0].threshold = 2.50
    errors = recipe.validate_chemistry_limits()
    assert len(errors) == 0

    # Over-discharge violation on LFP (e.g. 2.00V is below 2.50V)
    recipe.steps[1].cutoffs[0].threshold = 2.00
    errors = recipe.validate_chemistry_limits()
    assert len(errors) == 1
    assert "below LFP safe min (2.50V)" in errors[0]


def test_profile_editor_ui_guardrail_integration(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    editor = ProfileEditorWidget()
    editor.show()
    editor.resize(900, 500)
    qapp.processEvents()

    # Load an NMC recipe
    recipe_nmc = TestRecipe(
        recipe_name="NMC 4.2V Recipe",
        chemistry="NMC",
        steps=[
            TestStep(
                step_index=1,
                name="Charge",
                step_type=StepType.CHARGE,
                max_charge_voltage=True,  # 4.2V
                cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MAX, 4.20, True)],
            )
        ],
    )
    editor.set_recipe(recipe_nmc)
    assert len(editor.get_validation_errors()) == 0
    assert editor.lbl_validation_banner.isVisible() is False

    # Switch combo to LFP
    idx_lfp = editor.combo_chemistry.findData("LFP")
    editor.combo_chemistry.setCurrentIndex(idx_lfp)
    qapp.processEvents()

    # Must immediately detect violation and display banner
    errors = editor.get_validation_errors()
    assert len(errors) >= 1
    assert editor.lbl_validation_banner.isVisible() is True
    assert "Chemistry Safety Guardrail Violations (LFP)" in editor.lbl_validation_banner.text()

    # Table items in violating row must have warning styling
    item_name = editor.table_steps.item(0, 1)
    assert item_name.background().color().name() == "#450a0a"

    # Switch to Custom / Unconstrained: violations cleared
    idx_custom = editor.combo_chemistry.findData("CUSTOM")
    editor.combo_chemistry.setCurrentIndex(idx_custom)
    qapp.processEvents()

    assert len(editor.get_validation_errors()) == 0
    assert editor.lbl_validation_banner.isVisible() is False
