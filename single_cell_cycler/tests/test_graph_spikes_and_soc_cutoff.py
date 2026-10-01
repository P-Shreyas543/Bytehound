"""Verification for recipe SoC cutoff configuration."""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.core.profile_model import CutoffCondition, CutoffType, StepType, TestStep
from single_cell_cycler.ui.widgets.profile_editor import StepHardwareDialog


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])
    return app


def test_step_hardware_dialog_soc_and_voltage_cutoff(qapp):
    """Verify that StepHardwareDialog enables setting SoC cutoffs directly like voltage cutoffs."""
    step = TestStep(
        step_index=1,
        name="CC Charge",
        step_type=StepType.CHARGE,
        cutoffs=[
            CutoffCondition(CutoffType.VOLTAGE_MAX, 4.20, True, "Upper voltage cutoff"),
        ],
    )

    dlg = StepHardwareDialog(step)

    # By default, detected initial mode is 'voltage'
    assert dlg.combo_cmode.currentData() == "voltage"
    assert dlg.spin_v_cut.value() == pytest.approx(4.20)

    # Change cutoff mode to SoC Cut-off (e.g. 80%)
    soc_idx = dlg.combo_cmode.findData("soc")
    dlg.combo_cmode.setCurrentIndex(soc_idx)
    dlg.spin_soc_cut.setValue(80.0)

    # Save setpoints
    dlg._save_and_accept()

    # The step's cutoffs must now have SOC_MAX = 80.0% enabled
    soc_cutoff = next((c for c in step.cutoffs if c.cutoff_type == CutoffType.SOC_MAX), None)
    assert soc_cutoff is not None
    assert soc_cutoff.threshold == pytest.approx(80.0)
    assert soc_cutoff.enabled is True

    # Now edit for Discharge step with both Voltage and SoC
    step_dis = TestStep(
        step_index=2,
        name="Discharge Step",
        step_type=StepType.DISCHARGE,
        cutoffs=[],
    )
    dlg2 = StepHardwareDialog(step_dis)
    both_idx = dlg2.combo_cmode.findData("both")
    dlg2.combo_cmode.setCurrentIndex(both_idx)
    dlg2.spin_v_cut.setValue(2.80)
    dlg2.spin_soc_cut.setValue(20.0)
    dlg2.chk_dur_cut.setChecked(True)
    dlg2.spin_dur_cut.setValue(7200)

    dlg2._save_and_accept()

    v_cut = next((c for c in step_dis.cutoffs if c.cutoff_type == CutoffType.VOLTAGE_MIN), None)
    soc_cut = next((c for c in step_dis.cutoffs if c.cutoff_type == CutoffType.SOC_MIN), None)
    dur_cut = next((c for c in step_dis.cutoffs if c.cutoff_type == CutoffType.DURATION_MAX), None)

    assert v_cut is not None and v_cut.threshold == pytest.approx(2.80)
    assert soc_cut is not None and soc_cut.threshold == pytest.approx(20.0)
    assert dur_cut is not None and dur_cut.threshold == pytest.approx(7200)
    dlg.close()
    dlg2.close()
