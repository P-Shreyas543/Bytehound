"""Unit tests for IMP-09: Rate-of-Rise Thermal Trigger Early Warning (dT/dt)."""

import pytest

from single_cell_cycler.comm.packet_codec import CellDataTelemetry
from single_cell_cycler.comm.protocol_defs import (
    FRAME_CHARGE_CTRL,
    FRAME_DISCHARGE_CTRL,
    FRAME_RELAY_CTRL,
)
from single_cell_cycler.core.safety_monitor import SafetyLimits, SafetyMonitor


def test_steady_high_temperature_does_not_trip_rate_of_rise():
    cmds = []
    monitor = SafetyMonitor(
        command_sender=lambda f, d, p: cmds.append((f, d, p)),
        limits=SafetyLimits(max_temp_c=60.0, max_temp_rate_of_rise_c_per_min=1.5),
    )

    # 15 seconds of steady 45.0 °C (below 60.0 °C max limit)
    for i in range(150):
        t = 1000.0 + i * 0.1
        data = CellDataTelemetry(
            timestamp=t,
            voltage=3.7,
            current=1.0,
            terminal_temp=45.0,
            body_temp=45.0,
        )
        assert monitor.check_telemetry(data) is True

    assert not monitor.is_tripped
    assert abs(monitor.last_rate_of_rise_c_per_min) < 1e-3


def test_small_sensor_noise_does_not_false_trip():
    cmds = []
    monitor = SafetyMonitor(
        command_sender=lambda f, d, p: cmds.append((f, d, p)),
        limits=SafetyLimits(max_temp_c=60.0, max_temp_rate_of_rise_c_per_min=1.5),
    )

    # Alternating +-0.15 °C sensor noise around 25.0 °C
    for i in range(150):
        t = 1000.0 + i * 0.1
        noise = 0.15 if (i % 2 == 0) else -0.15
        data = CellDataTelemetry(
            timestamp=t,
            voltage=3.7,
            current=1.0,
            terminal_temp=25.0 + noise,
            body_temp=25.0 + noise,
        )
        assert monitor.check_telemetry(data) is True

    assert not monitor.is_tripped


def test_thermal_runaway_ramp_triggers_emergency_shutdown():
    cmds = []
    monitor = SafetyMonitor(
        command_sender=lambda f, d, p: cmds.append((f, d, p)),
        limits=SafetyLimits(
            max_temp_c=60.0,
            max_temp_rate_of_rise_c_per_min=1.5,
            temp_rate_window_s=10.0,
            temp_rate_sustain_s=2.5,
        ),
    )

    # Synthetic thermal runaway ramp: +3.0 °C/min = +0.05 °C/s
    # Base temp 25.0 °C -> after 10s: 25.5 °C (rate = 3.0 °C/min)
    # After sustain time (12.5s): triggers trip!
    tripped_at_step = None
    for i in range(160):  # 16 seconds at 10 Hz
        t = 1000.0 + i * 0.1
        temp = 25.0 + (i * 0.1) * 0.05
        data = CellDataTelemetry(
            timestamp=t,
            voltage=3.8,
            current=1.5,
            terminal_temp=temp,
            body_temp=temp,
        )
        safe = monitor.check_telemetry(data)
        if not safe:
            tripped_at_step = i
            break

    assert tripped_at_step is not None
    assert monitor.is_tripped is True
    assert "Rate of temperature rise exceeded limit" in monitor.trip_reason
    assert "3.00 °C/min" in monitor.trip_reason

    # Verify priority 0 shutdown frames were dispatched
    frame_ids = [c[0] for c in cmds]
    assert FRAME_CHARGE_CTRL in frame_ids
    assert FRAME_DISCHARGE_CTRL in frame_ids
    assert FRAME_RELAY_CTRL in frame_ids
    for c in cmds:
        assert c[2] == 0  # Priority 0 (highest emergency priority)


def test_reset_safety_clears_rate_of_rise_state():
    cmds = []
    monitor = SafetyMonitor(command_sender=lambda f, d, p: cmds.append((f, d, p)))

    # Force trip
    monitor._trigger_shutdown("Test Trip")
    assert monitor.is_tripped is True

    # Reset
    monitor.reset_safety()
    assert monitor.is_tripped is False
    assert monitor.trip_reason == ""
    assert len(monitor._temp_history) == 0
    assert monitor.last_rate_of_rise_c_per_min == 0.0
