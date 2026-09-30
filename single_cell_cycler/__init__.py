"""Bytehound Single-Cell BMS Cycler & Characterization Workstation."""

import json
from pathlib import Path

__version__ = "1.2.3"


def get_version_manifest() -> dict:
    """Return the structured version control and release manifest."""
    manifest_path = Path(__file__).resolve().parent / "version.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": __version__}
