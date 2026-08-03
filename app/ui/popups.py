"""Popup-message helpers extracted from MainWindow as a mixin.

Each popup logs itself into the Activity Log before delegating to
``QMessageBox``. The mixin relies on the host to provide
``self._log_activity(str)`` — that method stays on MainWindow because it
writes into a widget owned there.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox


class PopupsMixin:
    """MainWindow mixin: standard popup wrappers + the activity-log helper."""

    def _log_popup(self, kind: str, title: str, message: str) -> None:
        """Log a popup/error message into the Activity Log.

        Keeps single-line popups on one line; multi-line popups are logged
        as a small block for readability.
        """
        message_text = "" if message is None else str(message)
        lines = message_text.splitlines()
        if not lines:
            self._log_activity(f"[{kind}] {title}")
            return
        if len(lines) == 1:
            self._log_activity(f"[{kind}] {title}: {lines[0]}")
            return
        self._log_activity(f"[{kind}] {title}:")
        for line in lines:
            self._log_activity(f"    {line}")

    def _popup_information(self, title: str, message: str) -> None:
        self._log_popup("INFO", title, message)
        from app.ui.toast import Toast
        Toast.show_toast(self, message, level="info")

    def _popup_warning(self, title: str, message: str) -> None:
        self._log_popup("WARN", title, message)
        from app.ui.toast import Toast
        Toast.show_toast(self, message, level="warning", duration_ms=4000)

    def _popup_critical(self, title: str, message: str) -> None:
        self._log_popup("ERROR", title, message)
        from app.ui.toast import Toast
        Toast.show_toast(self, message, level="error", duration_ms=5000)
        # Keep the blocking box for critical errors as well, as they often require immediate attention
        QMessageBox.critical(self, title, message)

    def _popup_about(self, title: str, message: str) -> None:
        self._log_popup("ABOUT", title, message)
        QMessageBox.about(self, title, message)

    def _popup_question(
        self,
        title: str,
        message: str,
        *,
        buttons: QMessageBox.StandardButtons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    ) -> QMessageBox.StandardButton:
        self._log_popup("QUESTION", title, message)
        reply = QMessageBox.question(self, title, message, buttons, default_button)
        selected = "Yes" if reply == QMessageBox.StandardButton.Yes else "No" if reply == QMessageBox.StandardButton.No else str(reply)
        self._log_activity(f"[QUESTION] {title}: user selected {selected}")
        return reply
