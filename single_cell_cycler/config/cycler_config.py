"""Configuration defaults and paths for Single-Cell BMS Cycler."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dataclasses import dataclass

if getattr(sys, "frozen", False):
    # Running inside a PyInstaller frozen bundle (.exe)
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    CONFIG_DIR = _BUNDLE_ROOT / "single_cell_cycler" / "config"
    # Program Files is not writable for standard users; keep runtime data per-user.
    _LOCAL_APP_DATA = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    )
    DEFAULT_LOG_DIR = _LOCAL_APP_DATA / "Bytehound" / "SingleCellCycler" / "logs"
else:
    # Running directly from Python source code
    CONFIG_DIR = Path(__file__).resolve().parent
    DEFAULT_LOG_DIR = CONFIG_DIR.parent / "logs"

RECIPES_DIR = CONFIG_DIR / "recipes"
try:
    RECIPES_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

try:
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


@dataclass
class CyclerAppConfig:
    default_port: str = "COM3"
    default_baud: int = 115200
    telemetry_ui_rate_fps: int = 25
    max_plot_points: int = 10000
    current_taper_arming_delay_s: float = 3.0
    nominal_cell_capacity_mah: float = 3000.0
