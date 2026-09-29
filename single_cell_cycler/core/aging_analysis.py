"""Battery Aging, Degradation Trend Modeling, and End-of-Life (EOL) Forecasting.

Provides pure-NumPy regression models (linear and exponential decay) to forecast
capacity fade, Coulombic/Energy efficiency evolution, and 80% EOL cycle projection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class DegradationForecast:
    """Degradation trend model results and End-of-Life (EOL) projection."""
    model: str                                        # "linear" or "exponential"
    slope_mah_per_cycle: float = 0.0                 # Rate of capacity change (mAh/cycle)
    decay_pct_per_cycle: float = 0.0                 # Rate of capacity fade (%/cycle)
    current_retention_pct: float = 100.0             # Current capacity as % of initial
    q_initial_mah: float = 0.0                       # Baseline capacity (Cycle 1)
    q_latest_mah: float = 0.0                        # Most recent measured discharge capacity
    q_eol_mah: float = 0.0                           # 80.0% nominal EOL capacity cutoff
    projected_eol_cycle: Optional[int] = None        # Estimated cycle number reaching 80% EOL
    r_squared: float = 0.0                           # Coefficient of determination (0.0 to 1.0)
    proj_cycles: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    proj_capacities: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))


def fit_capacity_degradation(
    cycles: np.ndarray,
    capacities: np.ndarray,
    eol_fraction: float = 0.80,
    model: str = "linear",
    max_forecast_cycles: int = 3000,
) -> DegradationForecast:
    """Fit degradation model to capacity history and project 80% End-of-Life cycle.

    Parameters:
    -----------
    cycles : np.ndarray
        Array of integer or float cycle numbers [1, 2, ..., N].
    capacities : np.ndarray
        Delivered discharge capacity per cycle in mAh.
    eol_fraction : float
        Fraction of initial capacity defining End-of-Life (default 0.80 = 80%).
    model : str
        "linear" for Q(n) = a*n + b or "exponential" for Q(n) = Q0 * exp(-k*n).
    max_forecast_cycles : int
        Maximum cycle number bound for projection extrapolation.

    Returns:
    --------
    DegradationForecast
        Detailed forecast metrics and projected curve arrays.
    """
    c_arr = np.asarray(cycles, dtype=float)
    q_arr = np.asarray(capacities, dtype=float)

    mask = np.isfinite(c_arr) & np.isfinite(q_arr) & (q_arr > 0.0)
    c_valid = c_arr[mask]
    q_valid = q_arr[mask]

    n_pts = len(c_valid)
    if n_pts < 2:
        q_init = float(q_valid[0]) if n_pts == 1 else 0.0
        return DegradationForecast(
            model=model,
            current_retention_pct=100.0,
            q_initial_mah=round(q_init, 2),
            q_latest_mah=round(q_init, 2),
            q_eol_mah=round(q_init * eol_fraction, 2),
        )

    q_initial = float(q_valid[0])
    q_latest = float(q_valid[-1])
    retention_pct = (q_latest / q_initial * 100.0) if q_initial > 0 else 100.0
    q_eol = q_initial * eol_fraction

    # Design matrix [cycle, 1]
    a_mat = np.vstack([c_valid, np.ones(n_pts)]).T

    if model == "exponential":
        # log(Q) = -k*n + log(Q0)
        log_q = np.log(q_valid)
        slope, intercept = np.linalg.lstsq(a_mat, log_q, rcond=None)[0]
        q_pred = np.exp(slope * c_valid + intercept)
        slope_mah = float(slope * q_latest)
        decay_pct = float(abs(slope) * 100.0)

        # EOL Cycle: log(Q_eol) = slope * n_eol + intercept
        if slope < -1e-6:
            n_eol = int(round((np.log(q_eol) - intercept) / slope))
            n_eol = n_eol if n_eol > int(c_valid[-1]) else None
        else:
            n_eol = None
    else:
        # Linear: Q(n) = a*n + b
        slope, intercept = np.linalg.lstsq(a_mat, q_valid, rcond=None)[0]
        q_pred = slope * c_valid + intercept
        slope_mah = float(slope)
        decay_pct = float((abs(slope) / q_initial * 100.0)) if q_initial > 0 else 0.0

        # EOL Cycle: Q_eol = slope * n_eol + intercept
        if slope < -1e-5:
            n_eol = int(round((q_eol - intercept) / slope))
            n_eol = n_eol if n_eol > int(c_valid[-1]) else None
        else:
            n_eol = None

    # Calculate R-squared
    ss_tot = np.sum((q_valid - np.mean(q_valid)) ** 2)
    ss_res = np.sum((q_valid - q_pred) ** 2)
    r_squared = float(max(0.0, 1.0 - (ss_res / ss_tot))) if ss_tot > 0 else 1.0

    # Generate projection trajectory
    last_cyc = int(c_valid[-1])
    target_end_cyc = min(n_eol + 10 if n_eol else last_cyc + 30, max_forecast_cycles)
    if target_end_cyc > last_cyc:
        proj_cycles = np.arange(1, target_end_cyc + 1, dtype=float)
        if model == "exponential":
            proj_capacities = np.exp(slope * proj_cycles + intercept)
        else:
            proj_capacities = slope * proj_cycles + intercept
    else:
        proj_cycles = np.array([], dtype=float)
        proj_capacities = np.array([], dtype=float)

    return DegradationForecast(
        model=model,
        slope_mah_per_cycle=round(slope_mah, 3),
        decay_pct_per_cycle=round(decay_pct, 4),
        current_retention_pct=round(retention_pct, 2),
        q_initial_mah=round(q_initial, 2),
        q_latest_mah=round(q_latest, 2),
        q_eol_mah=round(q_eol, 2),
        projected_eol_cycle=n_eol,
        r_squared=round(r_squared, 4),
        proj_cycles=proj_cycles,
        proj_capacities=proj_capacities,
    )
