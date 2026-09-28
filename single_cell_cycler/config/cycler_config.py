"""Configuration defaults and paths for Single-Cell BMS Cycler."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

CONFIG_DIR = Path(__file__).resolve().parent
RECIPES_DIR = CONFIG_DIR / "recipes"
RECIPES_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LOG_DIR = CONFIG_DIR.parent / "logs"
DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class CyclerAppConfig:
    default_port: str = "COM3"
    default_baud: int = 115200
    telemetry_ui_rate_fps: int = 25
    max_plot_points: int = 10000
    current_taper_arming_delay_s: float = 3.0
    nominal_cell_capacity_mah: float = 3000.0
