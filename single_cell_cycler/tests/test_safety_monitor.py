"""Unit tests for safety monitoring, BMS fault detection, and emergency shutoff."""

from single_cell_cycler.comm.packet_codec import CellDataTelemetry, FaultSoCTelemetry
from single_cell_cycler.comm.protocol_defs import (
    ALL_CONTROL_FRAMES,
    BMSFaultFlags,
    FRAME_CHARGE_CTRL,
    FRAME_CHARGE_SEL,
    FRAME_DISCHARGE_CTRL,
    FRAME_DISCHARGE_SEL,
    FRAME_RELAY_CTRL,
)
from single_cell_cycler.core.safety_monitor import SafetyLimits, SafetyMonitor


def test_bms_fault_detection():
    dispatched_commands = []

    def mock_sender(fid, payload, prio):
        dispatched_commands.append((fid, payload, prio))

    monitor = SafetyMonitor(command_sender=mock_sender)

    # 1. Normal telemetry
    ok_fault = FaultSoCTelemetry(
        fault_byte=0,
        cov=False, cuv=False, occ=False, ocd=False, cot=False, cut=False,
        soc_ocv=50.0, soc_cc=50.0,
    )
    assert monitor.check_bms_faults(ok_fault) is True
    assert not monitor.is_tripped

    # 2. Hardware COT (Over Temperature) fault occurs
    cot_fault = FaultSoCTelemetry(
        fault_byte=BMSFaultFlags.COT,
        cov=False, cuv=False, occ=False, ocd=False, cot=True, cut=False,
        soc_ocv=50.0, soc_cc=50.0,
    )
    assert monitor.check_bms_faults(cot_fault) is False
    assert monitor.is_tripped is True
    assert "Cell Over Temperature" in monitor.trip_reason

    # Verify that all 5 emergency commands (Priority 0) were dispatched immediately:
    # 0x6002 = 0, 0x6003 = 0, 0x6001 = 0, 0x6004 = 0, 0x6000 = 0
    assert (FRAME_CHARGE_CTRL, 0x00, 0) in dispatched_commands
    assert (FRAME_DISCHARGE_CTRL, 0x00, 0) in dispatched_commands
    assert (FRAME_CHARGE_SEL, 0x00, 0) in dispatched_commands
    assert (FRAME_DISCHARGE_SEL, 0x00, 0) in dispatched_commands
    assert (FRAME_RELAY_CTRL, 0x00, 0) in dispatched_commands
    assert len(dispatched_commands) == 5


def test_software_overvoltage_guardrail():
    dispatched_commands = []
    monitor = SafetyMonitor(
        command_sender=lambda f, p, prio: dispatched_commands.append((f, p, prio)),
        limits=SafetyLimits(max_voltage_v=4.250),
    )

    # Voltage exceeds 4.250V limit
    assert monitor.check_telemetry(CellDataTelemetry(4.280, 1.0, 25.0, 25.0)) is False
    assert monitor.is_tripped is True
    assert "exceeded safety limit" in monitor.trip_reason
    assert len(dispatched_commands) == 5
    for frame_id in ALL_CONTROL_FRAMES:
        assert (frame_id, 0x00, 0) in dispatched_commands


def test_manual_emergency_stop():
    dispatched_commands = []
    monitor = SafetyMonitor(
        command_sender=lambda f, p, prio: dispatched_commands.append((f, p, prio))
    )
    monitor.emergency_stop()
    assert monitor.is_tripped is True
    assert "MANUAL EMERGENCY STOP" in monitor.trip_reason
    assert len(dispatched_commands) == 5
    for frame_id in ALL_CONTROL_FRAMES:
        assert (frame_id, 0x00, 0) in dispatched_commands


def test_transition_and_rest_comparator_immunity():
    dispatched_commands = []
    monitor = SafetyMonitor(
        command_sender=lambda f, p, prio: dispatched_commands.append((f, p, prio))
    )

    occ_fault = FaultSoCTelemetry(
        fault_byte=BMSFaultFlags.OCC,
        cov=False, cuv=False, occ=True, ocd=False, cot=False, cut=False,
        soc_ocv=50.0, soc_cc=50.0,
    )

    # 1. During step transition, OCC comparator flag must NOT trip safety or dispatch shutdown
    assert monitor.check_bms_faults(occ_fault, is_transitioning=True) is True
    assert not monitor.is_tripped
    assert len(dispatched_commands) == 0

    # 2. During Rest step, OCC/OCD flags must NOT trip safety or dispatch shutdown
    assert monitor.check_bms_faults(occ_fault, active_step_type="Rest", is_transitioning=False) is True
    assert not monitor.is_tripped
    assert len(dispatched_commands) == 0

    # 3. But real thermal runaway (COT) during transition MUST trip safety
    cot_fault = FaultSoCTelemetry(
        fault_byte=BMSFaultFlags.COT,
        cov=False, cuv=False, occ=False, ocd=False, cot=True, cut=False,
        soc_ocv=50.0, soc_cc=50.0,
    )
    assert monitor.check_bms_faults(cot_fault, is_transitioning=True) is False
    assert monitor.is_tripped is True
    assert "Cell Over Temperature" in monitor.trip_reason
    assert len(dispatched_commands) == 5

