"""Configuration defaults and paths for Single-Cell BMS Cycler."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dataclasses import dataclass

def _resolve_log_dir() -> Path:
    """Return a guaranteed writable log directory across frozen and dev environments."""
    if getattr(sys, "frozen", False):
        # Running inside a PyInstaller frozen bundle (.exe)
        _LOCAL_APP_DATA = Path(
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        )
        base = _LOCAL_APP_DATA / "Bytehound" / "SingleCellCycler" / "logs"
    else:
        # Running directly from Python source code
        base = Path(__file__).resolve().parent.parent / "logs"

    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except Exception:
        fallback = Path.home() / ".bytehound" / "cycler" / "logs"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
        except Exception:
            return Path.cwd() / "logs"


DEFAULT_LOG_DIR = _resolve_log_dir()

if getattr(sys, "frozen", False):
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    CONFIG_DIR = _BUNDLE_ROOT / "single_cell_cycler" / "config"
else:
    CONFIG_DIR = Path(__file__).resolve().parent

RECIPES_DIR = CONFIG_DIR / "recipes"
try:
    RECIPES_DIR.mkdir(parents=True, exist_ok=True)
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
