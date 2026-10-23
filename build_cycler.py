"""Root convenience entry point for building Single-Cell BMS Cycler."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD_SCRIPT = ROOT / "single_cell_cycler" / "build.py"

if __name__ == "__main__":
    cmd = [sys.executable, str(BUILD_SCRIPT), *sys.argv[1:]]
    sys.exit(subprocess.call(cmd, cwd=ROOT))
