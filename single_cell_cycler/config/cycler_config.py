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


def _resolve_settings_path() -> Path:
    """Operator-editable application settings.

    Installed app: %LOCALAPPDATA%\\Bytehound\\SingleCellCycler\\cycler_settings.json (the install
    folder is read-only). Source tree: config/cycler_settings.json.
    """
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Bytehound" / "SingleCellCycler" / "cycler_settings.json"
    return Path(__file__).resolve().parent / "cycler_settings.json"


SETTINGS_PATH = _resolve_settings_path()

LOG_THREAD_PRIORITIES = ("normal", "above_normal", "highest", "time_critical")


@dataclass
class LoggingSettings:
    """Telemetry CSV logging, from the "logging" section of cycler_settings.json."""

    interval_s: float = 0.1                 # one CSV row every interval, on a fixed clock
    thread_priority: str = "above_normal"   # one of LOG_THREAD_PRIORITIES
    soc_decimals: int = 2                   # decimals written for the SoC columns

    def __post_init__(self) -> None:
        try:
            self.interval_s = min(60.0, max(0.02, float(self.interval_s)))
        except (TypeError, ValueError):
            self.interval_s = 0.1
        if self.thread_priority not in LOG_THREAD_PRIORITIES:
            self.thread_priority = "above_normal"
        try:
            self.soc_decimals = min(6, max(0, int(self.soc_decimals)))
        except (TypeError, ValueError):
            self.soc_decimals = 2


def load_logging_settings(path: Path | None = None) -> LoggingSettings:
    """Read the logging settings; a missing file is created with the defaults, bad values fall back."""
    import json
    from dataclasses import asdict

    path = Path(path) if path is not None else SETTINGS_PATH   # resolved at call time
    try:
        if path.exists():
            section = json.loads(path.read_text(encoding="utf-8-sig")).get("logging", {})
            known = {k: section[k] for k in ("interval_s", "thread_priority", "soc_decimals") if k in section}
            return LoggingSettings(**known)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"logging": asdict(LoggingSettings())}, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass
    return LoggingSettings()


@dataclass
class CyclerAppConfig:
    default_port: str = "COM3"
    default_baud: int = 115200
    telemetry_ui_rate_fps: int = 25
    max_plot_points: int = 10000
    current_taper_arming_delay_s: float = 3.0
    nominal_cell_capacity_mah: float = 3000.0
