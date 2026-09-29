"""Automated test suite for Battery Aging, Degradation Trend Modeling, and EOL Forecasting - IMP-07."""

import numpy as np
import pytest

from single_cell_cycler.core.aging_analysis import (
    DegradationForecast,
    fit_capacity_degradation,
)


def test_linear_degradation_fit():
    """Verify linear degradation model and EOL calculation against known parameters."""
    # Synthetic cell: Q_0 = 2000 mAh, decay = 1.0 mAh/cycle
    # 80% EOL target: 1600 mAh -> should be reached at cycle 400
    cycles = np.arange(1, 51)
    capacities = 2000.0 - 1.0 * cycles

    forecast = fit_capacity_degradation(cycles, capacities, eol_fraction=0.80, model="linear")

    assert forecast.model == "linear"
    assert np.isclose(forecast.slope_mah_per_cycle, -1.0, atol=0.01)
    assert np.isclose(forecast.q_initial_mah, 1999.0, atol=1.0)
    assert forecast.projected_eol_cycle in (400, 401)
    assert np.isclose(forecast.r_squared, 1.0, atol=1e-4)
    assert len(forecast.proj_cycles) > 50


def test_exponential_degradation_fit():
    """Verify exponential degradation model fitting."""
    cycles = np.arange(1, 31)
    q0 = 3000.0
    k = 0.0005  # -0.05% per cycle
    capacities = q0 * np.exp(-k * cycles)

    forecast = fit_capacity_degradation(cycles, capacities, eol_fraction=0.80, model="exponential")

    assert forecast.model == "exponential"
    assert forecast.projected_eol_cycle is not None
    # ln(0.80) / (-0.0005) = -0.22314 / -0.0005 = ~446 cycles
    assert 440 <= forecast.projected_eol_cycle <= 455
    assert np.isclose(forecast.r_squared, 1.0, atol=1e-3)


def test_aging_fit_edge_cases():
    """Verify robust handling of small datasets and zero/positive slope."""
    # Empty
    f_empty = fit_capacity_degradation(np.array([]), np.array([]))
    assert f_empty.projected_eol_cycle is None

    # Single point
    f_single = fit_capacity_degradation(np.array([1]), np.array([2500.0]))
    assert f_single.projected_eol_cycle is None
    assert f_single.current_retention_pct == 100.0

    # Capacity increasing (e.g. early formation / wetting phase)
    cycles = np.arange(1, 6)
    caps_inc = np.array([2000.0, 2010.0, 2015.0, 2018.0, 2020.0])
    f_inc = fit_capacity_degradation(cycles, caps_inc)
    assert f_inc.slope_mah_per_cycle > 0
    # No EOL projected when slope is positive
    assert f_inc.projected_eol_cycle is None
