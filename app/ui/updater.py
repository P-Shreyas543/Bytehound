"""Auto-updater logic for Bytehound."""

import hashlib
import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, Signal

_LOG = logging.getLogger("bytehound.updater")


def require_https(url: str) -> str:
    """Only https:// URLs are opened (Bandit B310): the installer URL comes
    from the remote manifest, and urlopen would also accept file:// or
    other schemes."""
    if not str(url).lower().startswith("https://"):
        raise ValueError(f"refusing non-HTTPS URL: {url!r}")
    return url


def _project_root() -> Path:
    """Repo root in dev, exe-adjacent dir in a frozen PyInstaller build.

    Mirrors main_window._project_root so the updater finds version.json
    regardless of where the install layout puts it. The previous
    ``parent.parent`` walked from app/ui/updater.py to app/ — one level
    short — and the updater raised FileNotFoundError on every check.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def find_version_file() -> Path:
    """``version.json`` beside the exe (installed layout: the installer puts
    it there) or, when it is missing — a portable zip of the frozen build —
    the copy PyInstaller bundles in ``_internal``. Without the fallback a
    portable copy showed "v0.0.0" and the updater offered every release."""
    primary = _project_root() / "version.json"
    if primary.exists():
        return primary
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled and (Path(bundled) / "version.json").exists():
        return Path(bundled) / "version.json"
    return primary


VERSION_FILE = find_version_file()


def get_current_version() -> str:
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("version", "0.0.0")
    except Exception:
        # Missing or malformed version.json — fall back to a sentinel
        # version so the updater treats anything remote as newer. Log so
        # the install issue is visible in bytehound.log.
        _LOG.warning("Could not read %s; defaulting to 0.0.0", VERSION_FILE, exc_info=True)
        return "0.0.0"


class UpdateChecker(QThread):
    """Checks a remote version.json for updates."""
    update_available = Signal(str, str, str, str)  # version, installer_url, release_notes, sha256
    error = Signal(str)
    up_to_date = Signal()

    def run(self) -> None:
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                local_data = json.load(f)

            manifest_url = local_data.get("manifest_url", "")
            if not manifest_url:
                self.error.emit("No manifest URL configured in version.json.")
                return

            req = urllib.request.Request(require_https(manifest_url), headers={'User-Agent': 'Bytehound-Updater'})
            with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310 - https enforced
                remote_data = json.loads(response.read().decode("utf-8"))

            remote_version = remote_data.get("version", "0.0.0")
            local_version = local_data.get("version", "0.0.0")

            # Use packaging.version so non-numeric components ("1.0.0-rc1",
            # "1.0.0+dev", PEP 440 pre-releases) don't crash the parser.
            # Fall back to "up to date" on a malformed remote so a botched
            # manifest never blocks the user with an error dialog.
            from packaging.version import InvalidVersion, Version
            try:
                if Version(remote_version) > Version(local_version):
                    self.update_available.emit(
                        remote_version,
                        remote_data.get("installer_url", ""),
                        remote_data.get("release_notes", ""),
                        remote_data.get("sha256", ""),
                    )
                else:
                    self.up_to_date.emit()
            except InvalidVersion as exc:
                self.error.emit(f"Could not compare versions: {exc}")

        except Exception as e:
            self.error.emit(str(e))


class UpdateDownloader(QThread):
    """Downloads the new installer and verifies its sha256 before signaling done."""
    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, url: str, dest_path: str, expected_sha256: str = ""):
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        # Stored lower-case so the comparison is case-insensitive.
        self.expected_sha256 = (expected_sha256 or "").strip().lower()

    def run(self) -> None:
        try:
            hasher = hashlib.sha256()
            req = urllib.request.Request(require_https(self.url), headers={'User-Agent': 'Bytehound-Updater'})
            with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310 - https enforced
                total_size = int(response.getheader('Content-Length', 0))
                downloaded = 0
                with open(self.dest_path, 'wb') as f:
                    while True:
                        if self.isInterruptionRequested():
                            break
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            self.progress.emit(downloaded, total_size)
            if self.isInterruptionRequested():
                try:
                    os.remove(self.dest_path)
                except OSError:
                    pass
                return

            if self.expected_sha256:
                actual = hasher.hexdigest().lower()
                if actual != self.expected_sha256:
                    # Refuse to launch a tampered binary — delete it so a stale
                    # file in TEMP can't be opened manually by the user later.
                    try:
                        os.remove(self.dest_path)
                    except OSError:
                        pass
                    self.error.emit(
                        "Downloaded installer failed integrity check.\n"
                        f"Expected sha256: {self.expected_sha256}\n"
                        f"Actual sha256:   {actual}"
                    )
                    return
            else:
                # No checksum in remote manifest — refuse silently-launched install.
                self.error.emit(
                    "Remote manifest is missing a sha256 entry; refusing to install "
                    "an unverified binary."
                )
                return

            self.finished.emit(self.dest_path)
        except Exception as e:
            self.error.emit(str(e))


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def launch_installer(installer_path: str, expected_sha256: str = "") -> bool:
    """Launch the downloaded installer and exit the app.

    The file is hashed again right before it is started: it was verified
    when the download finished, but the user may take a while to answer
    "Install now?", and a file that changed in between must not run
    (check-then-use). Returns False, without launching, on a mismatch.
    """
    if expected_sha256:
        actual = file_sha256(installer_path)
        if actual != expected_sha256.strip().lower():
            _LOG.error("Installer %s changed after verification (sha256 %s); not launched",
                       installer_path, actual)
            try:
                os.remove(installer_path)
            except OSError:
                pass
            return False
    # /SILENT runs the Inno Setup installer without a wizard but shows progress
    # /VERYSILENT shows nothing
    subprocess.Popen([installer_path, "/SILENT"])

    # Graceful exit allows MainWindow.closeEvent to fire, saving UI state
    # and ensuring background logger threads drain cleanly.
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        app.quit()
    else:
        sys.exit(0)
    return True
