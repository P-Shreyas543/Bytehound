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


def _clamp(value, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return default if v != v else min(hi, max(lo, v))   # NaN -> default


@dataclass
class ThermalSafetySettings:
    """Temperature protection, from the "safety" section of cycler_settings.json.

    Out-of-range values are clamped to safe bounds, not rejected: the absolute limit can be
    lowered but never raised above 80 °C.
    """

    rate_of_rise_enabled: bool = False      # dT/dt early-runaway trip (both probes must agree); off by
                                            # default since v1.3.1, switch on in the Safety tab
    rate_of_rise_c_per_min: float = 1.5     # trip threshold
    rate_window_s: float = 15.0             # slope fitted over this window
    rate_sustain_s: float = 2.5             # threshold must hold this long
    max_temp_c: float = 60.0                # absolute trip (hotter probe)
    warn_temp_c: float = 45.0               # warning alarm only

    def __post_init__(self) -> None:
        self.rate_of_rise_enabled = bool(self.rate_of_rise_enabled)
        self.rate_of_rise_c_per_min = _clamp(self.rate_of_rise_c_per_min, 0.5, 10.0, 1.5)
        self.rate_window_s = _clamp(self.rate_window_s, 5.0, 120.0, 15.0)
        self.rate_sustain_s = _clamp(self.rate_sustain_s, 0.5, 60.0, 2.5)
        self.max_temp_c = _clamp(self.max_temp_c, 30.0, 80.0, 60.0)
        self.warn_temp_c = _clamp(self.warn_temp_c, 20.0, self.max_temp_c, min(45.0, self.max_temp_c))


_SAFETY_KEYS = tuple(ThermalSafetySettings.__dataclass_fields__)


def _read_settings_file(path: Path) -> dict:
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_safety_settings(path: Path | None = None) -> ThermalSafetySettings:
    """Read the safety section; a missing section is added to the file with the defaults so
    operators can find and edit it (the logging section and anything else is kept)."""
    from dataclasses import asdict

    path = Path(path) if path is not None else SETTINGS_PATH
    data = _read_settings_file(path) if path.exists() else {}
    section = data.get("safety")
    if isinstance(section, dict):
        return ThermalSafetySettings(**{k: section[k] for k in _SAFETY_KEYS if k in section})
    settings = ThermalSafetySettings()
    try:
        save_safety_settings(settings, path)
    except Exception:
        pass
    return settings


def save_safety_settings(settings: ThermalSafetySettings, path: Path | None = None) -> None:
    """Write the safety section, keeping every other section of the file."""
    import json
    from dataclasses import asdict

    path = Path(path) if path is not None else SETTINGS_PATH
    data = _read_settings_file(path) if path.exists() else {}
    if "logging" not in data:
        data["logging"] = asdict(LoggingSettings())
    data["safety"] = asdict(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@dataclass
class CyclerAppConfig:
    default_port: str = "COM3"
    default_baud: int = 115200
    telemetry_ui_rate_fps: int = 25
    max_plot_points: int = 10000
    current_taper_arming_delay_s: float = 3.0
    nominal_cell_capacity_mah: float = 3000.0
