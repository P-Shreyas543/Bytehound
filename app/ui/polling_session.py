"""Auto-fetch polling lifecycle methods extracted from MainWindow.

PollingSessionMixin holds the four methods that drive polling: populate
sidebar, toggle on/off, open the config dialog, and refresh the status.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QListWidgetItem

from .dialogs import PollingConfigDialog
from .widgets import _BTN_GREEN, _BTN_PINK


class PollingSessionMixin:
    """MainWindow mixin holding polling start/stop/config methods."""

    def _populate_polling_list(self) -> None:
        """Deprecated shim — delegates to the new status-sidebar updater."""
        self._update_poll_status_sidebar()

    def _on_toggle_polling(self) -> None:
        enabled = self._polling_action.isChecked()
        self._log_activity(f"[ACTION] Auto-Fetch toggle requested: {'start' if enabled else 'stop'}")
        if enabled:
            # Turning ON: open the config dialog to let the user pick targets
            if self._config is None:
                self._popup_warning("Auto-Fetch", "Please load a configuration first.")
                self._polling_action.setChecked(False)
                return
            if self._serial is None:
                self._popup_warning("Auto-Fetch", "Please connect to a device first.")
                self._polling_action.setChecked(False)
                return
            dlg = PollingConfigDialog(self._config.polling_schedules, self._settings, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._polling_action.setChecked(False)
                return
            # Apply the chosen enabled/disabled state per target in the worker
            enabled_ids = dlg.get_enabled_ids()
            for sched in self._config.polling_schedules:
                self._serial.toggle_schedule(sched.target_id, sched.target_id in enabled_ids)
            # Refresh the sidebar read-only list
            self._update_poll_status_sidebar(enabled_ids)
        else:
            if self._serial:
                self._serial.set_polling_global(False)
        self._polling_action.setText("Stop Auto-Fetch" if enabled else "Start Auto-Fetch")
        self._style_action_btn(
            self._polling_action,
            _BTN_PINK if enabled else _BTN_GREEN,
        )
        if self._serial:
            self._serial.set_polling_global(enabled)
        self._log_activity(f"[ACTION] Auto-Fetch {'started' if enabled else 'stopped'}")

    def _open_poll_config_dialog(self) -> None:
        """Sidebar Configure… button — opens dialog without toggling the action."""
        self._log_activity("[ACTION] Open Poll Schedule configure dialog")
        if self._config is None:
            self._popup_warning("Poll Schedule", "Load a configuration first.")
            return
        dlg = PollingConfigDialog(self._config.polling_schedules, self._settings, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        enabled_ids = dlg.get_enabled_ids()
        if self._serial:
            for sched in self._config.polling_schedules:
                self._serial.toggle_schedule(sched.target_id, sched.target_id in enabled_ids)
        self._update_poll_status_sidebar(enabled_ids)
        self._log_activity(
            f"[ACTION] Poll Schedule updated ({len(enabled_ids)} target(s) enabled)"
        )

    def _update_poll_status_sidebar(self, enabled_ids: set | None = None) -> None:
        """Refresh the read-only Poll Schedule sidebar list."""
        if not hasattr(self, "_polling_list"):
            return
        self._polling_list.clear()
        if self._config is None:
            if hasattr(self, "_poll_status_label"):
                self._poll_status_label.setText("No targets loaded")
            return
        active = 0
        for sched in self._config.polling_schedules:
            is_on = (enabled_ids is None and sched.enabled) or (
                enabled_ids is not None and sched.target_id in enabled_ids
            )
            label = f"0x{sched.target_id:04X}  ({sched.interval_ms} ms)"
            item = QListWidgetItem(("\u25cf " if is_on else "\u25cb ") + label)
            # Active = saturated green (works on both themes); inactive = the
            # disabled-text palette role so it dims correctly in light mode
            # instead of disappearing into the white background.
            if is_on:
                item.setForeground(QColor("#16A34A"))
            else:
                item.setForeground(self.palette().color(self.palette().ColorGroup.Disabled,
                                                        self.palette().ColorRole.Text))
            self._polling_list.addItem(item)
            if is_on:
                active += 1
        if hasattr(self, "_poll_status_label"):
            total = len(self._config.polling_schedules)
            self._poll_status_label.setText(f"{active} of {total} targets active")

