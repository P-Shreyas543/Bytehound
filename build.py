"""Build the Bytehound .exe with PyInstaller and zip it for sharing.

Usage:
    python build.py              # clean + build + zip
    python build.py --no-clean   # build without wiping build/ and dist/
    python build.py --no-zip     # skip the zip step

Code signing (opt-in): set SIGN_PFX and SIGN_PASSWORD env vars before running
to sign the inner .exe and the Inno Setup installer. Requires signtool.exe in
the Windows SDK (see tools/sign.ps1 for details).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "Bytehound.spec"
APP_NAME = "Bytehound"
DIST_DIR = ROOT / "dist" / APP_NAME
BRANDING_DIR = ROOT / "branding"
BRANDING_PATTERNS = ("*.ico", "*.png")
SIGN_SCRIPT = ROOT / "tools" / "sign.ps1"


def clean() -> None:
    import stat
    def remove_readonly(func, path, excinfo):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    for name in ("build", "dist"):
        target = ROOT / name
        if target.exists():
            print(f"[build] removing {target}")
            shutil.rmtree(target, onerror=remove_readonly)


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


def read_version_manifest() -> dict:
    """Load the full version.json manifest (version, Developer, etc.)."""
    try:
        with (ROOT / "version.json").open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {}


def write_installer_version_iss() -> Path:
    """Mirror version.json into installer_version.iss for Inno Setup.

    version.json is the single source of truth. The Inno Setup .iss script
    can't parse JSON on its own, so we generate a tiny include file with
    `#define`s before invoking ISCC. The file is gitignored — re-run
    `python build.py` (or just import-and-call this) after any version.json
    edit and the installer picks up the change.
    """
    manifest = read_version_manifest()
    version = str(manifest.get("version", "0.0.0"))
    developer = str(manifest.get("Developer", "")).replace('"', '\\"')
    out = ROOT / "installer_version.iss"
    out.write_text(
        "; Auto-generated from version.json by build.py - DO NOT EDIT.\n"
        "; Edit version.json, then re-run: python build.py\n"
        f'#define MyAppVersion "{version}"\n'
        f'#define MyDeveloper  "{developer}"\n',
        encoding="ascii",
    )
    print(f"[build] wrote {out.name} (version={version}, developer={developer!r})")
    return out


def update_index_html_version() -> None:
    """Ensure app/resources/index.html version matches version.json."""
    version = read_version()
    if version == "0.0.0":
        return
    docs_path = ROOT / "app" / "resources" / "index.html"
    if not docs_path.exists():
        print(f"[build] WARNING: User Manual not found at {docs_path}")
        return
    try:
        content = docs_path.read_text(encoding="utf-8")
        import re
        new_content, count = re.subn(
            r"Manual — Version \d+\.\d+\.\d+",
            f"Manual — Version {version}",
            content
        )
        if count > 0 and new_content != content:
            docs_path.write_text(new_content, encoding="utf-8")
            print(f"[build] dynamically updated User Manual version to {version} in {docs_path.name}")
        else:
            print(f"[build] User Manual version is already up to date ({version})")
    except Exception as exc:
        print(f"[build] WARNING: could not update User Manual version: {exc}")



def write_sha256(exe: Path) -> tuple[str, bool]:
    """Compute SHA-256 of the built exe and write it into version.json.

    Returns (digest, changed) where `changed` indicates whether version.json
    now differs from its previous on-disk content. Callers use that to decide
    whether an auto-commit of version.json is worth doing.
    """
    print(f"[build] computing SHA-256 for {exe.name} ...")
    h = hashlib.sha256()
    with exe.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()

    vpath = ROOT / "version.json"
    changed = False
    try:
        with vpath.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        previous = data.get("sha256", "")
        if previous != digest:
            data["sha256"] = digest
            with vpath.open("w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=4)
            changed = True
            print(f"[build] sha256 written to version.json: {digest}")
        else:
            print(f"[build] sha256 unchanged in version.json: {digest}")
    except Exception as exc:
        print(f"[build] WARNING: could not update version.json sha256: {exc}")
    return digest, changed


def auto_commit_version_manifest(version: str) -> None:
    """Stage and commit version.json only.

    Triggered after write_sha256 reports a changed digest so the manifest
    that's about to be published carries the hash of the installer just
    built. We intentionally do NOT push — the user opted for local commit
    only, so the push remains a deliberate manual step (see release
    checklist).

    Failures here are non-fatal: the build artifacts are already on disk and
    the developer can finish the commit by hand if something goes wrong
    (e.g. no git repo, detached HEAD, hooks rejecting).
    """
    vpath = ROOT / "version.json"
    try:
        # Is there anything to commit for just this file?
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", str(vpath)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        if not status.stdout.strip():
            print("[build] version.json already matches HEAD; skipping auto-commit.")
            return

        rc = subprocess.call(["git", "add", "--", str(vpath)], cwd=ROOT)
        if rc != 0:
            print(f"[build] WARNING: 'git add version.json' failed (rc={rc}); skipping auto-commit.")
            return

        message = f"build: update sha256 in version.json for v{version}"
        rc = subprocess.call(["git", "commit", "-m", message, "--", str(vpath)], cwd=ROOT)
        if rc != 0:
            print(f"[build] WARNING: 'git commit' failed (rc={rc}); commit version.json manually.")
            return
        print(f"[build] committed version.json locally (run 'git push' to publish).")
    except FileNotFoundError:
        print("[build] WARNING: git not on PATH; skipping auto-commit of version.json.")
    except subprocess.CalledProcessError as exc:
        print(f"[build] WARNING: git status check failed: {exc}; skipping auto-commit.")


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
    """Zip dist/Bytehound/ into dist/Bytehound_<version>.zip."""
    if not DIST_DIR.exists():
        raise FileNotFoundError(f"dist folder not found: {DIST_DIR}")

    version = read_version()
    zip_base = ROOT / "dist" / f"{APP_NAME}_{version}"
    # NOTE: don't use Path.with_suffix here — versions like "0.1.0" make Path
    # treat the trailing ".0" as the suffix, yielding the wrong filename.
    zip_path = zip_base.parent / f"{zip_base.name}.zip"
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


def signing_enabled() -> bool:
    return bool(os.environ.get("SIGN_PFX")) and bool(os.environ.get("SIGN_PASSWORD"))


def find_signtool() -> Path | None:
    """Locate signtool.exe via $SIGNTOOL_PATH or the Windows 10/11 SDK bin tree."""
    env = os.environ.get("SIGNTOOL_PATH")
    if env and Path(env).exists():
        return Path(env)
    sdk_root = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    if not sdk_root.exists():
        return None
    candidates = [p for p in sdk_root.rglob("signtool.exe") if "x64" in str(p).lower()]
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0]


def sign_exe(exe: Path) -> int:
    """Sign exe with tools/sign.ps1. Returns 0 if disabled or success."""
    if not signing_enabled():
        return 0
    if not SIGN_SCRIPT.exists():
        print(f"[build] WARNING: signing requested but {SIGN_SCRIPT} missing")
        return 1
    cmd = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(SIGN_SCRIPT),
        "-ExePath", str(exe),
    ]
    print(f"[build] signing {exe.name}")
    return subprocess.call(cmd, cwd=ROOT)


def run_inno_setup() -> tuple[int, Path | None]:
    """Compile installer.iss with Inno Setup. Returns (rc, installer_path)."""
    iss = ROOT / "installer.iss"
    if not iss.exists():
        print("[build] installer.iss not found; skipping installer step")
        return 0, None

    # Regenerate installer_version.iss from version.json so the .iss file
    # picks up any version/developer change without a manual edit.
    write_installer_version_iss()

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
        return 0, None

    out_dir = ROOT / "installer_output"
    out_dir.mkdir(exist_ok=True)
    cmd: list[str] = [str(iscc)]

    if signing_enabled():
        signtool = find_signtool()
        if signtool is None:
            print("[build] WARNING: SIGN_PFX set but signtool.exe not found; building unsigned.")
        else:
            # Generate a tiny .cmd shim for Inno's SignTool. Embedding the full
            # signtool command directly in /Ssigntool= breaks when the SDK path
            # contains spaces — the nested quoting confuses ISCC's parser into
            # seeing extra positional args. The shim path has no spaces so the
            # /Ssigntool= value stays simple.
            # Two timestamp authorities for resilience: if DigiCert's TSA is
            # down at release time (it has happened), signtool exits non-zero
            # AND leaves the binary unsigned. Retrying with Sectigo lets the
            # build finish instead of failing the whole release.
            runner = ROOT / "tools" / "sign-runner.cmd"
            runner.write_text(
                "@echo off\r\n"
                f'"{signtool}" sign /f "%SIGN_PFX%" /p "%SIGN_PASSWORD%" '
                "/fd sha256 /tr http://timestamp.digicert.com /td sha256 %1\r\n"
                "if not errorlevel 1 exit /b 0\r\n"
                "echo [sign-runner] DigiCert TSA failed, retrying with Sectigo...\r\n"
                f'"{signtool}" sign /f "%SIGN_PFX%" /p "%SIGN_PASSWORD%" '
                "/fd sha256 /tr http://timestamp.sectigo.com /td sha256 %1\r\n",
                encoding="ascii",
            )
            cmd += ["/dSIGN", f"/Ssigntool=signtool={runner} $f"]
            print("[build] Inno Setup will sign installer + uninstaller")

    cmd.append(str(iss))
    print(f"[build] running Inno Setup")
    rc = subprocess.call(cmd, cwd=ROOT)
    if rc != 0:
        print(f"[build] Inno Setup FAILED with exit code {rc}", file=sys.stderr)
        return rc, None

    version = read_version()
    installer = out_dir / f"Bytehound_Setup_{version}.exe"
    if installer.exists():
        size_mb = installer.stat().st_size / (1024 * 1024)
        print(f"[build] installer ready: {installer}  ({size_mb:.1f} MB)")
        return rc, installer
    print(f"[build] installer built in {out_dir}/ but expected file not found")
    return rc, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Bytehound .exe")
    parser.add_argument("--no-clean",     action="store_true", help="skip wiping build/ and dist/")
    parser.add_argument("--no-zip",       action="store_true", help="skip the zip step")
    parser.add_argument("--no-installer", action="store_true", help="skip Inno Setup installer step")
    # Auto-commit is gated behind --release so local dev builds never mutate
    # version.json's sha256 in git. A developer poking at the build would
    # otherwise overwrite the hash of the CI-published installer with one
    # tied to their local PE timestamps, breaking the updater integrity check.
    parser.add_argument("--release",      action="store_true", help="treat this as a release build (auto-commit version.json sha256 when it changes)")
    args, passthrough = parser.parse_known_args()

    if not SPEC.exists():
        print(f"[build] ERROR: spec file not found at {SPEC}", file=sys.stderr)
        return 1

    # Sync installer_version.iss from version.json on every build, even when
    # --no-installer is set. Keeps the include file fresh for users who want
    # to compile installer.iss directly from the Inno Setup IDE later.
    write_installer_version_iss()
    update_index_html_version()

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

    if signing_enabled():
        rc = sign_exe(exe)
        if rc != 0:
            print(f"[build] inner exe signing FAILED (rc={rc})", file=sys.stderr)
            return rc

    # Build the installer FIRST, then hash whichever artifact end-users will
    # actually download. version.json's installer_url points at the Inno Setup
    # output, so the sha256 must match that file (not the inner bundled exe)
    # for the auto-updater integrity check to be meaningful.
    installer_path: Path | None = None
    if not args.no_installer:
        _rc, installer_path = run_inno_setup()

    if installer_path is not None:
        _digest, sha_changed = write_sha256(installer_path)
        # Only auto-commit when we hashed the real installer — hashing the
        # inner exe as a fallback would produce a sha256 that doesn't match
        # the binary served at installer_url, which is worse than leaving
        # version.json untouched.
        if sha_changed and args.release:
            auto_commit_version_manifest(read_version())
        elif sha_changed:
            print("[build] sha256 changed but --release not set; leaving version.json uncommitted.")
    else:
        print("[build] WARNING: no installer produced; hashing inner exe as fallback.")
        print("[build]   Auto-updater integrity verification will be inaccurate until")
        print("[build]   you install Inno Setup and rebuild.")
        write_sha256(exe)

    if not args.no_zip:
        try:
            make_zip()
        except Exception as e:
            print(f"[build] zip step FAILED: {e}", file=sys.stderr)
            return 1

    version = read_version()
    # ASCII-only banner so Python's default Windows console encoding (cp1252)
    # doesn't choke on box-drawing characters during printing.
    print(f"""
[build] --- Release checklist ---------------------------------------
  1. git push origin master      (version.json sha256 auto-committed above)
  2. git tag v{version} && git push origin v{version}
  3. Create GitHub Release v{version} and upload:
       installer_output/Bytehound_Setup_{version}.exe
       dist/{APP_NAME}_{version}.zip
  4. If installer_url in version.json needs updating, edit + commit + push
---------------------------------------------------------------------
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
