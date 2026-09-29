"""Comprehensive MNC-grade tests for IMP-08: Power Loss / Crash Recovery & Atomic State Journaling."""

import os
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from single_cell_cycler.core.cycler_engine import CyclerEngine, EngineState
from single_cell_cycler.core.metrics_tracker import (
    CycleSummary,
    MetricsTracker,
    StepMetrics,
)
from single_cell_cycler.core.profile_model import (
    CutoffCondition,
    CutoffType,
    StepType,
    TestRecipe,
    TestStep,
)
from single_cell_cycler.core.state_journal import (
    StateJournalManager,
    TestJournalData,
    cycle_summary_from_dict,
    cycle_summary_to_dict,
    step_metrics_from_dict,
    step_metrics_to_dict,
)
from single_cell_cycler.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def tmp_journal_dir(tmp_path):
    j_dir = tmp_path / "logs"
    j_dir.mkdir(parents=True, exist_ok=True)
    return j_dir


def test_atomic_journal_write_and_read(tmp_journal_dir):
    mgr = StateJournalManager(journal_dir=tmp_journal_dir)
    assert not mgr.is_recovery_available()

    recipe = TestRecipe(
        recipe_name="NMC Qualification Profile",
        steps=[
            TestStep(step_index=1, name="CC Charge", step_type=StepType.CHARGE),
            TestStep(step_index=2, name="Rest OCV", step_type=StepType.REST),
            TestStep(step_index=3, name="CC Discharge", step_type=StepType.DISCHARGE),
        ],
    )

    sm = StepMetrics(
        cycle_index=1,
        step_index=1,
        step_name="CC Charge",
        step_type=StepType.CHARGE,
        start_time=1000.0,
        end_time=1300.0,
        duration_s=300.0,
        start_voltage=3.2,
        end_voltage=4.2,
        capacity_mah=1500.0,
        energy_mwh=5700.0,
        dcir_10s_mohm=14.8,
        cutoff_reason="4.20V Cutoff",
    )

    cs = CycleSummary(
        cycle_index=1,
        charge_capacity_mah=1500.0,
        discharge_capacity_mah=1490.0,
        coulombic_efficiency_pct=99.33,
        energy_efficiency_pct=93.5,
        dcir_10s_mohm=14.8,
    )

    journal = TestJournalData(
        version="1.0",
        active=True,
        timestamp=1000.0,
        recipe_name=recipe.recipe_name,
        recipe_dict=recipe.to_dict(),
        selected_cell=2,
        current_cycle=2,
        current_step_idx=1,
        step_name="Rest OCV",
        step_type="rest",
        loop_counters={"3": 5},
        cumulative_charge_mah=1500.0,
        cumulative_discharge_mah=1490.0,
        cumulative_charge_mwh=5700.0,
        cumulative_discharge_mwh=5300.0,
        total_test_start_time=1000.0,
        step_history=[step_metrics_to_dict(sm)],
        cycle_summaries=[cycle_summary_to_dict(cs)],
        csv_log_file="logs/test_run.csv",
    )

    # 1. Write journal atomically
    assert mgr.write_journal(journal)
    assert mgr.is_recovery_available()

    # 2. Read back journal and verify integrity
    loaded = mgr.read_journal()
    assert loaded is not None
    assert loaded.active is True
    assert loaded.recipe_name == "NMC Qualification Profile"
    assert loaded.selected_cell == 2
    assert loaded.current_cycle == 2
    assert loaded.current_step_idx == 1
    assert loaded.step_name == "Rest OCV"
    assert loaded.loop_counters == {"3": 5}
    assert loaded.cumulative_charge_mah == 1500.0
    assert len(loaded.step_history) == 1
    assert len(loaded.cycle_summaries) == 1

    restored_sm = step_metrics_from_dict(loaded.step_history[0])
    assert restored_sm.step_name == "CC Charge"
    assert restored_sm.capacity_mah == 1500.0
    assert restored_sm.dcir_10s_mohm == 14.8

    restored_cs = cycle_summary_from_dict(loaded.cycle_summaries[0])
    assert restored_cs.coulombic_efficiency_pct == 99.33

    # 3. Clear journal
    mgr.clear_journal()
    assert not mgr.is_recovery_available()
    assert mgr.read_journal() is None


def test_engine_crash_recovery_restoration(tmp_journal_dir):
    cmds_sent = []

    def mock_sender(f_type, d1, d2):
        cmds_sent.append((f_type, d1, d2))

    # Engine instance before crash
    engine = CyclerEngine(command_sender=mock_sender)
    engine.journal_manager = StateJournalManager(journal_dir=tmp_journal_dir)
    engine.selected_cell = 2

    recipe = TestRecipe(
        recipe_name="3-Step Qualification Test",
        steps=[
            TestStep(step_index=1, name="Step 1 Charge", step_type=StepType.CHARGE),
            TestStep(step_index=2, name="Step 2 Rest", step_type=StepType.REST),
            TestStep(step_index=3, name="Step 3 Discharge", step_type=StepType.DISCHARGE),
        ],
    )
    engine.load_recipe(recipe)
    engine.transition_controller.auto_ack = True
    engine.start_test()

    # Verify journal was created on start
    assert engine.journal_manager.is_recovery_available()

    # Complete Step 1 with a mock cutoff
    finished_step = engine.metrics_tracker.complete_step("Voltage Max Reached")
    engine.step_completed.emit(finished_step)
    engine.current_step_idx = 1
    engine._sync_journal()

    # Verify journal captures that Step 1 is completed and Step 2 is active
    journal_before_crash = engine.journal_manager.read_journal()
    assert journal_before_crash.current_step_idx == 1
    assert len(journal_before_crash.step_history) == 1

    # SIMULATE CRASH: Instantiate fresh CyclerEngine without previous in-memory state
    fresh_cmds = []
    resumed_engine = CyclerEngine(command_sender=lambda f, d1, d2: fresh_cmds.append((f, d1, d2)))
    resumed_engine.journal_manager = StateJournalManager(journal_dir=tmp_journal_dir)
    resumed_engine.transition_controller.auto_ack = True

    assert resumed_engine.journal_manager.is_recovery_available()
    journal = resumed_engine.journal_manager.read_journal()

    # Resume engine from journal
    resumed_engine.resume_from_journal(journal)

    # Verify state restored
    assert resumed_engine.selected_cell == 2
    assert resumed_engine.recipe.recipe_name == "3-Step Qualification Test"
    assert resumed_engine.current_step_idx == 1
    assert resumed_engine.active_step.name == "Step 2 Rest"
    assert len(resumed_engine.metrics_tracker.step_history) == 1
    assert resumed_engine.metrics_tracker.step_history[0].cutoff_reason == "Voltage Max Reached"
    assert resumed_engine.state in (EngineState.STEP_TRANSITION, EngineState.RUNNING)


def test_mainwindow_crash_recovery_integration(qapp, tmp_journal_dir):
    # Pre-populate an interrupted test journal
    mgr = StateJournalManager(journal_dir=tmp_journal_dir)
    recipe = TestRecipe(
        recipe_name="Crash Recovery UI Test",
        steps=[
            TestStep(step_index=1, name="Phase 1 Charge", step_type=StepType.CHARGE),
            TestStep(step_index=2, name="Phase 2 Discharge", step_type=StepType.DISCHARGE),
        ],
    )
    sm = StepMetrics(
        cycle_index=1,
        step_index=1,
        step_name="Phase 1 Charge",
        step_type=StepType.CHARGE,
        start_time=100.0,
        end_time=300.0,
        duration_s=200.0,
        capacity_mah=1200.0,
        energy_mwh=4500.0,
    )
    cs = CycleSummary(
        cycle_index=1,
        charge_capacity_mah=1200.0,
        discharge_capacity_mah=1190.0,
        coulombic_efficiency_pct=99.17,
        energy_efficiency_pct=92.5,
    )
    journal = TestJournalData(
        active=True,
        recipe_name=recipe.recipe_name,
        recipe_dict=recipe.to_dict(),
        selected_cell=2,
        current_cycle=1,
        current_step_idx=1,
        step_name="Phase 2 Discharge",
        step_type="discharge",
        cumulative_charge_mah=1200.0,
        step_history=[step_metrics_to_dict(sm)],
        cycle_summaries=[cycle_summary_to_dict(cs)],
    )
    mgr.write_journal(journal)

    # Initialize MainWindow with the journal directory
    window = MainWindow()
    window.engine.journal_manager = mgr
    window.engine.transition_controller.auto_ack = True

    # Test detection
    assert window.check_and_prompt_crash_recovery() is True

    # Test restoration
    success = window.restore_from_crash_journal(journal)
    assert success is True

    # Verify UI state restored:
    # 1. Active cell set to Cell 2
    assert window.engine.selected_cell == 2
    # 2. Recipe loaded in editor
    assert window.profile_editor.current_recipe.recipe_name == "Crash Recovery UI Test"
    # 3. Tracker table replayed completed step
    assert window.tracker_table.table.rowCount() >= 1
    # 4. Live plots replayed completed cycle
    assert len(window.live_plots._cycle_indices) == 1
    assert window.live_plots._cycle_q_dis[0] == 1190.0
    # 5. Engine is in transition or running step 2
    assert window.engine.current_step_idx == 1
    assert window.engine.active_step.name == "Phase 2 Discharge"

    window.close()
