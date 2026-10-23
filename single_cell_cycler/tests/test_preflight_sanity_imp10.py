"""Unit tests for IMP-10: Automated Pre-Flight Hardware Sanity Handshake."""

import pytest

from single_cell_cycler.comm.packet_codec import BoardParamsTelemetry, CellDataTelemetry
from single_cell_cycler.core.preflight_checker import (
    CheckStatus,
    PreflightReport,
    PreflightSanityChecker,
)


def test_preflight_all_nominal_pass():
    """Verify nominal conditions pass 4/4 checks with green status."""
    checker = PreflightSanityChecker()
    cell_data = CellDataTelemetry(voltage=3.650, current=0.005, terminal_temp=24.5, body_temp=24.8)
    board_params = BoardParamsTelemetry(ambient_temp=24.2, charge_voltage=0.0, load_voltage=0.0)
    readbacks = {0x6000: 0x00, 0x6001: 0x00, 0x6002: 0x00, 0x6003: 0x00, 0x6004: 0x00}

    report = checker.evaluate(
        cell_data=cell_data,
        board_params=board_params,
        readbacks=readbacks,
        last_telemetry_age_s=0.15,
        cell_id=1,
    )

    assert report.passed is True
    assert report.has_warnings is False
    assert report.passed_count == 4
    assert report.failure_count == 0
    assert "4/4 Passed" in report.summary_text
    assert "#064e3b" in report.summary_badge_style


def test_preflight_detached_sense_lead_fails():
    """Verify 0.00V (disconnected Kelvin lead) triggers critical failure."""
    checker = PreflightSanityChecker()
    cell_data = CellDataTelemetry(voltage=0.020, current=0.000, terminal_temp=25.0, body_temp=25.0)
    board_params = BoardParamsTelemetry(ambient_temp=24.8, charge_voltage=0.0, load_voltage=0.0)
    readbacks = {0x6000: 0x00, 0x6002: 0x00, 0x6003: 0x00, 0x6004: 0x00}

    report = checker.evaluate(
        cell_data=cell_data,
        board_params=board_params,
        readbacks=readbacks,
        last_telemetry_age_s=0.2,
        cell_id=1,
    )

    assert report.passed is False
    assert report.failure_count >= 1
    critical_fails = report.get_critical_failures()
    assert any("Cell Sense Lead Voltage" in f.name for f in critical_fails)
    assert "#7f1d1d" in report.summary_badge_style


def test_preflight_thermistor_faults():
    """Verify open-circuit thermistor (0°C) or thermal disparity (>6°C) fails."""
    checker = PreflightSanityChecker()

    # Case 1: Open probe reading 0.0°C
    cell_data_open = CellDataTelemetry(voltage=3.700, current=0.000, terminal_temp=0.0, body_temp=26.0)
    report_open = checker.evaluate(
        cell_data=cell_data_open,
        board_params=None,
        readbacks={},
        last_telemetry_age_s=0.1,
    )
    assert report_open.passed is False
    assert any("Thermistor Parity" in f.name and f.status == CheckStatus.FAIL for f in report_open.checks)

    # Case 2: Severe temperature parity mismatch (terminal 38°C vs body 24°C = 14°C delta)
    cell_data_skew = CellDataTelemetry(voltage=3.700, current=0.000, terminal_temp=38.0, body_temp=24.0)
    report_skew = checker.evaluate(
        cell_data=cell_data_skew,
        board_params=None,
        readbacks={},
        last_telemetry_age_s=0.1,
    )
    assert report_skew.passed is False
    assert any("Thermistor Parity" in f.name and f.status == CheckStatus.FAIL for f in report_skew.checks)


def test_preflight_idle_leakage_and_active_mosfet():
    """Verify non-zero leakage current or active stage at idle fails."""
    checker = PreflightSanityChecker()

    # Case 1: Active leakage current (0.45A)
    cell_data_leak = CellDataTelemetry(voltage=3.650, current=-0.450, terminal_temp=25.0, body_temp=25.2)
    report_leak = checker.evaluate(
        cell_data=cell_data_leak,
        board_params=None,
        readbacks={},
        last_telemetry_age_s=0.2,
    )
    assert report_leak.passed is False
    assert any("MOSFET" in f.name and f.status == CheckStatus.FAIL for f in report_leak.checks)

    # Case 2: Control register unexpectedly energized at idle
    cell_data_zero = CellDataTelemetry(voltage=3.650, current=0.000, terminal_temp=25.0, body_temp=25.2)
    readbacks_energized = {0x6002: 0x01}  # Charge stage active
    report_energized = checker.evaluate(
        cell_data=cell_data_zero,
        board_params=None,
        readbacks=readbacks_energized,
        last_telemetry_age_s=0.2,
    )
    assert report_energized.passed is False
    assert any("MOSFET" in f.name and f.status == CheckStatus.FAIL for f in report_energized.checks)


def test_preflight_offline_or_stale_telemetry():
    """Verify offline link or stale packet age fails."""
    checker = PreflightSanityChecker()

    # Link None
    report_none = checker.evaluate(cell_data=None, board_params=None, readbacks={}, last_telemetry_age_s=None)
    assert report_none.passed is False
    assert report_none.failure_count == 4  # All checks fail when offline

    # Stale link (> 2.5s)
    cell_data = CellDataTelemetry(voltage=3.650, current=0.000, terminal_temp=25.0, body_temp=25.0)
    report_stale = checker.evaluate(cell_data=cell_data, board_params=None, readbacks={}, last_telemetry_age_s=3.2)
    assert report_stale.passed is False
    assert any("Telemetry Link" in f.name and f.status == CheckStatus.FAIL for f in report_stale.checks)
