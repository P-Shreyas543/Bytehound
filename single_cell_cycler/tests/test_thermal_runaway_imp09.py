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


def _feed(monitor, temps, gaps=None, start=1000.0, dt=0.1):
    """Feed one 10 Hz temperature series; returns the time of the first trip, or None."""
    t = start
    for i, temp in enumerate(temps):
        t += dt + (gaps or {}).get(i, 0.0)
        data = CellDataTelemetry(timestamp=t, voltage=3.7, current=1.0, terminal_temp=temp, body_temp=temp)
        if not monitor.check_telemetry(data):
            return t - start
    return None


def test_settling_readings_right_after_connect_do_not_trip():
    """15-cycle run, 2026-10-01: 24 s after connecting, an idle cell 'rose' 7.1 °C/min. The old
    check compared two samples after only 5 s; the first readings settle by ~0.6 °C."""
    monitor = SafetyMonitor(command_sender=lambda f, d, p: None)
    temps = [min(27.0, 26.4 + i * 0.1 * 0.12) for i in range(400)]   # 26.4 -> 27.0 over 5 s, then steady
    assert _feed(monitor, temps) is None


def test_single_outlier_and_reconnect_gap_do_not_trip():
    monitor = SafetyMonitor(command_sender=lambda f, d, p: None)
    assert _feed(monitor, [27.6 if i == 100 else 27.0 for i in range(400)]) is None

    monitor = SafetyMonitor(command_sender=lambda f, d, p: None)
    # 3 s telemetry gap (reconnect) with readings 0.6 °C higher afterwards
    assert _feed(monitor, [27.0 if i < 150 else 27.6 for i in range(400)], gaps={150: 3.0}) is None


def test_rate_check_waits_for_a_full_window_and_still_catches_a_slow_runaway():
    monitor = SafetyMonitor(command_sender=lambda f, d, p: None)          # default 15 s window
    tripped_at = _feed(monitor, [25.0 + i * 0.1 * 1.6 / 60 for i in range(600)])   # 1.6 °C/min
    assert tripped_at is not None and 15.0 + 2.5 <= tripped_at < 18.0
    assert "1.60 °C/min" in monitor.trip_reason


def _feed_probes(monitor, samples, start=1000.0, dt=0.1):
    """samples: (terminal, body) pairs; returns the first sample index that tripped, else None."""
    for i, (term, body) in enumerate(samples):
        data = CellDataTelemetry(timestamp=start + i * dt, voltage=3.7, current=1.0,
                                 terminal_temp=term, body_temp=body)
        if not monitor.check_telemetry(data):
            return i
    return None


def test_one_glitching_probe_does_not_trip():
    # Field data (2026-10-01): at steady current the terminal probe flipped between 26.6 and
    # 27.5 °C every few samples while the body probe held 26.4-26.5 °C
    import random
    rng = random.Random(7)
    level = 26.6
    samples = []
    for _ in range(1800):
        if rng.random() < 0.3:
            level = 27.5 if level == 26.6 else 26.6
        samples.append((level, 26.4 + rng.choice((0.0, 0.1))))
    # Dwell longer on the high level for 15 s: on its own this fits several °C/min
    samples += [(27.5, 26.4)] * 150
    monitor = SafetyMonitor(command_sender=lambda *a: None, limits=SafetyLimits(max_temp_c=60.0))
    assert _feed_probes(monitor, samples) is None
    assert not monitor.is_tripped


def test_runaway_seen_by_both_probes_trips_despite_glitches():
    monitor = SafetyMonitor(command_sender=lambda *a: None, limits=SafetyLimits(max_temp_c=60.0))
    samples = []
    temp = 30.0
    for i in range(600):
        temp += 3.0 / 600.0                                  # 3 °C/min real heating
        glitch = 0.9 if (i // 37) % 2 else 0.0               # terminal flips on top
        samples.append((temp + glitch, temp - 0.3))
    tripped_at = _feed_probes(monitor, samples)
    assert tripped_at is not None and tripped_at * 0.1 < 25.0
    assert monitor.trip_kind == "thermal"
