"""Auto-updater logic for Serial-MonitorApp."""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal

VERSION_FILE = Path(__file__).resolve().parent.parent / "version.json"


def get_current_version() -> str:
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("version", "0.0.0")
    except Exception:
        return "0.0.0"


class UpdateChecker(QThread):
    """Checks a remote version.json for updates."""
    update_available = Signal(str, str, str)  # version, installer_url, release_notes
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

            req = urllib.request.Request(manifest_url, headers={'User-Agent': 'Serial-MonitorApp-Updater'})
            with urllib.request.urlopen(req, timeout=5) as response:
                remote_data = json.loads(response.read().decode("utf-8"))
                
            remote_version = remote_data.get("version", "0.0.0")
            local_version = local_data.get("version", "0.0.0")
            
            # Simple string comparison works for X.Y.Z if zero-padded or uniform
            # Consider using 'packaging.version' in a real environment
            if [int(x) for x in remote_version.split('.')] > [int(x) for x in local_version.split('.')]:
                self.update_available.emit(
                    remote_version, 
                    remote_data.get("installer_url", ""), 
                    remote_data.get("release_notes", "")
                )
            else:
                self.up_to_date.emit()
                
        except Exception as e:
            self.error.emit(str(e))


class UpdateDownloader(QThread):
    """Downloads the new installer."""
    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, url: str, dest_path: str):
        super().__init__()
        self.url = url
        self.dest_path = dest_path

    def run(self) -> None:
        try:
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Serial-MonitorApp-Updater'})
            with urllib.request.urlopen(req, timeout=10) as response:
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
                        downloaded += len(chunk)
                        if total_size > 0:
                            self.progress.emit(downloaded, total_size)
            if not self.isInterruptionRequested():
                self.finished.emit(self.dest_path)
        except Exception as e:
            self.error.emit(str(e))


def launch_installer(installer_path: str) -> None:
    """Launches the downloaded installer and exits the app."""
    # /SILENT runs the Inno Setup installer without a wizard but shows progress
    # /VERYSILENT shows nothing
    subprocess.Popen([installer_path, "/SILENT"])
    sys.exit(0)
