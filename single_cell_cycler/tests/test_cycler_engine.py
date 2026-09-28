"""End-to-end simulated test recipe execution tests."""

import time
from single_cell_cycler.comm.packet_codec import CellDataTelemetry
from single_cell_cycler.comm.protocol_defs import ALL_CONTROL_FRAMES
from single_cell_cycler.core.cycler_engine import CyclerEngine, EngineState
from single_cell_cycler.core.profile_model import CutoffCondition, CutoffType, StepType, TestRecipe, TestStep


def test_recipe_sequencing_and_looping():
    commands = []

    def mock_sender(fid, payload, prio):
        commands.append((fid, payload, prio))

    engine = CyclerEngine(command_sender=mock_sender)

    # Fast recipe:
    # Step 1: Charge (cutoff at 4.00V)
    # Step 2: Rest (cutoff at duration >= 2s)
    # Step 3: Loop back to Step 1 for 2 cycles
    recipe = TestRecipe(
        recipe_name="Test Cycle Loop",
        steps=[
            TestStep(
                step_index=1,
                name="Charge to 4.00V",
                step_type=StepType.CHARGE,
                cutoffs=[CutoffCondition(CutoffType.VOLTAGE_MAX, 4.00, True)],
            ),
            TestStep(
                step_index=2,
                name="Rest 2s",
                step_type=StepType.REST,
                cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 2.0, True)],
            ),
            TestStep(
                step_index=3,
                name="Loop 2x",
                step_type=StepType.LOOP,
                loop_target_step=1,
                loop_count=2,
            ),
        ],
    )

    engine.load_recipe(recipe)
    assert engine.state == EngineState.IDLE

    # Start test
    engine.start_test()
    assert engine.state == EngineState.RUNNING
    assert engine.active_step.name == "Charge to 4.00V"
    assert engine.current_cycle == 1

    # Feed telemetry below cutoff
    t = 1000.0
    engine.on_cell_telemetry(CellDataTelemetry(3.80, 1.5, 25.0, 25.0, timestamp=t))
    assert engine.state == EngineState.RUNNING
    assert engine.active_step.step_type == StepType.CHARGE

    # Reach 4.00V cutoff
    t += 0.5
    engine.on_cell_telemetry(CellDataTelemetry(4.005, 1.5, 25.0, 25.0, timestamp=t))

    # Should transition to Step 2 (Rest)
    assert engine.active_step.name == "Rest 2s"
    assert engine.active_step.step_type == StepType.REST

    # Advance Rest step time by 2.1s
    t += 2.1
    engine.on_cell_telemetry(CellDataTelemetry(3.99, 0.0, 25.0, 25.0, timestamp=t))

    # Now it hits Step 3 (LOOP), which decrements loop count and jumps back to Step 1 (Cycle 2)
    assert engine.current_cycle == 2
    assert engine.active_step.name == "Charge to 4.00V"

    # Cycle 2 Charge cutoff
    t += 0.5
    engine.on_cell_telemetry(CellDataTelemetry(4.01, 1.5, 25.0, 25.0, timestamp=t))
    assert engine.active_step.name == "Rest 2s"

    # Cycle 2 Rest cutoff
    t += 2.1
    engine.on_cell_telemetry(CellDataTelemetry(3.99, 0.0, 25.0, 25.0, timestamp=t))

    # All loops done -> Test completed!
    assert engine.state == EngineState.COMPLETED
    assert len(engine.metrics_tracker.step_history) == 4
    assert len(engine.metrics_tracker.cycle_summaries) == 2


def test_all_controls_zeroed_on_stop_and_pause_and_trip():
    commands = []

    def mock_sender(fid, payload, prio):
        commands.append((fid, payload, prio))

    engine = CyclerEngine(command_sender=mock_sender)
    recipe = TestRecipe(
        recipe_name="Single Step Test",
        steps=[
            TestStep(
                step_index=1,
                name="Charge Step",
                step_type=StepType.CHARGE,
                cutoffs=[CutoffCondition(CutoffType.DURATION_MAX, 10.0, True)],
            ),
        ],
    )
    engine.load_recipe(recipe)

    # 1. Test Pause zeroes all controls
    commands.clear()
    engine.start_test()
    commands.clear()
    engine.pause_test()
    assert engine.state == EngineState.PAUSED
    for frame_id in ALL_CONTROL_FRAMES:
        assert (frame_id, 0x00, 0) in commands

    # 2. Test Stop zeroes all controls
    commands.clear()
    engine.resume_test()
    commands.clear()
    engine.stop_test()
    assert engine.state == EngineState.ABORTED
    for frame_id in ALL_CONTROL_FRAMES:
        assert (frame_id, 0x00, 0) in commands

    # 3. Test Emergency Stop zeroes all controls
    commands.clear()
    engine.start_test()
    commands.clear()
    engine.emergency_stop()
    assert engine.state == EngineState.SAFETY_STOP
    for frame_id in ALL_CONTROL_FRAMES:
        assert (frame_id, 0x00, 0) in commands

    # 4. Test Safety Trip (overvoltage) zeroes all controls
    engine.safety_monitor.reset_safety()
    engine.load_recipe(recipe)
    commands.clear()
    engine.start_test()
    commands.clear()
    # Send telemetry that triggers safety trip (4.28V > 4.25V limit)
    engine.on_cell_telemetry(CellDataTelemetry(4.28, 1.0, 25.0, 25.0, timestamp=time.time()))
    assert engine.state == EngineState.SAFETY_STOP
    for frame_id in ALL_CONTROL_FRAMES:
        assert (frame_id, 0x00, 0) in commands

