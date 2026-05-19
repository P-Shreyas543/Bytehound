"""UI-side glue for the update check/download flow.

Mixin that holds the four signal handlers wired around
:class:`UpdateChecker` and :class:`UpdateDownloader`, plus the
``_download_update`` helper that owns the QProgressDialog. Designed to be
mixed into ``MainWindow`` — relies on host helpers ``self._log_activity``,
``self._popup_information``, ``self._popup_warning``, ``self._popup_critical``,
``self._popup_question`` and ``self._set_status``.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from .updater import UpdateChecker, UpdateDownloader, launch_installer


class UpdaterWiringMixin:
    """MainWindow mixin holding the update-check/download UI wiring."""

    def _on_check_updates(self) -> None:
        self._log_activity("[ACTION] Check for updates")
        self._update_checker = UpdateChecker()
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.up_to_date.connect(
            lambda: self._popup_information("Updater", "You are on the latest version.")
        )
        self._update_checker.error.connect(
            lambda e: self._popup_warning("Updater", f"Failed to check for updates:\n{e}")
        )
        self._update_checker.start()
        self._set_status("Checking for updates...")

    def _on_update_available(self, version: str, url: str, release_notes: str, sha256: str) -> None:
        reply = self._popup_question(
            "Update Available",
            (
                f"Version {version} is available.\n\n"
                f"Notes:\n{release_notes}\n\n"
                "Would you like to download and install it?"
            ),
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_update(url, sha256)

    def _download_update(self, url: str, sha256: str) -> None:
        # Late import: main_window imports this mixin, so importing APP_NAME at
        # module level would create a cycle.
        from .main_window import APP_NAME
        self._progress = QProgressDialog("Downloading update...", "Cancel", 0, 100, self)
        self._progress.setWindowTitle("Updater")
        # Non-modal so the user can keep working while the download runs.
        # A 50 MB download on a slow connection used to freeze the main
        # window for minutes; now the dialog floats but the rest of the
        # app stays responsive. Suppress auto-close on reaching maximum so
        # the user can read the final state before the download-finished
        # handler explicitly closes it.
        self._progress.setWindowModality(Qt.WindowModality.NonModal)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        # Keep the dialog above its parent without grabbing focus.
        self._progress.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._progress.show()

        dest_path = str(Path(os.environ.get("TEMP", ".")) / f"{APP_NAME}_Update.exe")
        self._downloader = UpdateDownloader(url, dest_path, expected_sha256=sha256)
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(
            lambda e: self._popup_critical("Updater Error", f"Download failed:\n{e}")
        )
        self._progress.canceled.connect(self._downloader.requestInterruption)
        self._downloader.start()

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        self._progress.setMaximum(total)
        self._progress.setValue(downloaded)

    def _on_download_finished(self, dest_path: str) -> None:
        self._progress.close()
        reply = self._popup_question(
            "Update Ready",
            "Download complete. Install now? The application will restart.",
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            launch_installer(dest_path)
