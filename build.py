"""Build the Serial-MonitorApp .exe with PyInstaller and zip it for sharing.

Usage:
    python build.py              # clean + build + zip
    python build.py --no-clean   # build without wiping build/ and dist/
    python build.py --no-zip     # skip the zip step
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "Serial-MonitorApp.spec"
APP_NAME = "Serial-MonitorApp"
DIST_DIR = ROOT / "dist" / APP_NAME
BRANDING_DIR = ROOT / "branding"
BRANDING_PATTERNS = ("*.ico", "*.png")


def clean() -> None:
    for name in ("build", "dist"):
        target = ROOT / name
        if target.exists():
            print(f"[build] removing {target}")
            shutil.rmtree(target, ignore_errors=True)


def run_pyinstaller(extra_args: list[str]) -> int:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC), *extra_args]
    print(f"[build] running: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=ROOT)


def read_version() -> str:
    try:
        with (ROOT / "version.json").open("r", encoding="utf-8") as fp:
            return json.load(fp).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def copy_branding() -> int:
    """Copy branding/*.ico and *.png next to the exe (NOT into _internal/).

    PyInstaller's COLLECT puts `datas` into `_internal/`, but we want the
    logos at the exe root so installers, icon-overlay tools, and the runtime
    can find them with a flat path. Skips silently if branding/ is empty.
    """
    if not BRANDING_DIR.exists():
        print(f"[build] no branding dir at {BRANDING_DIR}; skipping logo copy")
        return 0
    files: list[Path] = []
    for pattern in BRANDING_PATTERNS:
        files.extend(BRANDING_DIR.glob(pattern))
    if not files:
        print(f"[build] {BRANDING_DIR} has no .ico/.png files; skipping logo copy")
        return 0
    for src in files:
        dst = DIST_DIR / src.name
        shutil.copy2(src, dst)
        print(f"[build] copied {src.name} -> {dst}")
    return len(files)


def make_zip() -> Path:
    """Zip dist/Serial-MonitorApp/ into dist/Serial-MonitorApp_<version>.zip.

    The archive contains a single top-level folder so extracting on the target
    machine gives Serial-MonitorApp/Serial-MonitorApp.exe alongside _internal/.
    """
    if not DIST_DIR.exists():
        raise FileNotFoundError(f"dist folder not found: {DIST_DIR}")

    version = read_version()
    zip_base = ROOT / "dist" / f"{APP_NAME}_{version}"
    zip_path = zip_base.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()

    print(f"[build] zipping {DIST_DIR} -> {zip_path}")
    shutil.make_archive(
        base_name=str(zip_base),
        format="zip",
        root_dir=str(DIST_DIR.parent),
        base_dir=DIST_DIR.name,
    )
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[build] zip ready: {zip_path} ({size_mb:.1f} MB)")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Serial-MonitorApp .exe")
    parser.add_argument("--no-clean", action="store_true", help="skip wiping build/ and dist/")
    parser.add_argument("--no-zip", action="store_true", help="skip the zip step")
    args, passthrough = parser.parse_known_args()

    if not SPEC.exists():
        print(f"[build] ERROR: spec file not found at {SPEC}", file=sys.stderr)
        return 1

    if not args.no_clean:
        clean()

    rc = run_pyinstaller(passthrough)
    if rc != 0:
        print(f"\n[build] FAILED with exit code {rc}", file=sys.stderr)
        return rc

    exe = DIST_DIR / f"{APP_NAME}.exe"
    print(f"\n[build] done. exe at: {exe}")

    copy_branding()

    if not args.no_zip:
        try:
            make_zip()
        except Exception as e:
            print(f"[build] zip step FAILED: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
