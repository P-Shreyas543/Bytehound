"""Build the Serial-MonitorApp .exe with PyInstaller and zip it for sharing.

Usage:
    python build.py              # clean + build + zip
    python build.py --no-clean   # build without wiping build/ and dist/
    python build.py --no-zip     # skip the zip step
"""

from __future__ import annotations

import argparse
import hashlib
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


def write_sha256(exe: Path) -> str:
    """Compute SHA-256 of the built exe and write it into version.json."""
    print(f"[build] computing SHA-256 for {exe.name} ...")
    h = hashlib.sha256()
    with exe.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()

    vpath = ROOT / "version.json"
    try:
        with vpath.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        data["sha256"] = digest
        with vpath.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=4)
        print(f"[build] sha256 written to version.json: {digest}")
    except Exception as exc:
        print(f"[build] WARNING: could not update version.json sha256: {exc}")
    return digest


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
    """Zip dist/Serial-MonitorApp/ into dist/Serial-MonitorApp_<version>.zip."""
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


def run_inno_setup() -> int:
    """Compile installer.iss with Inno Setup (ISCC.exe) if available."""
    iss = ROOT / "installer.iss"
    if not iss.exists():
        print("[build] installer.iss not found; skipping installer step")
        return 0

    # Common Inno Setup install locations
    iscc_candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
    ]
    iscc = next((p for p in iscc_candidates if p.exists()), None)
    if iscc is None:
        print("[build] WARNING: Inno Setup not found. Skipping .exe installer creation.")
        print("[build]   Install from https://jrsoftware.org/isinfo.php then re-run.")
        return 0

    out_dir = ROOT / "installer_output"
    out_dir.mkdir(exist_ok=True)
    cmd = [str(iscc), str(iss)]
    print(f"[build] running Inno Setup: {' '.join(cmd)}")
    rc = subprocess.call(cmd, cwd=ROOT)
    if rc == 0:
        version = read_version()
        installer = out_dir / f"SerialMonitor_Setup_{version}.exe"
        if installer.exists():
            size_mb = installer.stat().st_size / (1024 * 1024)
            print(f"[build] installer ready: {installer}  ({size_mb:.1f} MB)")
        else:
            print(f"[build] installer built in {out_dir}/")
    else:
        print(f"[build] Inno Setup FAILED with exit code {rc}", file=sys.stderr)
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Serial-MonitorApp .exe")
    parser.add_argument("--no-clean",     action="store_true", help="skip wiping build/ and dist/")
    parser.add_argument("--no-zip",       action="store_true", help="skip the zip step")
    parser.add_argument("--no-installer", action="store_true", help="skip Inno Setup installer step")
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
    if not exe.exists():
        print(f"[build] ERROR: expected exe not found at {exe}", file=sys.stderr)
        return 1

    print(f"\n[build] done. exe at: {exe}")

    copy_branding()
    write_sha256(exe)   # auto-updates version.json sha256

    if not args.no_installer:
        run_inno_setup()

    if not args.no_zip:
        try:
            make_zip()
        except Exception as e:
            print(f"[build] zip step FAILED: {e}", file=sys.stderr)
            return 1

    version = read_version()
    print(f"""
[build] ── Release checklist ───────────────────────────────────────
  1. Commit & push version.json  (sha256 auto-updated above)
  2. git tag v{version} && git push origin v{version}
  3. Create GitHub Release v{version} and upload:
       dist/{APP_NAME}_{version}.zip
  4. Update installer_url in version.json to the release asset URL
  5. Commit & push version.json again
─────────────────────────────────────────────────────────────────────
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
