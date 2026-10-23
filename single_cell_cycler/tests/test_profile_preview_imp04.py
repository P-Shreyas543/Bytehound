"""Test suite for Pillar 1: IMP-04 (Visual Recipe Timeline Profile Preview).

Verifies:
1. RecipeTimelinePreview widget initialization and layout.
2. Multi-step voltage and current simulated trajectory generation.
3. Accurate step markers and step index text annotations.
4. Real-time preview synchronization when adding, editing, or reordering steps.
5. Loop step unrolling for visual confirmation.
"""

from __future__ import annotations

import os
import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.core.profile_model import (
    CutoffCondition,
    CutoffType,
    StepType,
    TestRecipe,
    TestStep,
)
from single_cell_cycler.ui.widgets.profile_editor import ProfileEditorWidget, RecipeTimelinePreview


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_preview_widget_generation(qapp):
    preview = RecipeTimelinePreview()
    preview.show()
    preview.resize(800, 200)
    qapp.processEvents()

    # 3-step cycle: Charge (1.5A, 100s) -> Rest (60s) -> Discharge (1.2A, 120s)
    recipe = TestRecipe(
        recipe_name="Standard 3-Stage Cycle",
        chemistry="NMC",
        steps=[
            TestStep(
                step_index=1,
                name="CC Charge",
                step_type=StepType.CHARGE,
                charge_current_1=True,
                charge_current_2=True,  # 1.5A
                max_charge_voltage=True, # 4.2V
                cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 100.0, True)],
            ),
            TestStep(
                step_index=2,
                name="OCV Rest",
                step_type=StepType.REST,
                cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 60.0, True)],
            ),
            TestStep(
                step_index=3,
                name="CC Discharge",
                step_type=StepType.DISCHARGE,
                discharge_load_2=True,
                discharge_load_3=True,  # 0.4 + 0.8 = 1.2A
                cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 120.0, True)],
            ),
        ],
    )

    preview.update_preview(recipe)
    qapp.processEvents()

    # Verify curves populated
    v_data = preview.curve_v.getData()
    i_data = preview.curve_i.getData()

    assert v_data[0] is not None and len(v_data[0]) > 0
    assert i_data[0] is not None and len(i_data[0]) > 0

    # Total simulated time = 100 + 60 + 120 = 280.0s
    total_t = v_data[0][-1]
    assert abs(total_t - 280.0) < 1.0

    # Step boundary lines (at t=100s and t=160s)
    assert len(preview.step_lines) == 2
    assert abs(preview.step_lines[0].value() - 100.0) < 0.1
    assert abs(preview.step_lines[1].value() - 160.0) < 0.1

    # Step text annotations (S1, S2, S3)
    assert len(preview.step_labels) == 3


def test_preview_loop_unrolling(qapp):
    preview = RecipeTimelinePreview()
    preview.show()
    preview.resize(800, 200)
    qapp.processEvents()

    # Recipe with Charge -> Rest -> Loop 2x back to Step 1
    recipe = TestRecipe(
        recipe_name="Loop Recipe",
        chemistry="NMC",
        steps=[
            TestStep(
                step_index=1,
                name="Charge",
                step_type=StepType.CHARGE,
                cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 50.0, True)],
            ),
            TestStep(
                step_index=2,
                name="Rest",
                step_type=StepType.REST,
                cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 50.0, True)],
            ),
            TestStep(
                step_index=3,
                name="Loop",
                step_type=StepType.LOOP,
                loop_target_step=1,
                loop_count=2,
            ),
        ],
    )

    preview.update_preview(recipe)
    qapp.processEvents()

    # Loop count 2 means 2 cycles of Charge + Rest = 4 unrolled steps in preview
    assert len(preview.step_labels) == 4
    total_t = preview.curve_v.getData()[0][-1]
    assert abs(total_t - 200.0) < 1.0


def test_profile_editor_preview_integration(qapp):
    editor = ProfileEditorWidget()
    editor.show()
    editor.resize(1000, 600)
    qapp.processEvents()

    assert hasattr(editor, "preview_widget")
    assert editor.preview_widget is not None

    # Load custom recipe
    recipe = TestRecipe(
        recipe_name="Integration Test",
        chemistry="LFP",
        steps=[
            TestStep(
                step_index=1,
                name="Step 1",
                step_type=StepType.CHARGE,
                max_charge_voltage=False, # 3.6V
                cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 60.0, True)],
            )
        ],
    )
    editor.set_recipe(recipe)
    qapp.processEvents()

    # Initial preview has 1 step
    assert len(editor.preview_widget.step_labels) == 1

    # Click Add Step
    editor.btn_add_step.click()
    qapp.processEvents()

    # Preview dynamically updated to 2 steps!
    assert len(editor.preview_widget.step_labels) == 2

    # Click Delete Step
    editor.table_steps.selectRow(1)
    editor.btn_del_step.click()
    qapp.processEvents()

    assert len(editor.preview_widget.step_labels) == 1
