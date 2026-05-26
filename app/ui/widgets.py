"""Reusable UI widgets and helpers carved out of main_window.py.

Houses small, MainWindow-independent UI components:
* :class:`_CheckableGroupCombo`   — multi-select group filter button.
* :class:`_StatusBadgeDelegate`   — pill-style Status column delegate.
* :class:`TitleBarThemeFilter`    — application-wide native title-bar themer.
* :func:`_apply_windows_dark_titlebar` — the underlying DWM toggle.
* :func:`_icon`                   — qtawesome wrapper that degrades gracefully.
* :func:`_pad_dock_content`       — applies internal margins to a QDockWidget.
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QSettings, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

try:
    import qtawesome as qta  # type: ignore
except ImportError:  # pragma: no cover - icons degrade to empty if missing
    qta = None


# Primary toolbar button colour palette. Three semantic states; all buttons
# show white (#FFFFFF) text/icons on top.
_BTN_GREEN  = "#16A34A"   # idle / safe-to-activate  (Connect, Start Auto-Fetch)
_BTN_YELLOW = "#D97706"   # ready but not running     (Start Logging — inactive)
_BTN_PINK   = "#DB2777"   # currently active / danger (Disconnect, Stop Fetch/Log)


def _contrast_text_color(bg_hex: str) -> str:
    """Pick black or white text for the given background hex colour.

    Uses ITU-R BT.601 relative luminance — close enough for picking pill
    chip text. Yellow-ish backgrounds like ``#bcbd22`` and pastels like
    ``#98df8a`` were previously rendered with white text against white-ish
    fill, which was almost unreadable. This makes the swap automatic.
    """
    h = bg_hex.lstrip("#")
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
    except (ValueError, IndexError):
        return "#fff"
    # BT.601 weighting; cheap and accurate enough for chip text.
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000" if luminance > 0.55 else "#fff"


def _icon(name: str, color: str = "#F8FAFC") -> QIcon:
    """Return a qtawesome icon tinted with *color*, or an empty QIcon.

    Pass ``color='#1F2937'`` for light-theme icons and ``color='#F8FAFC'``
    (default) for dark-theme icons so they contrast against their background.
    """
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color)
    except Exception:
        return QIcon()


def _pad_dock_content(dock: "QDockWidget", margin: int = 12) -> None:
    """Apply uniform internal margins to a dock's content widget.

    If the inner widget already has a layout, set its contentsMargins. Otherwise
    wrap the widget in a thin QVBoxLayout shim so the padding takes effect.
    """
    inner = dock.widget()
    if inner is None:
        return
    layout = inner.layout()
    if layout is not None:
        layout.setContentsMargins(margin, margin, margin, margin)
        return
    shim = QWidget()
    shim_layout = QVBoxLayout(shim)
    shim_layout.setContentsMargins(margin, margin, margin, margin)
    shim_layout.addWidget(inner)
    dock.setWidget(shim)


def _apply_windows_dark_titlebar(widget, dark: bool) -> None:
    """Toggle the Windows 10/11 dark title bar on a top-level widget.

    No-op on non-Windows or if the DWM call is unavailable.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        if result != 0:
            # Older Windows 10 builds use attribute 19 instead.
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        pass


class _CheckableGroupCombo(QPushButton):
    """A button that opens a checkable list of group names.

    Behaviour:
    • "All groups"  (top item) — when checked, all other items are checked;
      when unchecked, all are unchecked.
    • Individual groups can be checked/unchecked independently.
    • Button label shows:  "All groups" | "<group name>" | "N groups"
    • ``selection_changed`` is emitted whenever the selection changes.
    """

    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("checkableGroupCombo")
        self.setMinimumWidth(160)
        self.setText("All groups  ▾")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Popup container ──────────────────────────────────────
        self._popup = QFrame(self.window(), Qt.WindowType.Popup)
        self._popup.setObjectName("checkableGroupPopup")
        self._popup.setFrameShape(QFrame.Shape.StyledPanel)
        self._popup.setFrameShadow(QFrame.Shadow.Raised)
        layout = QVBoxLayout(self._popup)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._list = QListWidget(self._popup)
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self._list)

        self._list.itemChanged.connect(self._on_item_changed)
        self.clicked.connect(self._show_popup)

    # ── public API ────────────────────────────────────────────

    def set_groups(self, groups: list[str]) -> None:
        """Rebuild the list from a sorted list of group names.

        Existing selection is cleared (all groups selected = show all).
        """
        self._list.blockSignals(True)
        self._list.clear()

        # "All groups" header item
        all_item = QListWidgetItem("All groups")
        all_item.setFlags(all_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        all_item.setCheckState(Qt.CheckState.Checked)
        self._list.addItem(all_item)

        for g in groups:
            item = QListWidgetItem(g)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)

        # Resize list height to content (max ~300 px)
        row_h = self._list.sizeHintForRow(0) + 2
        total = min(row_h * (len(groups) + 1) + 8, 300)
        self._list.setFixedHeight(total)

        self._list.blockSignals(False)
        self._update_button_label()

    def selected_groups(self) -> set[str]:
        """Return the set of checked group names.

        An empty set means *all* groups are selected (or there are no groups).
        """
        if self._list.count() == 0:
            return set()
        all_item = self._list.item(0)
        if all_item and all_item.checkState() == Qt.CheckState.Checked:
            return set()          # "All" checked → no filter
        result = set()
        for i in range(1, self._list.count()):
            item = self._list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                result.add(item.text())
        return result

    # ── internals ─────────────────────────────────────────────

    def _show_popup(self) -> None:
        # Position popup below the button
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.move(pos)
        self._popup.setFixedWidth(max(self.width(), 180))
        self._popup.show()
        self._popup.raise_()

    def _on_item_changed(self, changed_item: QListWidgetItem) -> None:
        self._list.blockSignals(True)
        if self._list.row(changed_item) == 0:
            # "All groups" toggled → apply to all
            state = changed_item.checkState()
            for i in range(1, self._list.count()):
                self._list.item(i).setCheckState(state)
        else:
            # Individual item toggled → sync "All groups" header
            all_checked = all(
                self._list.item(i).checkState() == Qt.CheckState.Checked
                for i in range(1, self._list.count())
            )
            self._list.item(0).setCheckState(
                Qt.CheckState.Checked if all_checked else Qt.CheckState.Unchecked
            )
        self._list.blockSignals(False)
        self._update_button_label()
        self.selection_changed.emit()

    def _update_button_label(self) -> None:
        checked = [
            self._list.item(i).text()
            for i in range(1, self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]
        total = self._list.count() - 1   # excluding "All groups" row
        if total == 0 or len(checked) == total:
            self.setText("All groups  ▾")
        elif len(checked) == 1:
            self.setText(f"{checked[0]}  ▾")
        else:
            self.setText(f"{len(checked)} groups  ▾")


class _StatusBadgeDelegate(QStyledItemDelegate):
    """Paint the Status column as a rounded pill badge.

    Green for "ok", red for "error"/"fail", orange for everything else
    non-empty/non-dash. Falls back to the default delegate for empty / "-".
    Colors mirror the LED status palette for visual consistency.
    """

    # Light/dark colour pairs. Tailwind 500-shades work on white backgrounds
    # (light theme). On the Slate-900 dark theme they're a touch desaturated;
    # the 400-shades pop more without losing meaning.
    _LIGHT_GREEN = QColor("#10B981")   # emerald-500
    _LIGHT_RED = QColor("#EF4444")     # rose-500
    _LIGHT_ORANGE = QColor("#F59E0B")  # amber-500
    _DARK_GREEN = QColor("#34D399")    # emerald-400
    _DARK_RED = QColor("#F87171")      # rose-400
    _DARK_ORANGE = QColor("#FBBF24")   # amber-400

    def __init__(self, parent=None, *, settings: Optional[QSettings] = None) -> None:
        super().__init__(parent)
        self._settings = settings

    def _palette(self) -> tuple[QColor, QColor, QColor]:
        # Resolve the current theme on every paint; cheap, and avoids needing
        # a separate "theme changed" signal wired into the delegate.
        # Lazy import: widgets.py is imported during theming.py module init,
        # so a top-level import would be a cycle.
        from .theming import resolve_theme
        theme = "dark"
        if self._settings is not None:
            theme = str(self._settings.value("ui/theme", "dark"))
        if resolve_theme(theme) == "light":
            return self._LIGHT_GREEN, self._LIGHT_RED, self._LIGHT_ORANGE
        return self._DARK_GREEN, self._DARK_RED, self._DARK_ORANGE

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        if not text or text == "-":
            super().paint(painter, option, index)
            return

        # Honor selection highlight from the style first.
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        green, red, orange = self._palette()
        lower = text.lower()
        if "ok" in lower and "error" not in lower:
            color = green
        elif "error" in lower or "fail" in lower:
            color = red
        else:
            color = orange

        rect = option.rect.adjusted(6, 4, -6, -4)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2.0, rect.height() / 2.0)
        painter.fillPath(path, QBrush(color))
        painter.setPen(QPen(QColor("white")))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class TitleBarThemeFilter(QObject):
    """Application-wide event filter that themes the native title bar of
    every top-level widget (main window, dialogs, popups) when it is shown."""

    def __init__(self, settings: QSettings, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Show:
            try:
                if hasattr(obj, "isWindow") and obj.isWindow() and hasattr(obj, "winId"):
                    from .theming import resolve_theme
                    theme = str(self._settings.value("ui/theme", "dark"))
                    _apply_windows_dark_titlebar(obj, dark=(resolve_theme(theme) == "dark"))
            except Exception:
                pass
        return False
