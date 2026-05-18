"""PySide6 main window for the Serial monitor."""

from __future__ import annotations

import logging
import math
import os
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, QUrl, QObject, Signal, QSortFilterProxyModel, QLocale
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QFrame,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QIntValidator, QDoubleValidator

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover - exercised only when optional dep missing
    pg = None

import numpy as np

if pg is not None:
    # Global, intentional: keeps rendering consistent across Live Plot and Analysis Suite.
    pg.setConfigOptions(antialias=True)

try:
    import qdarktheme
except ImportError:  # pragma: no cover
    qdarktheme = None

try:
    import qtawesome as qta  # type: ignore
except ImportError:  # pragma: no cover - icons degrade to empty if missing
    qta = None


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

APP_ORG  = "Bytehound"
APP_NAME = "Bytehound"
APP_DISPLAY_NAME = "Bytehound"


def _project_root() -> Path:
    """Return the dir to look for runtime assets (branding/, version.json).

    Frozen build: next to Bytehound.exe (build.py copies branding/ here).
    Dev run:      the repo root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _read_version() -> str:
    try:
        import json
        with (_project_root() / "version.json").open("r", encoding="utf-8") as fp:
            return json.load(fp).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def _find_logo(name: str) -> Optional[Path]:
    """Search a few common locations for a branding asset."""
    root = _project_root()
    for candidate in (root / "branding" / name, root / name):
        if candidate.exists():
            return candidate
    return None


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


_PLOT_PALETTE_DARK = (
    "#60A5FA", "#F87171", "#34D399", "#FBBF24", "#C4B5FD",
    "#38BDF8", "#F472B6", "#A3E635", "#FDBA74", "#FCA5A5",
    "#22D3EE", "#E879F9",
)
_PLOT_PALETTE_LIGHT = (
    "#1D4ED8", "#DC2626", "#059669", "#D97706", "#7C3AED",
    "#0284C7", "#BE185D", "#16A34A", "#9333EA", "#C2410C",
    "#0F766E", "#7C2D12",
)

# Width of the live plot's X view before any data has arrived AND the minimum
# width once data exists. Keeps the curve from looking glued to the left edge
# in the first ~10 s of a session.
_PLOT_INITIAL_WINDOW_S = 10.0


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
        self.setMinimumWidth(160)
        self.setText("All groups")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Popup container ──────────────────────────────────────
        self._popup = QFrame(self.window(), Qt.WindowType.Popup)
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
            self.setText("All groups")
        elif len(checked) == 1:
            self.setText(checked[0])
        else:
            self.setText(f"{len(checked)} groups")


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
        theme = "dark"
        if self._settings is not None:
            theme = str(self._settings.value("ui/theme", "dark"))
        if theme == "light":
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
                    theme = str(self._settings.value("ui/theme", "dark"))
                    _apply_windows_dark_titlebar(obj, dark=(theme == "dark"))
            except Exception:
                pass
        return False


def _format_serial_open_error(port: str, exc: BaseException) -> str:
    """Return a user-friendly explanation for a failed serial port open.

    Falls back to the raw exception text if the error doesn't match a known
    pattern, but always includes the original detail at the end.
    """
    raw = str(exc)
    lower = raw.lower()
    port_label = port or "the selected port"

    if isinstance(exc, PermissionError) or "permissionerror" in lower or "access is denied" in lower:
        friendly = (
            f"Cannot open {port_label}.\n\n"
            "The port is unavailable. Common causes:\n"
            "  • The device was unplugged or its driver glitched — try unplugging and re-plugging it.\n"
            "  • Another application is using the port (Arduino IDE Serial Monitor, PuTTY, another terminal, or a previous instance of this app).\n"
            "  • The port no longer exists — refresh the port list.\n"
        )
    elif "could not open port" in lower or "filenotfounderror" in lower:
        friendly = (
            f"Could not open {port_label}.\n\n"
            "The port does not exist. It may have been disconnected; refresh the port list and try again.\n"
        )
    else:
        friendly = f"Failed to open {port_label}.\n"

    return f"{friendly}\nDetails: {raw}"

from .updater import UpdateChecker, UpdateDownloader, launch_installer
from .telemetry_model import TelemetryTableModel, COLUMNS as _MODEL_COLUMNS
from .dialogs import ConnectionDialog, LoggingSettingsDialog, PollingConfigDialog
from ..commands.tx_command_builder import CommandBuildError, build_tx_command
from ..decoder.config_loader import ConfigError, load_config
from ..decoder.frame_decoder import DecodedFrame, DecodedSignal, decode_frame
from ..decoder.template_io import export_excel_template, snapshot_config
from ..decoder.types import FrameConfig
from ..serial_logging.decoded_logger import DecodedLogger
from ..serial_logging.raw_logger import RawLogger
from ..protocol.packet_parser import create_parser, ParserProtocol, ParsedPacket
from ..serial_io.replay_source import parse_log_file, replay_bytes
from ..serial_io.serial_worker import SerialSettings, PollingWorker, available_ports

_COLUMNS = (
    ("Frame",     100),
    ("Group",      90),
    ("Variable",  190),
    ("Start B.",   60),
    ("Data Type",  75),
    ("Raw",        95),
    ("Value",      95),
    ("Unit",       55),
    ("Status",     70),
    ("Updated",   110),
)

# ---------------------------------------------------------------------------
# QSS stylesheets
# ---------------------------------------------------------------------------
# _QSS_BASE — rules shared by every theme.
# Uses palette() references so they adapt to both dark and light themes when
# qdarktheme is NOT installed or when the light theme is active.
_QSS_BASE = """
QWidget#centralPanel {
    background-color: palette(window);
}
QFrame[card="true"] {
    background-color: palette(alternate-base);
    border: 1px solid palette(mid);
    border-radius: 10px;
}
QLabel[cardTitle="true"] {
    font-family: "PT Sans";
    font-size: 11pt;
    font-weight: bold;
}
QDockWidget {
    border: none;
}
QDockWidget::title {
    background: palette(window);
    padding: 4px 8px;
    border-bottom: 1px solid palette(mid);
    font-weight: bold;
}
QToolButton#primaryAction {
    background-color: #388E3C;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 4px 12px;
    font-weight: bold;
}
QToolButton#primaryAction:hover  { background-color: #4CAF50; }
QToolButton#primaryAction:pressed { background-color: #2E7D32; }
QToolButton#primaryAction:disabled {
    /* Use palette roles so disabled state is legible in both themes. */
    background-color: palette(midlight);
    color: palette(mid);
}
QMenu { padding: 5px; }
QMenu::item {
    padding: 6px 24px 6px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    /* Track the active palette: qdarktheme picks an appropriate highlight
       blue for dark mode and a paler one for light mode. Hard-coding a
       saturated blue here used to clash with the light-theme menu. */
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
QMenu::separator {
    height: 1px;
    background: palette(mid);
    margin: 4px 8px;
}
"""

# _QSS_DARK_OVERRIDES — appended on top of _QSS_BASE when dark mode is active.
# These rules use explicit hex codes to override the qdarktheme palette values
# that cause the three visual bugs:
#   1. Dock title bars rendering with bright white background / invisible text
#   2. White separators / bleed-through behind the main table
#   3. Toolbar icon buttons too dark against the dark toolbar
_QSS_DARK_OVERRIDES = """
/* 1. Main window and separator backgrounds */
QMainWindow, QMainWindow::separator {
    background-color: #0F172A;
}
/* The central panel contains the filter bar + main table.
   objectName is set to "centralPanel" in _build_main_layout(). */
QWidget#centralPanel {
    background-color: #1E293B;
}

/* 2. Dock widget panels and title bars */
QDockWidget {
    color: #F8FAFC;
}
QDockWidget > QWidget {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 4px;
}
QDockWidget::title {
    background-color: #1E293B;
    text-align: left;
    padding: 6px 10px;
    color: #F8FAFC;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    border-bottom: 1px solid #334155;
    font-weight: bold;
}

/* 3. Toolbar icon contrast */
QToolBar QToolButton {
    color: #F8FAFC;
}

/* 4. Central panel: also make its direct QWidget children (layout containers)
   inherit the dark background so no white sub-panels bleed through. */
QWidget#centralPanel > QWidget {
    background-color: #1E293B;
}

/* 5. Input controls — search bar, dropdowns, spinboxes */
QLineEdit, QComboBox, QSpinBox {
    background-color: #0F172A;
    color: #F8FAFC;
    border: 1px solid #334155;
    padding: 4px 8px;
    border-radius: 3px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #2563EB;
}
QComboBox QAbstractItemView {
    background-color: #1E293B;
    color: #F8FAFC;
    selection-background-color: #2563EB;
    border: 1px solid #334155;
}

/* 6. Checkboxes */
QCheckBox {
    color: #F8FAFC;
    background-color: transparent;
}

/* 7. Main data table body */
QTableView {
    background-color: #0F172A;
    alternate-background-color: #1E293B;
    color: #F8FAFC;
    gridline-color: #334155;
    border: 1px solid #334155;
    border-radius: 3px;
}
QTableView::item:selected {
    background-color: #2563EB;
    color: #F8FAFC;
}

/* 8. Table column headers */
QHeaderView::section {
    background-color: #1E293B;
    color: #F8FAFC;
    padding: 4px 6px;
    border: 1px solid #334155;
    font-weight: bold;
}
QHeaderView::section:hover {
    background-color: #273549;
}

/* 9. Tabbed dock bars — match the dock title surface so the tabs
      look like an extension of the dock header, not a separate band. */
QTabBar {
    background-color: #1E293B;
}
QTabBar::tab {
    background-color: #1E293B;
    color: #CBD5E1;
    padding: 6px 14px;
    border: 1px solid transparent;
    border-bottom: 1px solid #334155;
}
QTabBar::tab:selected {
    background-color: #0F172A;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-bottom: 2px solid #2563EB;
}
QTabBar::tab:hover:!selected {
    background-color: #273549;
    color: #F8FAFC;
}
"""


# _QSS_LIGHT_OVERRIDES — mirror of _QSS_DARK_OVERRIDES with light-theme colors.
# qdarktheme's light palette doesn't always propagate cleanly through Qt's
# QDockWidget::title rendering (especially on Windows with PySide6 6.6+),
# leaving dock title bars stuck on the previous dark colours after a theme
# switch. Explicit hex codes here guarantee the light theme actually looks
# light, mirroring the role each rule plays in the dark variant.
_QSS_LIGHT_OVERRIDES = """
/* 1. Main window and separator backgrounds */
QMainWindow, QMainWindow::separator {
    background-color: #F1F5F9;
}
/* Central panel + its direct widget children */
QWidget#centralPanel {
    background-color: #FFFFFF;
}
QWidget#centralPanel > QWidget {
    background-color: #FFFFFF;
}

/* 2. Dock widget panels and title bars */
QDockWidget {
    color: #1F2937;
}
QDockWidget > QWidget {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 4px;
}
QDockWidget::title {
    background-color: #F3F4F6;
    text-align: left;
    padding: 6px 10px;
    color: #1F2937;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    border-bottom: 1px solid #E5E7EB;
    font-weight: bold;
}

/* 3. Toolbar icon contrast on light bg */
QToolBar QToolButton {
    color: #1F2937;
}

/* 4. Input controls */
QLineEdit, QComboBox, QSpinBox {
    background-color: #FFFFFF;
    color: #1F2937;
    border: 1px solid #D1D5DB;
    padding: 4px 8px;
    border-radius: 3px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #2563EB;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #1F2937;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
    border: 1px solid #D1D5DB;
}

/* 5. Checkboxes */
QCheckBox {
    color: #1F2937;
    background-color: transparent;
}

/* 6. Main data table body */
QTableView {
    background-color: #FFFFFF;
    alternate-background-color: #F9FAFB;
    color: #1F2937;
    gridline-color: #E5E7EB;
    border: 1px solid #E5E7EB;
    border-radius: 3px;
}
QTableView::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}

/* 7. Table column headers */
QHeaderView::section {
    background-color: #F3F4F6;
    color: #1F2937;
    padding: 4px 6px;
    border: 1px solid #E5E7EB;
    font-weight: bold;
}
QHeaderView::section:hover {
    background-color: #E5E7EB;
}

/* 8. Tabbed dock bars (Bitfields | Enums | TX Commands | … and the
      Raw Console | Activity Log pair). Without these, Qt's default
      tab rendering picks up a hold-over dark colour from earlier
      stylesheets and the tab strip looks black in light mode. */
QTabBar {
    background-color: #F3F4F6;
}
QTabBar::tab {
    background-color: #F3F4F6;
    color: #1F2937;
    padding: 6px 14px;
    border: 1px solid transparent;
    border-bottom: 1px solid #E5E7EB;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #1F2937;
    border: 1px solid #E5E7EB;
    border-bottom: 2px solid #2563EB;
}
QTabBar::tab:hover:!selected {
    background-color: #E5E7EB;
}
"""


def build_card_qss(theme: str) -> str:
    """Assemble the app's shared card/dock/table/tab QSS for a given theme.

    Exposed so secondary top-level windows (e.g. Analysis Suite) can apply the
    same styling — qdarktheme's palette is applied app-wide, but these QSS
    rules are not, and must be installed on each top-level window.
    """
    qss = _QSS_BASE
    if theme == "dark":
        qss += "\n" + _QSS_DARK_OVERRIDES
    elif theme == "light":
        qss += "\n" + _QSS_LIGHT_OVERRIDES
    return qss


# ---------------------------------------------------------------------------
# Primary toolbar button colour palette
# ---------------------------------------------------------------------------
# Three semantic states; all buttons show white (#FFFFFF) text/icons on top.
_BTN_GREEN  = "#16A34A"   # idle / safe-to-activate  (Connect, Start Auto-Fetch)
_BTN_YELLOW = "#D97706"   # ready but not running     (Start Logging — inactive)
_BTN_PINK   = "#DB2777"   # currently active / danger (Disconnect, Stop Fetch/Log)

# ---------------------------------------------------------------------------
# Live Plot grid layouts
# ---------------------------------------------------------------------------
# Each entry: display label → (rows, cols)
GRID_LAYOUTS: Dict[str, Tuple[int, int]] = {
    "1×1": (1, 1),
    "1×2": (1, 2),
    "2×1": (2, 1),
    "1×3": (1, 3),
    "3×1": (3, 1),
    "2×2": (2, 2),
    "2×4": (2, 4),
    "4×2": (4, 2),
}


@dataclass
class PlotPanel:
    """State for one subplot cell in the multi-grid live plot.

    ``plot_item``     – the pyqtgraph PlotItem for this cell.
    ``assigned_keys`` – ordered list of (frame_id, signal_name) signals to draw.
    ``curves``        – mapping from key → PlotDataItem (the live curve object).
    ``auto_fit_y``    – when True, pyqtgraph rescales the y-axis automatically
                        so growing signals stay in view without manual zoom.
    """
    plot_item: object                                     # pg.PlotItem
    assigned_keys: List[Tuple[int, str]] = field(default_factory=list)
    curves:        Dict[Tuple[int, str], object] = field(default_factory=dict)
    auto_fit_y:    bool = True
    legend:        Optional[object] = None
    time_axis:     Optional[object] = None
    index:         int = 0


def _format_elapsed_time(seconds: float, spacing: Optional[float] = None) -> str:
    if not math.isfinite(seconds):
        return ""
    spacing = spacing if spacing is not None else 1.0
    abs_s = abs(seconds)
    if abs_s >= 60 or spacing >= 10:
        sign = "-" if seconds < 0 else ""
        minutes, secs = divmod(abs_s, 60)
        return f"{sign}{int(minutes)}:{int(secs):02d}"
    if spacing < 1:
        return f"{seconds:.1f}s"
    return f"{seconds:.0f}s"


if pg is not None:
    class _TimeAxisItem(pg.AxisItem):
        def __init__(
            self,
            *,
            mode: str = "elapsed",
            session_start: Optional[datetime] = None,
            min_label_px: int = 80,
        ) -> None:
            super().__init__(orientation="bottom")
            self._mode = mode
            self._session_start = session_start or datetime.now()
            self._min_label_px = min_label_px

        def set_mode(self, mode: str) -> None:
            self._mode = mode

        def set_session_start(self, session_start: datetime) -> None:
            self._session_start = session_start

        @staticmethod
        def _nice_step(span: float, target_ticks: int) -> float:
            raw = span / max(target_ticks, 1)
            if raw <= 0 or not math.isfinite(raw):
                return 1.0
            power = 10 ** math.floor(math.log10(raw))
            for mult in (1, 2, 5, 10):
                step = mult * power
                if step >= raw:
                    return step
            return 10 * power

        def tickValues(self, minVal: float, maxVal: float, size: float):  # noqa: N802
            if not (math.isfinite(minVal) and math.isfinite(maxVal)):
                return []
            span = maxVal - minVal
            if span <= 0 or size <= 0:
                return []
            target = max(2, int(size / self._min_label_px))
            step = self._nice_step(span, target)
            first = math.floor(minVal / step) * step
            count = int(math.ceil((maxVal - first) / step)) + 1
            ticks = [first + i * step for i in range(count)]
            return [(step, ticks)]

        def tickStrings(self, values, scale, spacing):  # noqa: N802
            if self._mode == "clock":
                base = self._session_start
                return [
                    (base + timedelta(seconds=float(v))).strftime("%H:%M:%S")
                    if math.isfinite(float(v)) else ""
                    for v in values
                ]
            return [_format_elapsed_time(float(v), spacing) for v in values]
else:
    _TimeAxisItem = object  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Configuration dialogs
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def _make_history_buffer(self) -> Tuple[Deque[float], Deque[float]]:
        """Factory for the parallel-deque entries in ``self._plot_history``.

        Two bounded deques: one for x (timestamps), one for y (values).
        ``maxlen`` is read from ``self._plot_history_maxlen`` so it can be
        changed at runtime; existing buffers keep their original cap until
        a new signal is first plotted.
        """
        n = getattr(self, "_plot_history_maxlen", 6_000)
        return (deque(maxlen=n), deque(maxlen=n))


    def __init__(self) -> None:
        super().__init__()
        self._version = _read_version()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} v{self._version}")
        self.resize(1280, 780)

        icon_path = _find_logo("logo_sq.ico") or _find_logo("logo_sq.png")
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))

        self._config: Optional[FrameConfig] = None
        self._config_path: Optional[Path] = None
        self._parser: Optional[ParserProtocol] = None
        self._serial: Optional[PollingWorker] = None
        # Inter-packet latency in milliseconds — time between consecutive RX
        # frames reaching _handle_packet. _last_packet_perf is the perf_counter
        # timestamp of the previous packet, or None before the first packet.
        self._delta_t_ms = 0.0
        self._last_packet_perf: Optional[float] = None
        self._row_index: Dict[Tuple[int, str], int] = {}
        self._packet_count = 0
        self._error_count = 0
        self._timeouts = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._logging = False
        self._raw_logger: Optional[RawLogger] = None
        self._decoded_logger: Optional[DecodedLogger] = None
        self._settings = QSettings(APP_ORG, APP_NAME)
        self._apply_logging_level(str(self._settings.value("logging/level", "INFO")))
        self._tx_field_inputs: Dict[str, QLineEdit] = {}
        self._seen_decode_warnings: set[tuple[int, str, int]] = set()

        # Timer removed; using PollingWorker QThread

        # Live-plot history. Two parallel bounded deques per signal (one for
        # x, one for y) instead of a single deque of (x, y) tuples: this lets
        # _redraw_plot pass arrays straight to setData without the expensive
        # zip(*values) unpack pass — a meaningful win at 60 Hz with 5+ curves
        # and a long history.
        self._plot_history_maxlen: int = int(
            self._settings.value("plot/history_maxlen", 6_000))
        self._plot_history: Dict[Tuple[int, str], Tuple[Deque[float], Deque[float]]] = (
            defaultdict(self._make_history_buffer))
        # Multi-grid plot state
        self._plot_panels: List[PlotPanel] = []   # one entry per subplot cell
        self._gl_widget = None                     # pg.GraphicsLayoutWidget
        self._plot_widget = None                   # alias → panels[0].plot_item (compat)
        self._plot_curves: Dict = {}               # compat shim (unused after refactor)
        self._plot_keys: List[Tuple[int, str]] = []  # union of all panel keys
        self._curve_icon_cache: Dict[Tuple[int, str, str], QIcon] = {}
        self._session_started = datetime.now()
        self._plot_time_mode = str(self._settings.value("plot/time_mode", "elapsed"))
        if self._plot_time_mode not in ("elapsed", "clock"):
            self._plot_time_mode = "elapsed"
        self._plot_palette = _PLOT_PALETTE_DARK
        self._plot_redraw_interval_s = 1.0 / 30.0
        self._plot_last_redraw = 0.0
        self._signal_unit_map: Dict[Tuple[int, str], str] = {}
        self._signal_group_map: Dict[Tuple[int, str], str] = {}
        self._plot_y_range_pending: Dict[int, Tuple[float, float]] = {}
        self._plot_y_range_timers: Dict[int, QTimer] = {}
        # Logging session start — distinct from _session_started, which tracks
        # the app/config session. Set when Start Logging is pressed and used as
        # the t=0 reference for decoded log elapsed_ms and the metadata sheet.
        # We keep two: _log_started (wall clock, used only for the Metadata
        # sheet's "session_started" string) and _log_started_perf (monotonic,
        # used for elapsed_ms math). Mixing the two avoids backward jumps when
        # the system clock is corrected by NTP mid-session.
        self._log_started: Optional[datetime] = None
        self._log_started_perf: Optional[float] = None
        # Plot view mode: True = Live (auto-expand 0→now), False = Explore (user panned)
        self._plot_live: bool = True
        self._plot_range_changing: bool = False   # re-entrancy guard for setXRange calls


        # Packet queue + 60 Hz throttle timer
        # Bounded deque prevents OOM if the Qt event loop stalls (e.g. user
        # drags the window title bar for several seconds): oldest packets are
        # silently dropped rather than growing the list without bound.
        self._pending_packets: deque = deque(maxlen=10_000)
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(16)  # ~60 Hz
        self._ui_timer.timeout.connect(self._flush_ui)

        self._build_ui()
        self._load_default_config()
        self._refresh_action_state()
        # Rebuild icon tints after all widgets exist so secondary menu/toolbar
        # icons get the correct colour even without a manual theme switch.
        _saved_theme = str(self._settings.value("ui/theme", "dark"))
        self._rebuild_action_icons(_saved_theme)

        self._default_state = self.saveState()
        self._default_geometry = self.saveGeometry()
        self._restore_window_state()

        self._log_activity(f"[SESSION] Started {APP_DISPLAY_NAME} v{self._version}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_main_layout()

        self._led_label = QLabel("⬤")
        self._led_label.setStyleSheet("color: #ef5350;")
        self._led_label.setToolTip("Disconnected")
        self._status_label = QLabel("")
        self._counts_label = QLabel("")
        self._counts_label.setFont(QFont("Consolas", 9))
        self._counts_label.setStyleSheet("padding: 0 8px; letter-spacing: 0.5px;")
        bar = QStatusBar(self)
        bar.addWidget(self._led_label)
        bar.addWidget(self._status_label, 1)
        bar.addPermanentWidget(self._counts_label)
        self.setStatusBar(bar)

        # Subtle "card" styling for compact panels + dock + primary action.
        # Pick the right QSS set based on the saved theme preference.
        _saved_theme = str(self._settings.value("ui/theme", "dark"))
        self._apply_card_qss(_saved_theme)

    def _apply_card_qss(self, theme: str) -> None:
        """Install card + dock QSS.  Called on startup and on every theme switch.

        Key design note: ``qdarktheme`` applies its palette to the
        ``QApplication`` object, NOT to individual windows.  Therefore
        ``self.styleSheet()`` only ever contains *our* card rules, never the
        qdarktheme base.  We must set from scratch here (not append), otherwise
        dark overrides accumulate and leak into subsequent light-theme switches.

        Rules applied:
          - ``_QSS_BASE`` always — palette-relative rules for cards, menus, etc.
          - ``_QSS_DARK_OVERRIDES`` when ``theme == "dark"``  — explicit hex
            codes for dock titles, separators, table body, inputs.
          - ``_QSS_LIGHT_OVERRIDES`` when ``theme == "light"`` — same surfaces
            re-styled with explicit light hex codes.  Without this, qdarktheme's
            light palette propagation through QDockWidget::title is unreliable
            on Windows / PySide6 6.6+ and the dock titles ended up stuck on the
            previous dark colours.
        """
        self.setStyleSheet(build_card_qss(theme))


    def _build_actions(self) -> None:

        # All action icons follow the active theme tint. Primary actions
        # (Connect / Poll / Log) live in BOTH the toolbar (on a coloured
        # button background) AND the Device menu (on the regular menu
        # background), so a fixed white tint that looked great on the
        # toolbar made the same icons invisible in the Device menu under
        # light theme. The theme-tinted icon is readable in both contexts:
        #   dark menu bg + white icon  -> good
        #   light menu bg + dark icon  -> good
        #   green/yellow/pink button + white-or-dark icon -> still readable
        #     because the button colours are saturated (high contrast both ways).
        _saved_theme = str(self._settings.value("ui/theme", "dark"))
        _ic = "#F8FAFC" if _saved_theme == "dark" else "#1F2937"

        # Keyboard shortcuts are passed to setShortcut() so Qt automatically
        # renders them in the menu text (right-aligned) — users learn them by
        # opening the menu once. We avoid Ctrl+R because earlier builds bound
        # it to "Auto-Range Plot"; some users still hit it out of habit.
        self._connect_action = QAction(_icon("mdi6.usb-port", _ic), "Connect", self)
        self._connect_action.setShortcut(QKeySequence("F9"))
        self._connect_action.triggered.connect(self._on_toggle_connect)

        self._polling_action = QAction(_icon("mdi6.play-circle-outline", _ic), "Start Auto-Fetch", self)
        self._polling_action.setCheckable(True)
        self._polling_action.setChecked(False)
        self._polling_action.setShortcut(QKeySequence("F10"))
        self._polling_action.triggered.connect(self._on_toggle_polling)

        self._logging_action = QAction(_icon("mdi6.record-rec", _ic), "Start Logging", self)
        self._logging_action.setShortcut("Ctrl+L")
        self._logging_action.triggered.connect(self._on_toggle_logging)

        self._load_config_action = QAction(_icon("mdi6.folder-upload-outline", _ic), "Import Config", self)
        self._load_config_action.setShortcut(QKeySequence("Ctrl+O"))
        self._load_config_action.triggered.connect(self._on_load_config)

        self._export_template_action = QAction(_icon("mdi6.file-export-outline", _ic), "Export Template", self)
        self._export_template_action.setShortcut(QKeySequence("Ctrl+E"))
        self._export_template_action.triggered.connect(self._on_export_template)

        self._load_log_action = QAction(_icon("mdi6.history", _ic), "Load Raw Log", self)
        self._load_log_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self._load_log_action.triggered.connect(self._on_load_log)

        self._clear_action = QAction(_icon("mdi6.broom", _ic), "Clear Console / Log", self)
        self._clear_action.setShortcut(QKeySequence("Ctrl+K"))
        self._clear_action.triggered.connect(self._on_clear)

        self._copy_value_action = QAction(_icon("mdi6.content-copy", _ic), "Copy Value", self)
        self._copy_value_action.setShortcut("Ctrl+Shift+C")
        self._copy_value_action.triggered.connect(self._on_copy_value)

        self._exit_action = QAction(_icon("mdi6.exit-to-app", _ic), "Exit", self)
        self._exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._exit_action.triggered.connect(self.close)

        self._info_action = QAction(_icon("mdi6.information-outline", _ic), "About Bytehound", self)
        self._info_action.triggered.connect(self._on_info)

        self._docs_action = QAction(_icon("mdi6.book-open-page-variant-outline", _ic), "View Documentation", self)
        self._docs_action.setShortcut(QKeySequence("F1"))
        self._docs_action.triggered.connect(self._on_view_docs)

        self._update_action = QAction(_icon("mdi6.cloud-download-outline", _ic), "Check for Updates", self)
        self._update_action.triggered.connect(self._on_check_updates)

        # chart-multiple distinguishes the offline "Analysis Suite" (which
        # overlays many recordings) from the Live Plot panel which uses
        # plain chart-line.
        self._analysis_action = QAction(_icon("mdi6.chart-multiple", _ic), "Analysis Suite", self)
        self._analysis_action.setShortcut(QKeySequence("Ctrl+T"))
        self._analysis_action.triggered.connect(self._on_analysis_suite)

        self._logging_settings_action = QAction(_icon("mdi6.tune-vertical", _ic), "Logging Settings...", self)
        self._logging_settings_action.triggered.connect(self._on_logging_settings)


    def _build_menus(self) -> None:
        menubar = self.menuBar()

        # Add a thin separator line between each top-level menu so the
        # menu bar reads  File | Edit | View | Device | Tools | Help
        def _add_sep():
            menubar.addSeparator()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._load_config_action)
        file_menu.addAction(self._export_template_action)
        file_menu.addSeparator()
        file_menu.addAction(self._load_log_action)
        file_menu.addSeparator()
        file_menu.addAction(self._exit_action)
        _add_sep()

        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self._copy_value_action)
        edit_menu.addAction(self._clear_action)
        _add_sep()

        self._view_menu = menubar.addMenu("&View")
        _add_sep()

        device_menu = menubar.addMenu("&Device")
        device_menu.addAction(self._connect_action)
        device_menu.addAction(self._polling_action)
        device_menu.addAction(self._logging_action)
        _add_sep()

        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self._analysis_action)
        tools_menu.addAction(self._logging_settings_action)
        _add_sep()

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._docs_action)
        help_menu.addAction(self._update_action)
        help_menu.addSeparator()
        help_menu.addAction(self._info_action)

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

    def _on_analysis_suite(self) -> None:
        self._log_activity("[ACTION] Open Analysis Suite")
        if not hasattr(self, "_analysis_window") or self._analysis_window is None:
            from .analysis_suite import AnalysisSuiteWindow
            self._analysis_window = AnalysisSuiteWindow(self)
        self._analysis_window.show()
        self._analysis_window.raise_()
        self._analysis_window.activateWindow()

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

    def _on_copy_value(self) -> None:
        indexes = self._table.selectedIndexes()
        if indexes:
            row = indexes[0].row()
            text = self._table_model.cell_text(row, 6)  # col 6 = Value
            if text:
                QApplication.clipboard().setText(text)
                self._log_activity(f"[ACTION] Copy value: {text}")

    def _on_info(self) -> None:
        import json as _json
        _vpath = Path(__file__).resolve().parents[2] / "version.json"
        try:
            _v = _json.loads(_vpath.read_text(encoding="utf-8"))
        except Exception:
            _v = {}
        version    = _v.get("version",    self._version)
        developer  = _v.get("Developer",  "Shreyas P")
        build_date = _v.get("build_date", "")
        license_   = _v.get("license",    "MIT")
        homepage   = _v.get("homepage",   "")
        issue_url  = _v.get("issue_url",  "")

        lines = [
            f"<b>{APP_DISPLAY_NAME}</b>",
            "",
            f"Version:&nbsp;&nbsp;&nbsp;{version}",
            f"Developer:&nbsp;{developer}",
        ]
        if build_date:
            lines.append(f"Build Date:&nbsp;{build_date}")
        lines += [
            "",
            "Serial Data Logger and Visualizer.",
            "Configuration-driven decoding.",
            "",
            f"Released under the {license_} License.",
        ]
        if homepage or issue_url:
            lines.append("")
            if homepage:
                lines.append(f'<a href="{homepage}">View on GitHub</a>')
            if issue_url:
                lines.append(f'<a href="{issue_url}">Report an Issue</a>')

        self._popup_about("About Bytehound", "<br>".join(lines))

    def _on_view_docs(self) -> None:
        self._log_activity("[ACTION] View documentation")
        docs_path = Path(__file__).resolve().parents[1] / "resources" / "index.html"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(docs_path)))

    def _on_show_config_info(self) -> None:
        """View → Config Info… — shows current config, protocol and logging state."""
        self._log_activity("[ACTION] Open Config Info dialog")
        dlg = QDialog(self)
        dlg.setWindowTitle("Config Info")
        dlg.setMinimumWidth(420)
        root = QVBoxLayout(dlg)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        def _row(lbl: str, val: str) -> None:
            v = QLabel(val)
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(lbl, v)

        _row("Config file:", self._config_label.text())
        _row("Protocol:", self._protocol_label.text())
        _row("Frames:", self._frames_label.text())
        _row("Logging:", self._logging_label.text())

        root.addLayout(form)

        btn_row = QDialogButtonBox()
        open_log_btn = QPushButton("📂  Open Log Folder")
        open_log_btn.clicked.connect(self._on_open_log_folder)
        btn_row.addButton(open_log_btn, QDialogButtonBox.ButtonRole.ActionRole)
        btn_row.addButton(QDialogButtonBox.StandardButton.Close)
        btn_row.rejected.connect(dlg.reject)
        root.addWidget(btn_row)

        dlg.exec()

    def _on_logging_settings(self) -> None:
        self._log_activity("[ACTION] Open Logging Settings dialog")
        dlg = LoggingSettingsDialog(self._settings, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        level_name, flush_interval = dlg.get_values()
        self._apply_logging_level(level_name)
        if self._raw_logger:
            self._raw_logger.set_flush_interval(flush_interval)
        if self._decoded_logger:
            self._decoded_logger.set_flush_interval(flush_interval)
        self._set_status(
            f"Logging settings updated: level {level_name}, flush {flush_interval:.2f}s"
        )
        self._log_activity(
            f"[ACTION] Logging settings updated: level {level_name}, flush {flush_interval:.2f}s"
        )

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toolbar = toolbar

        # --- Secondary actions (file / log) ---
        toolbar.addAction(self._load_config_action)
        toolbar.addAction(self._export_template_action)
        toolbar.addSeparator()
        toolbar.addAction(self._load_log_action)
        toolbar.addSeparator()

        # --- Primary actions: Connect, Poll, Log ---
        # Icons are always white because these buttons always have a
        # coloured background (green / yellow / pink).  We don't use
        # #primaryAction QSS for these — we drive their colour via
        # _style_action_btn() so states (connected, fetching, logging)
        # can have distinct colours.
        toolbar.addAction(self._connect_action)
        toolbar.addAction(self._polling_action)
        toolbar.addAction(self._logging_action)

        for action in (self._connect_action, self._polling_action, self._logging_action):
            btn = toolbar.widgetForAction(action)
            if isinstance(btn, QToolButton):
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        # Set initial button colours before any connection is made.
        self._style_action_btn(self._connect_action,  _BTN_GREEN)   # idle → green
        self._style_action_btn(self._polling_action,  _BTN_GREEN)   # idle → green
        self._style_action_btn(self._logging_action,  _BTN_YELLOW)  # idle → yellow

        toolbar.addSeparator()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self._logo_button = QPushButton()
        self._logo_button.setIcon(QIcon(str(Path(__file__).resolve().parents[2] / "logo_rec.png")))
        self._logo_button.setFlat(True)
        toolbar.addWidget(self._logo_button)

        self.addToolBar(toolbar)

    def _style_action_btn(self, action: "QAction", bg: str) -> None:
        """Colour a primary toolbar button with *bg* and always-white text/icon.

        Three semantic states drive the three distinct colours:
          ``_BTN_GREEN``  — idle / safe to activate (Connect, Start Auto-Fetch)
          ``_BTN_YELLOW`` — ready but not started (Start Logging)
          ``_BTN_PINK``   — currently active / click to stop
        """
        if not hasattr(self, "_toolbar"):
            return
        btn = self._toolbar.widgetForAction(action)
        if not isinstance(btn, QToolButton):
            return
        btn.setStyleSheet(
            f"""
            QToolButton {{
                background-color: {bg};
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 4px 14px;
                font-weight: 700;
            }}
            QToolButton:hover   {{ background-color: {bg}; }}
            QToolButton:pressed {{ background-color: {bg}; }}
            QToolButton:disabled {{
                background-color: {bg};
                color: #AAAAAA;
                border: 2px dashed #AAAAAA;
            }}
            """
        )

    def _build_main_layout(self) -> None:
        self.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)

        self._table_model = TelemetryTableModel(self)
        self._table = QTableView(self)
        self._table.setModel(self._table_model)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setFont(QFont("Consolas", 10))
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._status_delegate = _StatusBadgeDelegate(self._table, settings=self._settings)
        self._table.setItemDelegateForColumn(8, self._status_delegate)
        for index, (_, width) in enumerate(_MODEL_COLUMNS):
            self._table.setColumnWidth(index, width)

        center_widget = QWidget(self)
        center_widget.setObjectName("centralPanel")
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(12, 12, 12, 12)

        top_row = QHBoxLayout()
        self._search_input = QLineEdit(center_widget)
        self._search_input.setPlaceholderText("Search / Filter variables...")

        self._group_combo = _CheckableGroupCombo(center_widget)
        self._group_combo.selection_changed.connect(self._apply_group_filter)

        self._show_calcs_check = QCheckBox("Show calculations", center_widget)
        self._show_calcs_check.setChecked(True)
        self._show_calcs_check.toggled.connect(self._apply_group_filter)

        self._search_input.textChanged.connect(self._apply_group_filter)

        top_row.addWidget(self._search_input, 1)
        top_row.addWidget(QLabel("Group", center_widget))
        top_row.addWidget(self._group_combo)
        top_row.addWidget(self._show_calcs_check)

        # Config/logging status labels — kept as hidden attributes so
        # _refresh_config_status / logging helpers can still update their text.
        # Visible via View → Config Info...
        self._config_label = QLabel("No config loaded")
        self._protocol_label = QLabel("-")
        self._frames_label = QLabel("-")
        self._logging_label = QLabel("Logging: stopped")
        self._open_log_btn = QPushButton("\U0001f4c2")
        self._open_log_btn.setToolTip("Open Log Folder")
        self._open_log_btn.clicked.connect(self._on_open_log_folder)

        center_layout.addLayout(top_row)
        center_layout.addWidget(self._table)

        self.setCentralWidget(center_widget)

        # Connection dock REMOVED — Connect button opens ConnectionDialog popup.
        # Poll Configure accessible via Device menu.
        # Config/logging status shown in the central info bar.

        # ── Right column: tabbed panels (top) ─────────────────────────────
        self._plot_dock = QDockWidget("Live Plot", self)
        self._plot_dock.setObjectName("PlotDock")
        self._plot_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._plot_dock.setWidget(self._build_plot_tab())
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._plot_dock)

        self._bitfields_dock = QDockWidget("Bitfields", self)
        self._bitfields_dock.setObjectName("BitfieldsDock")
        self._bitfields_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._bitfields_dock.setWidget(self._build_bitfield_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._bitfields_dock)

        self._enums_dock = QDockWidget("Enums", self)
        self._enums_dock.setObjectName("EnumsDock")
        self._enums_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._enums_dock.setWidget(self._build_enum_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._enums_dock)
        self.tabifyDockWidget(self._bitfields_dock, self._enums_dock)

        self._tx_dock = QDockWidget("TX Commands", self)
        self._tx_dock.setObjectName("TxDock")
        self._tx_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._tx_dock.setWidget(self._build_tx_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tx_dock)
        self.tabifyDockWidget(self._bitfields_dock, self._tx_dock)

        self._editor_dock = QDockWidget("Parameter Editor", self)
        self._editor_dock.setObjectName("EditorDock")
        self._editor_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._editor_dock.setWidget(self._build_editor_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._editor_dock)
        self.tabifyDockWidget(self._bitfields_dock, self._editor_dock)

        self._tx_dock.raise_()

        # Build the left-panel widgets (recent config combo, poll list, etc.)
        # without attaching them to a dock — they are accessed by other methods.
        self._build_left_panel()

        # ── Logs: bottom-right, split below the panel tabs ─────────────────
        self._console = QPlainTextEdit(self)
        self._console.setReadOnly(True)
        self._console.setPlaceholderText("Raw RX/TX frames will appear here...")
        self._console.setMaximumBlockCount(3000)
        self._console.setFont(QFont("Consolas", 10))

        self._console_dock = QDockWidget("Raw Console", self)
        self._console_dock.setObjectName("ConsoleDock")
        self._console_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        self._console_dock.setWidget(self._console)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._console_dock)

        self._activity_log = QPlainTextEdit(self)
        self._activity_log.setReadOnly(True)
        self._activity_log.setPlaceholderText("Application activity will appear here...")
        self._activity_log.setMaximumBlockCount(5000)
        self._activity_log.setFont(QFont("Consolas", 10))

        self._activity_dock = QDockWidget("Activity Log", self)
        self._activity_dock.setObjectName("ActivityDock")
        self._activity_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        self._activity_dock.setWidget(self._activity_log)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._activity_dock)
        self.tabifyDockWidget(self._console_dock, self._activity_dock)
        self._activity_dock.raise_()

        # NOTE: splitDockWidget is deferred to showEvent — Qt ignores it
        # during __init__ before the window geometry is finalised.


        for dock in (
            self._plot_dock,
            self._bitfields_dock,
            self._enums_dock,
            self._tx_dock,
            self._editor_dock,
            self._console_dock,
            self._activity_dock,
        ):
            _pad_dock_content(dock)

        self._populate_view_menu()

    def _populate_view_menu(self) -> None:
        menu = self._view_menu
        menu.clear()
        theme = str(self._settings.value("ui/theme", "dark"))
        ic = "#F8FAFC" if theme == "dark" else "#1F2937"

        # Each toggle gets a distinctive Material Design icon that hints at
        # the panel's content. Without these the Panels submenu was a wall
        # of plain-text toggles indistinguishable at a glance.
        panels_menu = menu.addMenu(_icon("mdi6.view-quilt-outline", ic), "Panels")
        for dock, label, dock_icon in (
            (self._plot_dock,       "Live Plot",        "mdi6.chart-line"),
            (self._bitfields_dock,  "Bitfields",        "mdi6.toggle-switch-outline"),
            (self._enums_dock,      "Enums",            "mdi6.format-list-bulleted-type"),
            (self._tx_dock,         "TX Commands",      "mdi6.send-outline"),
            (self._editor_dock,     "Parameter Editor", "mdi6.tune-vertical"),
            (self._console_dock,    "Raw Console",      "mdi6.console-line"),
            (self._activity_dock,   "Activity Log",     "mdi6.text-box-outline"),
        ):
            action = dock.toggleViewAction()
            action.setText(label)
            action.setIcon(_icon(dock_icon, ic))
            panels_menu.addAction(action)

        # Reset Window Layout sits directly under Panels — that's where users
        # look when they've accidentally dragged a dock and want to recover.
        # Ctrl+Shift+R shortcut surfaces in the menu text automatically.
        reset_layout_action = QAction(_icon("mdi6.view-grid-outline", ic), "Reset Window Layout", self)
        reset_layout_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        reset_layout_action.triggered.connect(self._reset_window_layout)
        menu.addAction(reset_layout_action)

        menu.addSeparator()
        # Use file-cog so this is visually distinct from "About Bytehound"
        # which uses information-outline.
        config_info_action = QAction(_icon("mdi6.file-cog-outline", ic), "Config Info\u2026", self)
        config_info_action.triggered.connect(self._on_show_config_info)
        menu.addAction(config_info_action)

        theme_menu = menu.addMenu(_icon("mdi6.palette-outline", ic), "Theme")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        current_theme = str(self._settings.value("ui/theme", "dark"))
        for label, key, icon_name in (
            ("Dark",   "dark",  "mdi6.weather-night"),
            ("Light",  "light", "mdi6.weather-sunny"),
            ("System", "auto",  "mdi6.theme-light-dark"),
        ):
            action = QAction(_icon(icon_name, ic), label, self, checkable=True)
            action.setData(key)
            action.setChecked(key == current_theme)
            action.triggered.connect(lambda _checked=False, k=key: self._apply_theme(k))
            self._theme_group.addAction(action)
            theme_menu.addAction(action)

    def _apply_theme(self, theme: str) -> None:
        if qdarktheme is None:
            return
        try:
            qdarktheme.setup_theme(theme, corner_shape="rounded")
        except Exception as exc:
            self._popup_warning("Theme", f"Failed to apply theme: {exc}")
            return
        # Persist the new theme BEFORE rebuilding any UI that reads it back
        # from QSettings. _rebuild_action_icons -> _populate_view_menu reads
        # the saved value to decide its icon tint; without this ordering,
        # the View submenu stayed on the previous theme's tint until the
        # NEXT theme change.
        self._settings.setValue("ui/theme", theme)
        # Re-apply our card + dark-override QSS on top of the fresh qdarktheme base.
        self._apply_card_qss(theme)
        # Rebuild qtawesome icons with the correct tint for the new theme.
        self._rebuild_action_icons(theme)
        # Repaint the pyqtgraph canvas — it is not a QWidget child so it does
        # not pick up the QPalette change automatically.
        self._apply_plot_theme(theme)
        # Forward theme change to the Analysis Suite if it's open — it's a
        # separate top-level window so QSS doesn't cascade into it.
        analysis = getattr(self, "_analysis_window", None)
        if analysis is not None and hasattr(analysis, "apply_theme"):
            try:
                analysis.apply_theme(theme)
            except Exception:
                pass
        from PySide6.QtWidgets import QApplication
        # Schedule title-bar update via singleShot so the native HWND is stable.
        dark = (theme == "dark")
        for w in QApplication.topLevelWidgets():
            QTimer.singleShot(0, lambda _w=w, _d=dark: _apply_windows_dark_titlebar(_w, _d))
        # Status-badge colours come from a custom delegate that reads the
        # current theme on every paint. Force a repaint of the table viewport
        # so the badges pick up the new colour pair immediately, without
        # waiting for the next data tick.
        if hasattr(self, "_table") and self._table is not None:
            self._table.viewport().update()
        self._set_status(f"Theme: {theme}")
        # Invalidate the cached toast so it picks up new theme colours.
        if hasattr(self, "_toast_label") and self._toast_label is not None:
            self._toast_label.deleteLater()
            self._toast_label = None
        # Theme switches were previously a status-bar update only — almost
        # invisible. The toast confirms the switch landed.
        self._toast(f"Theme: {theme.title()}")
        self._log_activity(f"[ACTION] Theme changed to {theme}")

    def _apply_plot_theme(self, theme: str) -> None:
        """Tint the pyqtgraph canvas + axis labels for the active theme."""
        if pg is None or not hasattr(self, "_gl_widget"):
            return
        if theme == "dark":
            bg = "#1E293B"          # match QDockWidget body — same Slate
            axis = "#CBD5E1"        # high-contrast on dark
            self._plot_palette = _PLOT_PALETTE_DARK
        else:
            bg = "#FFFFFF"
            axis = "#475569"        # readable on light
            self._plot_palette = _PLOT_PALETTE_LIGHT
        self._gl_widget.setBackground(pg.mkColor(bg))
        crosshair_pen = self._plot_crosshair_pen(theme)
        # Repaint the axis lines + tick labels on every existing PlotItem.
        for panel in getattr(self, "_plot_panels", []):
            plot = getattr(panel, "plot_item", None)
            if plot is None:
                continue
            for ax_name in ("left", "bottom", "right", "top"):
                ax = plot.getAxis(ax_name)
                if ax is not None:
                    ax.setPen(pg.mkPen(axis))
                    ax.setTextPen(pg.mkPen(axis))
            if getattr(panel, "legend", None) is not None:
                self._style_plot_legend(panel.legend, theme)
            if getattr(panel, "vline", None) is not None:
                panel.vline.setPen(crosshair_pen)
            if getattr(panel, "hline", None) is not None:
                panel.hline.setPen(crosshair_pen)
        if hasattr(self, "_panel_strip_layout") and self._panel_strip_layout is not None:
            self._rebuild_panel_strips()
        self._redraw_plot()

    def _current_plot_palette(self) -> Tuple[str, ...]:
        return getattr(self, "_plot_palette", _PLOT_PALETTE_DARK)

    def _plot_time_axis_label(self) -> str:
        if self._plot_time_mode == "clock":
            return "Time (HH:MM:SS)"
        return "Time (s, since connect)"

    def _format_plot_time(self, seconds: float) -> str:
        if self._plot_time_mode == "clock":
            base = self._session_started or datetime.now()
            if not math.isfinite(seconds):
                return ""
            return (base + timedelta(seconds=seconds)).strftime("%H:%M:%S")
        return _format_elapsed_time(seconds)

    def _plot_crosshair_pen(self, theme: str):
        if pg is None:
            return QPen()
        color = "#94A3B8" if theme == "dark" else "#64748B"
        return pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)

    def _style_plot_legend(self, legend, theme: str) -> None:
        if pg is None or legend is None:
            return
        if theme == "dark":
            bg = QColor(15, 23, 42, 160)
            border = "#475569"
        else:
            bg = QColor(255, 255, 255, 180)
            border = "#CBD5E1"
        legend.setBrush(pg.mkBrush(bg))
        legend.setPen(pg.mkPen(border, width=1))

    def _on_plot_time_mode_changed(self, idx: int) -> None:
        mode = "elapsed" if idx == 0 else "clock"
        self._apply_plot_time_mode(mode, persist=True)

    def _apply_plot_time_mode(self, mode: str, *, persist: bool = True) -> None:
        if mode not in ("elapsed", "clock"):
            mode = "elapsed"
        self._plot_time_mode = mode
        if persist:
            self._settings.setValue("plot/time_mode", mode)
        label = self._plot_time_axis_label()
        for panel in getattr(self, "_plot_panels", []):
            axis = getattr(panel, "time_axis", None) or panel.plot_item.getAxis("bottom")
            if hasattr(axis, "set_mode"):
                axis.set_mode(mode)
            if hasattr(axis, "set_session_start"):
                axis.set_session_start(self._session_started)
            panel.plot_item.setLabel("bottom", label)
        self._redraw_plot()

    def _on_plot_mode_clicked(self) -> None:
        if not self._plot_live:
            self._set_plot_live(True, source="button")
            self._redraw_plot()

    def _on_plot_y_range_changed(self, panel_idx: int, y_range) -> None:
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        if panel.auto_fit_y:
            return
        if not y_range or len(y_range) != 2:
            return
        try:
            y0, y1 = float(y_range[0]), float(y_range[1])
        except (TypeError, ValueError):
            return
        self._plot_y_range_pending[panel_idx] = (y0, y1)
        timer = self._plot_y_range_timers.get(panel_idx)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda i=panel_idx: self._persist_plot_y_range(i))
            self._plot_y_range_timers[panel_idx] = timer
        timer.start(500)

    def _persist_plot_y_range(self, panel_idx: int) -> None:
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        if panel.auto_fit_y:
            return
        pending = self._plot_y_range_pending.get(panel_idx)
        if pending is None:
            return
        self._settings.setValue(f"plot/panel/{panel_idx}/y_range", [pending[0], pending[1]])

    def _read_saved_y_range(self, panel_idx: int) -> Optional[Tuple[float, float]]:
        raw = self._settings.value(f"plot/panel/{panel_idx}/y_range", None)
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            try:
                return float(raw[0]), float(raw[1])
            except (TypeError, ValueError):
                return None
        return None

    def _clear_saved_y_ranges(self) -> None:
        self._settings.beginGroup("plot")
        try:
            for key in list(self._settings.allKeys()):
                if key.startswith("panel/") and key.endswith("/y_range"):
                    self._settings.remove(key)
        finally:
            self._settings.endGroup()
        for timer in self._plot_y_range_timers.values():
            timer.stop()
        self._plot_y_range_timers.clear()
        self._plot_y_range_pending.clear()

    def _reset_panel_view(self, panel_idx: int, *, resume_live: bool = False) -> None:
        if pg is None or panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        vb = panel.plot_item.getViewBox()
        if vb is None:
            return
        if panel.auto_fit_y:
            vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        else:
            y_range = self._read_saved_y_range(panel_idx)
            if y_range is not None:
                vb.setYRange(y_range[0], y_range[1], padding=0)
        if resume_live and not self._plot_live:
            self._set_plot_live(True, source="reset")
        self._redraw_plot()

    def _clear_panel_history(self, panel_idx: int) -> None:
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        span = None
        for key in panel.assigned_keys:
            buf = self._plot_history.get(key)
            if not buf:
                continue
            xs = buf[0]
            if len(xs) > 1:
                key_span = float(xs[-1]) - float(xs[0])
                if span is None or key_span > span:
                    span = key_span
        if span is not None and span > 30.0:
            choice = QMessageBox.question(
                self,
                "Clear Plot History",
                "This will clear more than 30 seconds of data for this panel. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        for key in panel.assigned_keys:
            buf = self._plot_history.get(key)
            if buf:
                buf[0].clear()
                buf[1].clear()
        if hasattr(self, "_hover_cache"):
            self._hover_cache.clear()
        self._redraw_plot()

    def _rebuild_action_icons(self, theme: str) -> None:
        """Re-tint all QAction icons to match the current theme.

        qtawesome bakes the color into the QPixmap at icon() creation time, so
        we must recreate the icons whenever the theme changes.

        Every action — primary (Connect / Poll / Log) and secondary
        (File / Edit / Help) — follows the active theme tint. We used to
        pin primary icons to white because they sat on coloured toolbar
        buttons, but the same QAction also lives in the Device menu where
        a fixed white icon vanishes against a light-theme menu background.
        Theme-tinted icons read well in both places.
        """
        color = "#F8FAFC" if theme == "dark" else "#1F2937"

        # Primary AND secondary actions all use the theme tint.
        for action, name in [
            (self._connect_action,  "mdi6.usb-port"),
            (self._polling_action,  "mdi6.play-circle-outline"),
            (self._logging_action,  "mdi6.record-rec"),
        ]:
            action.setIcon(_icon(name, color))

        # Secondary: follow the active theme
        for action, name in [
            (self._load_config_action,      "mdi6.folder-upload-outline"),
            (self._export_template_action,  "mdi6.file-export-outline"),
            (self._load_log_action,         "mdi6.history"),
            (self._clear_action,            "mdi6.broom"),
            (self._copy_value_action,       "mdi6.content-copy"),
            (self._exit_action,             "mdi6.exit-to-app"),
            (self._info_action,             "mdi6.information-outline"),
            (self._analysis_action,         "mdi6.chart-multiple"),
            (self._logging_settings_action, "mdi6.tune-vertical"),
            # Names MUST match the icons used at QAction construction in
            # _create_actions(); otherwise the menu icon silently changes
            # shape the first time the user switches theme.
            (self._docs_action,             "mdi6.book-open-page-variant-outline"),
            (self._update_action,           "mdi6.cloud-download-outline"),
        ]:
            action.setIcon(_icon(name, color))

        # View menu is rebuilt from scratch each time — call it with the new tint
        self._populate_view_menu()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        theme = str(self._settings.value("ui/theme", "dark"))
        QTimer.singleShot(0, lambda: _apply_windows_dark_titlebar(self, dark=(theme == "dark")))
        # Split right column after the window is fully shown so Qt honours it.
        if not self._settings.value("window/state"):  # only on first launch
            QTimer.singleShot(50, self._apply_default_dock_split)

    def _apply_default_dock_split(self) -> None:
        """Split right column: panels top, logs bottom. Called once on first show."""
        self.splitDockWidget(self._bitfields_dock, self._console_dock, Qt.Orientation.Vertical)
        # Give logs ~35% of the right column height
        h = self.height()
        self.resizeDocks(
            [self._bitfields_dock, self._console_dock],
            [int(h * 0.65), int(h * 0.35)],
            Qt.Orientation.Vertical,
        )
        self._tx_dock.raise_()
        self._activity_dock.raise_()

    def _reset_window_layout(self) -> None:
        self._log_activity("[ACTION] Reset window layout")
        self.restoreGeometry(self._default_geometry)
        self.restoreState(self._default_state)
        for dock in (
            self._plot_dock,
            self._bitfields_dock,
            self._enums_dock,
            self._tx_dock,
            self._editor_dock,
            self._console_dock,
            self._activity_dock,
        ):
            dock.setVisible(True)
        self._toolbar.setVisible(True)
        self._toast("Window layout reset")

    def _save_window_state(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/state", self.saveState())

    def _restore_window_state(self) -> None:
        geometry = self._settings.value("window/geometry")
        state = self._settings.value("window/state")
        if geometry:
            self.restoreGeometry(geometry)
            # Clamp to the current screen's available area (excludes taskbar).
            # This prevents QWindowsWindow::setGeometry warnings when the saved
            # geometry came from a larger monitor or a previous HiDPI session.
            from PySide6.QtWidgets import QApplication
            screen = self.screen() or QApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                geo = self.frameGeometry()
                new_w = min(geo.width(),  available.width())
                new_h = min(geo.height(), available.height())
                new_x = max(available.x(), min(geo.x(), available.right()  - new_w))
                new_y = max(available.y(), min(geo.y(), available.bottom() - new_h))
                self.setGeometry(new_x, new_y, new_w, new_h)
        if state:
            self.restoreState(state)

    def _card(self, title: str, parent: QWidget) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(parent)
        frame.setProperty("card", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        title_label = QLabel(title, frame)
        title_label.setProperty("cardTitle", True)
        layout.addWidget(title_label)
        return frame, layout

    def _build_left_panel(self) -> None:
        """Initialise sidebar-only widgets (not visible anywhere in the UI).
        These attributes are read by _on_load_recent_config, _populate_polling_list, etc.
        """
        self._recent_config_combo = QComboBox()
        self._recent_config_combo.setMinimumWidth(120)

        self._poll_status_label = QLabel("No targets loaded")
        self._poll_status_label.setWordWrap(True)

        self._polling_list = QListWidget()
        self._polling_list.setMaximumHeight(130)
        self._polling_list.setEnabled(False)

    def _build_plot_tab(self) -> QWidget:
        outer = QWidget(self)
        root_layout = QVBoxLayout(outer)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        # ── Top control bar ────────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(8)

        hint = QLabel("Right-click a row → Add to Plot   ·   Space = Pause/Live")
        hint.setEnabled(False)
        hint.setStyleSheet("font-size: 11px;")
        controls.addWidget(hint)
        controls.addStretch(1)

        # Hover readout — shows time + value(s) under the mouse on any subplot.
        # Fixed-width so the controls bar doesn't reflow when text changes.
        self._hover_label = QLabel("", outer)
        self._hover_label.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "color: palette(text); padding: 0 6px;"
        )
        self._hover_label.setMinimumWidth(280)
        self._hover_label.setMaximumWidth(420)
        self._hover_label.setToolTip("Time and signal values under the mouse cursor.")
        controls.addWidget(self._hover_label)

        controls.addWidget(QLabel("Layout:"))
        self._layout_combo = QComboBox(outer)
        self._layout_combo.addItems(list(GRID_LAYOUTS.keys()))
        saved_layout = str(self._settings.value("plot/layout", "2×1")).lower().replace("x", "×")
        self._layout_combo.setCurrentText(saved_layout if saved_layout in GRID_LAYOUTS else "2×1")
        self._layout_combo.currentTextChanged.connect(self._on_layout_changed)
        controls.addWidget(self._layout_combo)

        controls.addWidget(QLabel("Time:"))
        self._time_mode_combo = QComboBox(outer)
        self._time_mode_combo.addItems(["Elapsed", "Clock"])
        self._time_mode_combo.setCurrentIndex(0 if self._plot_time_mode == "elapsed" else 1)
        self._time_mode_combo.setToolTip("Elapsed (mm:ss) or wall-clock (HH:MM:SS) axis labels.")
        self._time_mode_combo.currentIndexChanged.connect(self._on_plot_time_mode_changed)
        controls.addWidget(self._time_mode_combo)

        # Pause / Live toggle — checkable, color-coded so users see the
        # current mode at a glance. Clicking Live also re-fits Y auto-range
        # and snaps X back to (0, now), so it doubles as a reset.
        self._pause_btn = QPushButton("⏸ Pause", outer)
        self._pause_btn.setCheckable(True)
        self._pause_btn.setToolTip(
            "Pause: freeze the x-axis at the current view (Space).\n"
            "Live:  scroll the x-axis to keep up with new data."
        )
        self._pause_btn.toggled.connect(self._on_pause_toggled)
        self._pause_btn.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self._restyle_pause_btn(False)
        controls.addWidget(self._pause_btn)

        self._plot_mode_btn = QToolButton(outer)
        self._plot_mode_btn.setAutoRaise(True)
        self._plot_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plot_mode_btn.setToolTip(
            "Live: X-axis always shows the full session from t=0 to now.\n"
            "Explore: You panned or zoomed — view is frozen.\n"
            "Click to resume Live."
        )
        self._plot_mode_btn.clicked.connect(self._on_plot_mode_clicked)
        controls.addWidget(self._plot_mode_btn)

        # Session clock — updates every second via _flush_ui
        self._session_clock_label = QLabel("⏱ 0:00:00", outer)
        self._session_clock_label.setToolTip("Elapsed time since session start (or last config load).")
        # palette(placeholderText) sits between palette(text) and palette(mid):
        # it's designed as readable-but-secondary text in both Qt-supplied and
        # qdarktheme palettes. palette(mid) was nearly invisible on some light
        # themes, palette(text) reads as primary content. This strikes the
        # right "auxiliary readout" weight on dark AND light.
        self._session_clock_label.setStyleSheet(
            "font-size:11px; color: palette(placeholderText); padding-left:8px;"
        )
        self._session_clock_label.setMinimumWidth(70)
        controls.addWidget(self._session_clock_label)

        # Update-rate readout — packets/sec coming in. Computed by _flush_ui.
        self._rate_label = QLabel("0 Hz", outer)
        self._rate_label.setStyleSheet(
            "font-size:11px; color: palette(placeholderText); padding-left:8px;"
        )
        self._rate_label.setMinimumWidth(50)
        self._rate_label.setToolTip("Incoming packet rate (averaged over the last second).")
        controls.addWidget(self._rate_label)

        root_layout.addLayout(controls)

        if pg is None:
            root_layout.addWidget(QLabel("pyqtgraph is not installed."))
            self._gl_widget = None
            self._panel_strip_container = None
            return outer

        # ── Per-panel variable-strip container ─────────────────────────────
        # Strips live in a QWidget ABOVE the GraphicsLayoutWidget because
        # pg.GraphicsLayoutWidget is an OpenGL canvas and cannot host Qt widgets.
        self._panel_strip_container = QWidget(outer)
        self._panel_strip_layout = QHBoxLayout(self._panel_strip_container)
        self._panel_strip_layout.setContentsMargins(0, 0, 0, 0)
        self._panel_strip_layout.setSpacing(4)
        root_layout.addWidget(self._panel_strip_container)

        # ── Graphics canvas ────────────────────────────────────────────────
        self._gl_widget = pg.GraphicsLayoutWidget(outer)
        # The pyqtgraph canvas is not a QWidget child so qdarktheme does not
        # paint it; we tint it explicitly per theme. Re-applied on every
        # theme switch by _apply_plot_theme().
        self._apply_plot_theme(str(self._settings.value("ui/theme", "dark")))
        root_layout.addWidget(self._gl_widget, 1)

        # Build the initial grid from saved (or default) layout
        rows, cols = GRID_LAYOUTS.get(self._layout_combo.currentText(), (2, 1))
        self._rebuild_plot_grid(rows, cols, restore=True)
        self._set_plot_live(self._plot_live)

        return outer

    # ------------------------------------------------------------------
    # Grid management
    # ------------------------------------------------------------------

    def _rebuild_plot_grid(self, rows: int, cols: int, restore: bool = False) -> None:
        """Tear down the existing grid and build a fresh rows×cols layout.

        When *restore* is True, previously-assigned keys are loaded from
        QSettings (used on startup).  Otherwise assigned keys from the old
        panels are redistributed across new panels in order.
        """
        if pg is None or self._gl_widget is None:
            return

        # Collect previously assigned keys in panel order
        old_keys: List[List[Tuple[int, str]]] = [
            list(p.assigned_keys) for p in self._plot_panels
        ]
        flat_old: List[Tuple[int, str]] = [k for sub in old_keys for k in sub]

        # Clear graphics canvas and panel list
        self._gl_widget.clear()
        self._plot_panels.clear()

        # Drop any pending y-range debounce state — panel indexes are about
        # to be reassigned, so stale timers would fire against new panels.
        for timer in self._plot_y_range_timers.values():
            timer.stop()
        self._plot_y_range_timers.clear()
        self._plot_y_range_pending.clear()

        # Clear variable-strip widgets
        if hasattr(self, "_panel_strip_layout") and self._panel_strip_layout is not None:
            while self._panel_strip_layout.count():
                item = self._panel_strip_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        n = rows * cols
        # Determine assigned keys for each new panel
        if restore:
            panel_keys: List[List[Tuple[int, str]]] = []
            for i in range(n):
                raw = self._settings.value(f"plot/panel/{i}/keys", [])
                if isinstance(raw, list):
                    # QSettings serialises all values as strings; cast frame_id back to int.
                    decoded = [
                        (int(k[0]), str(k[1]))
                        for k in raw
                        if isinstance(k, (list, tuple)) and len(k) == 2
                    ]
                else:
                    decoded = []
                panel_keys.append(decoded)
        else:
            # Spread old keys: panel i gets old_keys[i] if it exists
            panel_keys = [old_keys[i] if i < len(old_keys) else [] for i in range(n)]

        # Build PlotItems and variable strips
        first_vb = None
        theme = str(self._settings.value("ui/theme", "dark"))
        axis_color = "#CBD5E1" if theme == "dark" else "#475569"
        border_color = "#334155" if theme == "dark" else "#CBD5E1"
        for idx in range(n):
            row_idx, col_idx = divmod(idx, cols)
            time_axis = _TimeAxisItem(
                mode=self._plot_time_mode,
                session_start=self._session_started,
            )
            pi = self._gl_widget.addPlot(
                row=row_idx,
                col=col_idx,
                axisItems={"bottom": time_axis},
            )
            pi.showGrid(x=True, y=True, alpha=0.15)
            pi.setLabel("bottom", self._plot_time_axis_label())
            legend = pi.addLegend(offset=(10, 10))
            legend.setLabelTextSize("8pt")
            self._style_plot_legend(legend, theme)
            vb = pi.getViewBox()
            vb.setMouseEnabled(x=True, y=True)
            vb.setDefaultPadding(0.04)   # gentle y-padding so curves don't touch the frame
            if getattr(vb, "menu", None) is not None:
                vb.menu.addSeparator()
                vb.menu.addAction("Reset View", lambda i=idx: self._reset_panel_view(i))
                vb.menu.addAction(
                    "Reset View && Resume Live",
                    lambda i=idx: self._reset_panel_view(i, resume_live=True),
                )
                vb.menu.addAction("Clear", lambda i=idx: self._clear_panel_history(i))
            # Card-style frame around each panel's view box so each subplot
            # has an unambiguous boundary on the dark/light canvas. Matches
            # the Analysis Suite's visual convention.
            vb.setBorder(pg.mkPen(border_color, width=1))
            # Internal padding so y-axis tick labels for big numbers and the
            # rotated y-title can't collide with the border.
            pi.layout.setContentsMargins(6, 6, 10, 6)
            # Pin a minimum width on the y-axis so the left edges of every
            # subplot in the grid line up vertically.
            pi.getAxis('left').setWidth(60)
            for ax_name in ('left', 'bottom'):
                ax = pi.getAxis(ax_name)
                ax.setPen(pg.mkPen(axis_color))
                ax.setTextPen(pg.mkPen(axis_color))

            # Share X-axis with the first subplot (oscilloscope-style)
            if first_vb is None:
                first_vb = vb
            else:
                vb.setXLink(first_vb)

            # Detect user pan/zoom → switch to Explore mode
            vb.sigXRangeChanged.connect(self._on_plot_range_changed)
            if hasattr(vb, "sigYRangeChanged"):
                vb.sigYRangeChanged.connect(
                    lambda _vb, y_range, i=idx: self._on_plot_y_range_changed(i, y_range)
                )

            # Crosshair (vline + hline) shown on hover. Hidden by default.
            crosshair_pen = self._plot_crosshair_pen(theme)
            vline = pg.InfiniteLine(angle=90, movable=False, pen=crosshair_pen)
            hline = pg.InfiniteLine(angle=0, movable=False, pen=crosshair_pen)
            vline.setVisible(False)
            hline.setVisible(False)
            pi.addItem(vline, ignoreBounds=True)
            pi.addItem(hline, ignoreBounds=True)
            # 60 Hz rate-limited mouse tracking on this panel's scene so the
            # crosshair feels snappy without flooding the event loop.
            proxy = pg.SignalProxy(
                pi.scene().sigMouseMoved,
                rateLimit=60,
                slot=lambda evt, _pi=pi: self._on_plot_mouse_moved(evt, _pi),
            )

            panel = PlotPanel(
                plot_item=pi,
                assigned_keys=list(panel_keys[idx]),
                legend=legend,
                time_axis=time_axis,
                index=idx,
            )
            # Stash crosshair refs on the panel via dynamic attrs — keeps
            # the dataclass narrow but lets _redraw_plot etc. find them.
            panel.vline = vline      # type: ignore[attr-defined]
            panel.hline = hline      # type: ignore[attr-defined]
            panel.mouse_proxy = proxy  # type: ignore[attr-defined]
            # Restore per-panel Auto-Y preference (defaults to True).
            saved_auto_y = self._settings.value(f"plot/panel/{idx}/auto_y", True)
            panel.auto_fit_y = (
                bool(saved_auto_y)
                if not isinstance(saved_auto_y, str)
                else saved_auto_y.lower() in ("true", "1", "yes"))
            vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=panel.auto_fit_y)
            if not panel.auto_fit_y:
                y_range = self._read_saved_y_range(idx)
                if y_range is not None:
                    vb.setYRange(y_range[0], y_range[1], padding=0)
            self._plot_panels.append(panel)

            # Redraw existing curves for this panel
            for key in panel.assigned_keys:
                label = f"0x{key[0]:04X} {key[1]}"
                color_idx = sum(len(p.assigned_keys) for p in self._plot_panels[:-1]) + len(panel.curves)
                palette = self._current_plot_palette()
                color = palette[color_idx % len(palette)]
                panel.curves[key] = pi.plot(name=label, pen=pg.mkPen(color, width=1.8))

            # Build variable-strip widget for this panel
            if hasattr(self, "_panel_strip_layout") and self._panel_strip_layout is not None:
                strip = self._make_panel_strip(idx)
                self._panel_strip_layout.addWidget(strip, 1)

        # Anchor X to start at 0 immediately, before any data arrives. Without
        # this, pyqtgraph's default auto-range shows roughly [-0.5, 0.5] until
        # the first packet, then snaps. The guard suppresses the sigXRangeChanged
        # callback that would otherwise flip us out of Live mode.
        if self._plot_panels:
            self._plot_range_changing = True
            try:
                self._plot_panels[0].plot_item.setXRange(0.0, _PLOT_INITIAL_WINDOW_S, padding=0)
            finally:
                self._plot_range_changing = False

        # Update aggregate _plot_keys
        self._sync_plot_keys()
        # Persist new layout
        self._settings.setValue("plot/layout", self._layout_combo.currentText())
        # Newly-created panels start with default axis pens; re-tint them for
        # the active theme so a layout change after a theme switch does not
        # leave dark axes on a light canvas.
        self._apply_plot_theme(str(self._settings.value("ui/theme", "dark")))

    def _make_panel_strip(self, panel_idx: int) -> QWidget:
        """Build the variable-chip strip for one subplot panel."""
        strip = QWidget()
        strip.setObjectName(f"panelStrip_{panel_idx}")
        strip.setMaximumHeight(36)
        hl = QHBoxLayout(strip)
        hl.setContentsMargins(2, 2, 2, 2)
        hl.setSpacing(4)
        lbl = QLabel(f"P{panel_idx + 1}:")
        lbl.setStyleSheet("font-weight:bold; font-size:11px;")
        hl.addWidget(lbl)
        self._refresh_panel_strip_contents(panel_idx, hl)
        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(24)
        add_btn.setStyleSheet("font-size:11px; padding: 0 6px;")
        add_btn.clicked.connect(lambda _, i=panel_idx: self._on_panel_add_signal(i))
        hl.addWidget(add_btn)
        # Per-panel Auto-Y checkbox — when on, pyqtgraph rescales y to fit
        # all visible curves on every redraw. When off, the user controls
        # zoom manually (typical "freeze the y-axis" workflow).
        auto_y_cb = QCheckBox("Auto Y")
        auto_y_cb.setToolTip(
            "Auto-rescale the y-axis on every update so growing signals "
            "stay in view. Uncheck to lock the current y range."
        )
        auto_y_cb.setStyleSheet("font-size: 11px;")
        panel = self._plot_panels[panel_idx] if panel_idx < len(self._plot_panels) else None
        auto_y_cb.setChecked(bool(panel.auto_fit_y) if panel else True)
        auto_y_cb.toggled.connect(
            lambda checked, i=panel_idx: self._on_panel_auto_y_toggled(i, checked))
        hl.addWidget(auto_y_cb)
        hl.addStretch(1)
        return strip

    def _on_panel_auto_y_toggled(self, panel_idx: int, checked: bool) -> None:
        if panel_idx >= len(self._plot_panels) or pg is None:
            return
        panel = self._plot_panels[panel_idx]
        panel.auto_fit_y = checked
        vb = panel.plot_item.getViewBox()
        vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=checked)
        if not checked:
            y_range = vb.viewRange()[1]
            if y_range and len(y_range) == 2:
                self._settings.setValue(
                    f"plot/panel/{panel_idx}/y_range",
                    [float(y_range[0]), float(y_range[1])],
                )
        self._settings.setValue(f"plot/panel/{panel_idx}/auto_y", checked)

    def _refresh_panel_strip_contents(self, panel_idx: int, layout: QHBoxLayout) -> None:
        """Add chip labels for each assigned key in the panel strip."""
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        color_offset = sum(len(self._plot_panels[i].assigned_keys) for i in range(panel_idx))
        palette = self._current_plot_palette()
        for local_idx, key in enumerate(panel.assigned_keys):
            color = palette[(color_offset + local_idx) % len(palette)]
            text_color = _contrast_text_color(color)
            chip = QPushButton(f"● {key[1]}  ✕")
            chip.setFixedHeight(22)
            chip.setStyleSheet(
                f"font-size:10px; padding:0 5px; border-radius:4px;"
                f"background:{color}; color:{text_color}; border:none;"
            )
            chip.clicked.connect(lambda _, i=panel_idx, k=key: self._remove_signal_from_panel(i, k))
            layout.addWidget(chip)

    def _rebuild_panel_strips(self) -> None:
        """Rebuild all variable-chip strips after assignments change."""
        if not hasattr(self, "_panel_strip_layout") or self._panel_strip_layout is None:
            return
        while self._panel_strip_layout.count():
            item = self._panel_strip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for idx in range(len(self._plot_panels)):
            strip = self._make_panel_strip(idx)
            self._panel_strip_layout.addWidget(strip, 1)

    def _on_layout_changed(self, label: str) -> None:
        rows, cols = GRID_LAYOUTS.get(label, (2, 1))
        self._clear_saved_y_ranges()
        self._rebuild_plot_grid(rows, cols, restore=False)
        self._redraw_plot()
        self._log_activity(f"[ACTION] Plot layout changed to {label} ({rows}x{cols})")

    def _on_panel_add_signal(self, panel_idx: int) -> None:
        """Open a searchable dialog to pick a signal to assign to panel *panel_idx*.

        QInputDialog.getItem renders a scrollable list with no filter — fine
        for 10 signals, miserable for 100+. The custom dialog adds a live
        filter box, marks signals already on a panel, and accepts Enter /
        double-click to commit so power users keep their hands on the
        keyboard.
        """
        if self._config is None:
            self._popup_warning("Add Signal", "Load a configuration first.")
            return
        all_keys = [(sig.frame_id, sig.signal_name) for sig in self._config.all_signals]
        if not all_keys:
            self._popup_information("Add Signal", "No signals available in the loaded config.")
            return
        already: Set[Tuple[int, str]] = {k for p in self._plot_panels for k in p.assigned_keys}

        key = self._prompt_signal_pick(
            title=f"Add signal to Panel {panel_idx + 1}",
            all_keys=all_keys,
            already_assigned=already,
        )
        if key is None:
            return
        self._add_signal_to_panel(panel_idx, key)

    def _prompt_signal_pick(
        self,
        *,
        title: str,
        all_keys: List[Tuple[int, str]],
        already_assigned: Set[Tuple[int, str]],
    ) -> Optional[Tuple[int, str]]:
        """Show a search-as-you-type dialog and return the picked key, or None."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(420, 460)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        filt = QLineEdit(dlg)
        filt.setPlaceholderText("Type to filter (substring match on frame id or name)…")
        layout.addWidget(filt)

        listw = QListWidget(dlg)
        listw.setAlternatingRowColors(True)
        layout.addWidget(listw, 1)

        hint = QLabel("• already assigned to a panel", dlg)
        hint.setStyleSheet("font-size:11px; color: palette(placeholderText);")
        layout.addWidget(hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        def _populate(query: str) -> None:
            listw.clear()
            q = query.strip().lower()
            for fid, nm in all_keys:
                label = f"0x{fid:04X}  {nm}"
                if q and q not in label.lower():
                    continue
                item = QListWidgetItem(
                    f"{'• ' if (fid, nm) in already_assigned else '  '}{label}"
                )
                item.setData(Qt.ItemDataRole.UserRole, (fid, nm))
                listw.addItem(item)
            if listw.count() > 0:
                listw.setCurrentRow(0)

        _populate("")
        filt.textChanged.connect(_populate)
        # Enter inside the filter box should commit the highlighted item.
        filt.returnPressed.connect(dlg.accept)
        listw.itemDoubleClicked.connect(lambda _it: dlg.accept())
        filt.setFocus()

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        item = listw.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _add_signal_to_panel(self, panel_idx: int, key: Tuple[int, str]) -> None:
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        if key not in panel.assigned_keys:
            panel.assigned_keys.append(key)
            self._sync_plot_keys()
            self._persist_panel_assignments()
            self._rebuild_panel_strips()
            self._redraw_plot()
            self._log_activity(
                f"[ACTION] Added signal 0x{key[0]:04X} {key[1]} to panel {panel_idx + 1}"
            )

    def _remove_signal_from_panel(self, panel_idx: int, key: Tuple[int, str]) -> None:
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        if key in panel.assigned_keys:
            panel.assigned_keys.remove(key)
            if key in panel.curves:
                panel.plot_item.removeItem(panel.curves.pop(key))
            self._sync_plot_keys()
            self._persist_panel_assignments()
            self._rebuild_panel_strips()
            self._redraw_plot()
            self._log_activity(
                f"[ACTION] Removed signal 0x{key[0]:04X} {key[1]} from panel {panel_idx + 1}"
            )

    def _sync_plot_keys(self) -> None:
        """Rebuild the aggregate _plot_keys from all panels (maintains order)."""
        seen: Set[Tuple[int, str]] = set()
        merged: List[Tuple[int, str]] = []
        for panel in self._plot_panels:
            for k in panel.assigned_keys:
                if k not in seen:
                    seen.add(k)
                    merged.append(k)
        self._plot_keys = merged

    def _persist_panel_assignments(self) -> None:
        for i, panel in enumerate(self._plot_panels):
            self._settings.setValue(f"plot/panel/{i}/keys", [list(k) for k in panel.assigned_keys])

    def _mouseMoved(self, evt):
        """Crosshair handler — disabled in multi-panel mode (panels use their own)."""
        pass



    def _build_bitfield_tab(self) -> QWidget:
        outer = QWidget(self)
        v = QVBoxLayout(outer)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("Group:", outer))
        self._bitfield_group_combo = _CheckableGroupCombo(outer)
        self._bitfield_group_combo.selection_changed.connect(self._apply_bitfield_group_filter)
        bar.addWidget(self._bitfield_group_combo, 1)
        v.addLayout(bar)

        self._bitfield_table = QTableWidget(0, 4, outer)
        self._bitfield_table.setHorizontalHeaderLabels(["Frame", "Variable", "Bit", "State"])
        self._bitfield_table.verticalHeader().setVisible(False)
        self._bitfield_table.horizontalHeader().setStretchLastSection(True)
        # Side index: key_text -> row, kept in sync with the table by
        # _upsert_detail_row and reset alongside _bitfield_table.setRowCount(0)
        # in _on_clear. Turns the previous O(rows) linear scan per signal
        # into O(1) — matters at high frame rates where every decoded packet
        # may touch the same bitfield rows.
        self._bitfield_row_index: Dict[str, int] = {}
        v.addWidget(self._bitfield_table, 1)
        return outer

    def _build_enum_tab(self) -> QWidget:
        outer = QWidget(self)
        v = QVBoxLayout(outer)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("Group:", outer))
        self._enum_group_combo = _CheckableGroupCombo(outer)
        self._enum_group_combo.selection_changed.connect(self._apply_enum_group_filter)
        bar.addWidget(self._enum_group_combo, 1)
        v.addLayout(bar)

        self._enum_table = QTableWidget(0, 4, outer)
        self._enum_table.setHorizontalHeaderLabels(["Frame", "Variable", "Raw", "Label"])
        self._enum_table.verticalHeader().setVisible(False)
        self._enum_table.horizontalHeader().setStretchLastSection(True)
        # See _bitfield_row_index — same pattern for the enum table.
        self._enum_row_index: Dict[str, int] = {}
        v.addWidget(self._enum_table, 1)
        return outer

    
    def _build_editor_tab(self) -> QWidget:
        outer = QWidget(self)
        vlay = QVBoxLayout(outer)
        vlay.setContentsMargins(4, 4, 4, 4)

        info = QLabel(
            "🔒 Only signals marked  read–write (RW) or write-only (W)  in the config "
            "appear here. Connect to write a new value."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size:11px; color: palette(mid); padding-bottom:4px;")
        vlay.addWidget(info)

        self._editor_table = QTableWidget(0, 4, outer)
        self._editor_table.setHorizontalHeaderLabels(
            ["Frame ID", "Signal", "Live Value", "Write"]
        )
        self._editor_table.verticalHeader().setVisible(False)
        hdr = self._editor_table.horizontalHeader()
        hdr.setSectionResizeMode(0, hdr.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, hdr.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, hdr.ResizeMode.Stretch)
        self._editor_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._editor_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        vlay.addWidget(self._editor_table)
        return outer

    def _build_tx_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        self._tx_command_combo = QComboBox(widget)
        self._tx_command_combo.currentIndexChanged.connect(self._rebuild_tx_fields)
        self._tx_fields_widget = QWidget(widget)
        self._tx_fields_form = QFormLayout(self._tx_fields_widget)
        self._tx_preview = QPlainTextEdit(widget)
        self._tx_preview.setReadOnly(True)
        self._tx_preview.setMaximumHeight(90)
        build_button = QPushButton("Build", widget)
        build_button.clicked.connect(self._preview_tx_command)
        send_button = QPushButton("Send", widget)
        send_button.clicked.connect(self._send_tx_command)
        buttons = QHBoxLayout()
        buttons.addWidget(build_button)
        buttons.addWidget(send_button)
        layout.addWidget(QLabel("Command"))
        layout.addWidget(self._tx_command_combo)
        layout.addWidget(self._tx_fields_widget)
        layout.addLayout(buttons)
        layout.addWidget(QLabel("Packet Preview"))
        layout.addWidget(self._tx_preview)
        layout.addStretch(1)
        return widget

    # ------------------------------------------------------------------
    # Config and toolbar handlers
    # ------------------------------------------------------------------
    def _load_default_config(self) -> None:
        self._populate_recent_selector()
        recent = self._recent_paths()
        for item in recent:
            path = Path(item)
            if path.exists():
                try:
                    self._load_config_from_path(path)
                    return
                except ConfigError:
                    continue
        resources_dir = Path(__file__).resolve().parents[1] / "resources"
        default_path = resources_dir / "config_template"
        try:
            self._load_config_from_path(default_path)
        except ConfigError as exc:
            self._set_status(f"Default config failed: {exc}")

    def _on_load_config(self) -> None:
        self._log_activity("[ACTION] Load configuration (dialog opened)")
        start_dir = str(Path(__file__).resolve().parents[1] / "resources")
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select configuration (Excel workbook or any CSV in a config folder)",
            start_dir,
            "Config (*.xlsx *.xlsm *.csv);;Excel workbook (*.xlsx *.xlsm);;CSV files (*.csv);;All files (*)",
        )
        if not path_str:
            return

        chosen = Path(path_str)
        suffix = chosen.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            path = chosen
        elif suffix == ".csv":
            path = chosen.parent
        else:
            self._popup_warning("Config error", f"Unsupported config selection: {chosen.name}")
            return

        try:
            self._load_config_from_path(path)
        except ConfigError as exc:
            self._popup_critical("Config error", str(exc))
            return

        # The running PollingWorker captured its protocol/parser/schedules at
        # construction time. Loading a new config replaces self._config and
        # self._parser (used by replay), but the worker keeps decoding live
        # bytes with the OLD rules until it is restarted. Tell the user.
        if self._serial is not None and self._serial.is_open:
            self._popup_information(
                "Reconnect required",
                "The new configuration is loaded for the UI, but the live "
                "serial connection is still using the previous protocol and "
                "polling schedule. Disconnect and reconnect to apply the new "
                "settings on the wire.",
            )

    def _load_config_from_path(self, path: Path) -> None:
        # Keep a snapshot so we can revert on failure
        _prev_config = self._config
        _prev_config_path = self._config_path
        _prev_parser = self._parser
        try:
            self._config = load_config(path)
        except Exception as exc:  # ConfigError or unexpected
            self._config = _prev_config
            self._config_path = _prev_config_path
            self._parser = _prev_parser
            self._popup_critical("Config error", str(exc))
            return
        self._config_path = path
        self._parser = create_parser(self._config.protocol)
        self._session_started = datetime.now()
        self._apply_plot_time_mode(self._plot_time_mode, persist=False)
        self._plot_history.clear()
        self._seen_decode_warnings.clear()
        self._packet_count = 0
        self._error_count = 0
        self._timeouts = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._delta_t_ms = 0.0
        self._last_packet_perf = None
        if self._serial is not None:
            self._serial.reset_metrics()
        self._console.clear()
        self._populate_table_from_config()
        self._populate_group_selector()
        self._plot_keys.clear()
        # Clear panel assignments — old signals may not exist in the new config
        for panel in self._plot_panels:
            panel.assigned_keys.clear()
            for curve in panel.curves.values():
                panel.plot_item.removeItem(curve)
            panel.curves.clear()
        self._rebuild_panel_strips()   # once after the loop, not N times
        self._persist_panel_assignments()
        self._populate_tx_commands()
        self._update_poll_status_sidebar()
        self._populate_editor_table()
        self._refresh_config_status()
        self._remember_config(path)
        self._refresh_action_state()
        self._set_status(f"Loaded config from {path}")
        self._log_activity(f"Loaded config: {path}")

    def _on_load_recent_config(self) -> None:
        path_text = self._recent_config_combo.currentText()
        if not path_text:
            return
        self._log_activity(f"[ACTION] Load recent config: {path_text}")
        try:
            self._load_config_from_path(Path(path_text))
        except ConfigError as exc:
            self._popup_critical("Config error", str(exc))

    def _recent_paths(self) -> list[str]:
        value = self._settings.value("recent_configs", [])
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value if str(item)]

    def _remember_config(self, path: Path) -> None:
        path_text = str(path)
        recent = [item for item in self._recent_paths() if item != path_text]
        recent.insert(0, path_text)
        self._settings.setValue("recent_configs", recent[:8])
        self._populate_recent_selector()

    def _populate_recent_selector(self) -> None:
        if not hasattr(self, "_recent_config_combo"):
            return
        current = self._recent_config_combo.currentText()
        self._recent_config_combo.clear()
        self._recent_config_combo.addItems(self._recent_paths())
        index = self._recent_config_combo.findText(current)
        if index >= 0:
            self._recent_config_combo.setCurrentIndex(index)

    def _on_export_template(self) -> None:
        self._log_activity("[ACTION] Export Excel template (dialog opened)")
        # Always build the template from the bundled blank CSV files so the
        # user always receives a complete, fresh workbook — regardless of
        # whether the currently-loaded config is a CSV folder or an .xlsx.
        bundled_template_dir = Path(__file__).resolve().parents[1] / "resources" / "config_template"
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export Excel template",
            str(Path.home() / "frame_config_template.xlsx"),
            "Excel workbook (*.xlsx)",
        )
        if not target:
            return
        try:
            export_excel_template(bundled_template_dir, target)
        except Exception as exc:
            self._popup_critical("Export template", str(exc))
            return
        self._set_status(f"Exported Excel template to {target}")
        self._log_activity(f"[ACTION] Exported Excel template: {target}")

    def _on_load_log(self) -> None:
        if self._config is None or self._parser is None:
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select raw log file", "", "Log files (*.csv *.txt *.log);;All files (*)"
        )
        if not path_str:
            return

        rows, errors = parse_log_file(path_str)
        # Mirror every parse error into the Activity Log so the user can
        # review them after dismissing the popup. The popup truncates at
        # 5 lines for readability; the log keeps the full list.
        if errors:
            self._log_activity(
                f"[REPLAY] {len(errors)} log line(s) failed to parse in {Path(path_str).name}"
            )
            for line_err in errors:
                self._log_activity(f"  [REPLAY-PARSE] {line_err}")
            self._popup_warning(
                "Log parse warnings",
                f"{len(errors)} line(s) skipped (full list in Activity Log):\n"
                + "\n".join(errors[:5])
                + ("\n…" if len(errors) > 5 else ""),
            )
        self._seen_decode_warnings.clear()
        replay_bad_packets = 0
        for chunk in replay_bytes(rows):
            self._rx_bytes += len(chunk)
            self._parser.feed(chunk)
            for pkt in self._parser.extract_all():
                if not pkt.ok:
                    replay_bad_packets += 1
                    fid = f"0x{pkt.frame_id:04X}" if pkt.frame_id is not None else "?"
                    self._log_activity(
                        f"  [REPLAY-FRAME] {fid}: {pkt.error or 'unknown error'}"
                    )
                self._handle_packet(pkt)
        if replay_bad_packets:
            self._log_activity(
                f"[REPLAY] {replay_bad_packets} frame(s) failed CRC or framing during replay"
            )
        # _handle_packet no longer touches the status-bar counts (the live
        # path refreshes once per UI flush). Replay has no UI timer, so do
        # a single refresh here after the whole file is consumed.
        self._refresh_counts_label()
        self._set_status(f"Replayed {len(rows)} log row(s) from {Path(path_str).name}")
        self._log_activity(
            f"[ACTION] Replayed log file ({len(rows)} rows, {replay_bad_packets} bad frames): {path_str}"
        )



    def _disconnect(self, *, reason: str = "Disconnected") -> None:
        """Single shutdown path for every disconnect scenario.

        Guarantees the safe sequence:
          1. Stop the 60 Hz UI flush timer
          2. Stop logging (flushes final data while worker may still be alive)
          3. Stop the worker thread and wait for it to exit
          4. Null the reference
          5. Update the UI chrome

        Idempotent — safe to call even when already disconnected.
        """
        self._ui_timer.stop()
        if self._logging:
            self._stop_logging()
            self._log_activity("[INFO] Logging auto-stopped on disconnect")
        if self._serial is not None:
            self._serial.close()   # calls stop() + wait(2000) + port.close()
            self._serial = None
        self._set_connection_ui(False)
        self._set_status(reason)

    def _on_toggle_connect(self) -> None:
        self._log_activity(
            "[ACTION] Connect toggle requested "
            f"{'disconnect' if (self._serial is not None and self._serial.is_open) else 'connect'}"
        )
        # --- Already connected: disconnect immediately -----------------------
        if self._serial is not None and self._serial.is_open:
            self._disconnect(reason="Disconnected")
            self._log_activity("Disconnected")
            return

        # --- Not connected: open ConnectionDialog ---------------------------
        if self._config is None:
            self._popup_warning("Connect", "Please load a configuration first.")
            return

        dlg = ConnectionDialog(self._settings, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        settings = dlg.get_settings()
        if not settings.port:
            self._popup_warning("Connect", "No port selected. Please plug in a device and refresh.")
            return

        self._seen_decode_warnings.clear()
        try:
            self._serial = PollingWorker(settings, self._config.protocol, self._config.polling_schedules)
            self._serial.packets_received.connect(self._on_packets_received)
            self._serial.metrics_updated.connect(self._on_metrics_updated)
            self._serial.error_occurred.connect(self._on_serial_error)
            self._serial.tx_recorded.connect(self._on_tx_recorded)
            self._serial.connection_lost.connect(self._on_connection_lost)
            self._serial.device_timeout.connect(self._on_device_timeout)
            self._serial.open()
            self._serial.set_polling_global(self._polling_action.isChecked())
            self._ui_timer.start()

            self._set_connection_ui(True)
            self._set_status(f"Connected to {settings.port}")
            self._log_activity(f"Connected to {settings.port} @ {settings.baud_rate}")
        except Exception as exc:
            self._serial = None
            self._popup_critical(
                "Connection Error",
                _format_serial_open_error(getattr(settings, "port", ""), exc),
            )

    def _on_serial_error(self, err: str) -> None:
        self._log_activity(f"Serial Error: {err}")
        self._disconnect(reason=f"Error: {err}")

    def _on_packets_received(self, batch: list) -> None:
        """Slot called by the worker's batch signal. Queues for the 60Hz UI timer.

        The underlying deque is bounded (maxlen=10_000) so a stalled Qt event
        loop cannot cause an OOM crash — oldest packets are silently dropped.
        """
        self._pending_packets.extend(batch)

    def _flush_ui(self) -> None:
        """Drain the pending packet queue and refresh the UI at 60 Hz.

        The session clock and rate label are updated on EVERY tick (even when
        no packets arrived) so the clock doesn't freeze during device timeouts.
        """
        # Update the session elapsed clock unconditionally (cheap string op).
        if self._session_started is not None and hasattr(self, '_session_clock_label'):
            elapsed = int((datetime.now() - self._session_started).total_seconds())
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self._session_clock_label.setText(f"\u23f1 {h}:{m:02d}:{s:02d}")

        # --- Drain packet queue ---
        # Atomic swap: replace the shared deque with a fresh one so the worker
        # thread's extend() never races with our iteration.  CPython's GIL
        # makes a single attribute assignment atomic.
        pending = self._pending_packets
        self._pending_packets = deque(maxlen=10_000)
        if not pending:
            return

        packets = list(pending)
        # Buffer all per-packet console rows so we can emit ONE
        # appendPlainText per flush instead of one per packet. At 1 kHz RX
        # this drops the Qt block-layout cost by ~50x.
        self._console_buffer: List[str] = []
        for packet in packets:
            self._handle_packet(packet)
        if self._console_buffer:
            self._console.appendPlainText("\n".join(self._console_buffer))
            self._console_buffer.clear()
        # Counts label is rebuilt once per flush — the worker pushes the
        # authoritative wire-level counters via metrics_updated at ~10 Hz,
        # and _handle_packet only mutates the UI-side _packet_count. One
        # refresh per flush is plenty and saves ~50 string rebuilds/batch.
        self._refresh_counts_label()
        # Commit all staged model cell updates in ONE dataChanged per row.
        self._table_model.commit_staged()
        # Redraw the plot once for the entire batch.
        now = time.monotonic()
        if (now - self._plot_last_redraw) >= self._plot_redraw_interval_s:
            self._redraw_plot()
            self._plot_last_redraw = now
        # Invalidate the hover crosshair cache now that plot_history has changed
        if hasattr(self, "_hover_cache"):
            self._hover_cache.clear()

        # Packet rate readout in the plot toolbar — refreshed at most ~4 Hz
        # so the label doesn't flicker. Uses a 1-second sliding-sum window.
        if hasattr(self, "_rate_label"):
            now = time.monotonic()
            if not hasattr(self, "_rate_window"):
                self._rate_window: Deque[Tuple[float, int]] = deque()
                self._rate_last_redraw = now
            self._rate_window.append((now, len(packets)))
            # Drop entries older than 1 second.
            cutoff = now - 1.0
            while self._rate_window and self._rate_window[0][0] < cutoff:
                self._rate_window.popleft()
            if (now - self._rate_last_redraw) >= 0.25:
                hz = sum(c for _, c in self._rate_window)
                self._rate_label.setText(f"{hz} Hz")
                self._rate_last_redraw = now

    def _on_connection_lost(self) -> None:
        """Called when the worker detects a physical USB unplug."""
        self._disconnect(reason="USB device disconnected")
        self._log_activity("[WARN] Connection lost — USB device was disconnected")

    def _on_device_timeout(self) -> None:
        """Called when the device is connected but has sent no data for ≥ 3 s."""
        # Amber LED — connected but silent
        self._led_label.setStyleSheet("color: #F59E0B;")
        self._led_label.setToolTip("Connected (No Data)")
        self._set_status("Connected (No Data)")

    @staticmethod
    def _fmt_bytes(n: int) -> str:
        """Human-readable byte count, always the same character width."""
        if n >= 1_048_576:
            return f"{n / 1_048_576:6.1f} MB"
        if n >= 1_024:
            return f"{n / 1_024:6.1f} KB"
        return f"{n:7d}  B"

    def _refresh_counts_label(self) -> None:
        """Single source of truth for the status-bar metrics string.
        Always the same format so the label never changes width.
        """
        if not hasattr(self, "_counts_label"):
            return
        self._counts_label.setText(
            f"Frames: {self._packet_count:>6d}"
            f"  |  Errors: {self._error_count:>4d}"
            f"  |  Timeouts: {self._timeouts:>4d}"
            f"  |  RX: {self._fmt_bytes(self._rx_bytes)}"
            f"  |  TX: {self._fmt_bytes(self._tx_bytes)}"
            f"  |  Lat: {self._delta_t_ms:>6.1f} ms"
        )

    def _on_metrics_updated(self, timeouts: int, crc: int, rx_bytes: int) -> None:
        self._timeouts = timeouts
        self._rx_bytes = rx_bytes
        self._error_count = crc
        self._refresh_counts_label()

    def _update_counts(self) -> None:
        self._refresh_counts_label()
        
    def _on_tx_recorded(self, packet: bytes) -> None:
        self._tx_bytes += len(packet)
        if self._raw_logger:
            self._raw_logger.log("TX", packet)
        self._console.appendPlainText(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, TX, {packet.hex(' ').upper()}")

    def _on_toggle_logging(self) -> None:
        if self._logging:
            self._stop_logging()
            return
        # Guard: logging only makes sense when connected
        if self._serial is None:
            self._popup_warning(
                "Start Logging",
                "Please connect to a device before starting logging.\n"
                "(Offline log replay does not support active logging.)"
            )
            return

        choice, ok = QInputDialog.getItem(
            self,
            "Logging mode",
            "What do you want to log?",
            ["Raw + Decoded", "Raw only", "Decoded only"],
            0,
            False,
        )
        if not ok:
            return
        log_raw = choice in ("Raw + Decoded", "Raw only")
        log_decoded = choice in ("Raw + Decoded", "Decoded only")

        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        default_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_file = default_dir / f"serial_log_{timestamp}.csv"

        target, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            str(default_file),
            "Log files (*.csv *.xlsx);;All files (*)",
        )
        if not target:
            return

        base = Path(target)
        base_stem = base.stem
        for suffix in ("_raw", "_decoded"):
            if base_stem.endswith(suffix):
                base_stem = base_stem[: -len(suffix)]
                break

        raw_path: Optional[Path] = None
        decoded_path: Optional[Path] = None
        if log_raw and log_decoded:
            raw_path = base.with_name(f"{base_stem}_raw.csv")
            decoded_path = base.with_name(f"{base_stem}_decoded.xlsx")
        elif log_raw:
            raw_path = base.with_name(f"{base_stem}.csv")
        else:
            decoded_path = base.with_name(f"{base_stem}.xlsx")

        # Set the logging t=0 BEFORE building metadata so the timestamp written
        # to the Metadata sheet matches the elapsed_ms baseline used in Data.
        # _log_started_perf is the monotonic baseline that elapsed_ms is
        # actually computed against; _log_started is the wall-clock string
        # for the Metadata sheet.
        self._log_started = datetime.now()
        self._log_started_perf = time.perf_counter()
        flush_interval = self._log_flush_interval()
        metadata = self._build_log_metadata(choice, raw_path, decoded_path)
        self._raw_logger = (
            RawLogger(
                raw_path,
                flush_interval=flush_interval,
                metadata=metadata,
                on_error=self._on_logger_error,
            )
            if raw_path
            else None
        )
        if decoded_path:
            assert self._config is not None
            self._decoded_logger = DecodedLogger(
                decoded_path,
                self._config,
                flush_interval=flush_interval,
                metadata=metadata,
                on_error=self._on_logger_error,
            )
        else:
            self._decoded_logger = None

        # Open eagerly so header-mismatch / permission errors surface here as
        # a popup, instead of being raised inside the 60 Hz UI flush callback
        # (which would crash the event loop) when the first packet arrives.
        try:
            if self._raw_logger:
                self._raw_logger.open()
            if self._decoded_logger:
                self._decoded_logger.open()
        except (ValueError, OSError) as exc:
            if self._raw_logger:
                self._raw_logger.close()
                self._raw_logger = None
            if self._decoded_logger:
                self._decoded_logger.close()
                self._decoded_logger = None
            self._popup_critical("Start Logging", f"Could not open log file:\n\n{exc}")
            return

        if self._config_path is not None:
            snapshot_config(self._config_path, base.with_name(f"{base_stem}_session"))

        self._logging = True
        self._logging_action.setText("Stop Logging")
        self._style_action_btn(self._logging_action, _BTN_PINK)   # active → pink

        label_parts = []
        if raw_path:
            label_parts.append(f"raw → {raw_path.name}")
        if decoded_path:
            label_parts.append(f"decoded → {decoded_path.name}")
        summary = ", ".join(label_parts)
        self._logging_label.setText(f"Logging: {summary}")
        self._set_status(f"Logging started ({choice}): {summary}")
        self._log_activity(f"Logging started ({choice}): {summary}")

    def _log_flush_interval(self) -> float:
        value = self._settings.value("logging/flush_interval_s", 0.5)
        try:
            interval = float(value)
        except (TypeError, ValueError):
            interval = 0.5
        if interval < 0:
            interval = 0.0
        return interval

    def _apply_logging_level(self, level_name: str) -> None:
        raw_level = getattr(logging, str(level_name).upper(), logging.INFO)
        level = raw_level if isinstance(raw_level, int) else logging.INFO
        root = logging.getLogger()
        root.setLevel(level)
        for handler in root.handlers:
            handler.setLevel(level)

    def _build_log_metadata(
        self,
        choice: str,
        raw_path: Optional[Path],
        decoded_path: Optional[Path],
    ) -> Dict[str, str]:
        metadata: Dict[str, str] = {
            "app": APP_NAME,
            "app_version": _read_version(),
            "session_started": (self._log_started or self._session_started).strftime("%Y-%m-%d %H:%M:%S"),
            "logging_mode": choice,
        }
        if raw_path is not None:
            metadata["raw_file"] = raw_path.name
        if decoded_path is not None:
            metadata["decoded_file"] = decoded_path.name
        if self._config_path is not None:
            metadata["config_source"] = str(self._config_path)
        if self._serial is not None:
            metadata["serial_port"] = self._serial.settings.port
            metadata["baud_rate"] = str(self._serial.settings.baud_rate)
        return metadata

    def _on_logger_error(self, message: str) -> None:
        logging.getLogger("bytehound.logging").error("Logging error: %s", message)
        if self._logging:
            self._stop_logging()
        self._set_status("Logging stopped (error)")
        self._log_activity(f"[ERROR] {message}")
        self._popup_warning("Logging Error", f"Logging stopped due to an error:\n\n{message}")

    def _stop_logging(self) -> None:
        was_logging = self._logging
        if self._raw_logger:
            self._raw_logger.close()
        if self._decoded_logger:
            self._decoded_logger.close()
        self._raw_logger = None
        self._decoded_logger = None
        self._logging = False
        self._log_started = None
        self._log_started_perf = None
        self._logging_action.setText("Start Logging")
        self._style_action_btn(self._logging_action, _BTN_YELLOW)   # back to yellow
        self._logging_label.setText("Logging: stopped")
        self._set_status("Logging stopped")
        if was_logging:
            self._log_activity("Logging stopped")

    def _on_open_log_folder(self) -> None:
        default_dir = Path(os.path.expanduser("~")) / "Documents" / APP_NAME
        self._log_activity(f"[ACTION] Open log folder: {default_dir}")
        if default_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(default_dir)))
        else:
            self._popup_information("Logs", f"Log directory does not exist yet:\n{default_dir}")

    def _on_clear(self) -> None:
        self._console.clear()
        self._packet_count = 0
        self._error_count = 0
        self._timeouts = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._delta_t_ms = 0.0
        self._last_packet_perf = None
        # Also clear the worker-owned counters so they don't snap back on the
        # next metrics_updated emission. No-op when not connected.
        if self._serial is not None:
            self._serial.reset_metrics()
        self._plot_history.clear()
        self._bitfield_table.setRowCount(0)
        self._enum_table.setRowCount(0)
        # Side indexes must drop their mappings alongside the table reset,
        # otherwise the next decode would try to write into a row that no
        # longer exists.
        self._bitfield_row_index.clear()
        self._enum_row_index.clear()
        self._table_model.clear_live_columns()
        self._seen_decode_warnings.clear()
        self._redraw_plot()
        self._update_counts()
        self._set_status("Cleared decoded values and console")
        self._log_activity("[ACTION] Cleared console and decoded values")

    def _populate_tx_commands(self) -> None:
        self._tx_command_combo.clear()
        self._tx_field_inputs.clear()
        if self._config is None:
            return
        self._tx_command_combo.addItems(sorted(self._config.tx_commands))
        self._rebuild_tx_fields()

    def _rebuild_tx_fields(self) -> None:
        while self._tx_fields_form.rowCount():
            self._tx_fields_form.removeRow(0)
        self._tx_field_inputs.clear()
        if self._config is None:
            return
        command = self._config.tx_commands.get(self._tx_command_combo.currentText())
        if command is None:
            return
        for field in command.fields:
            editor = QLineEdit(self._tx_fields_widget)
            if field.default is not None:
                editor.setText(f"{field.default:g}")
            suffix = f" ({field.unit})" if field.unit else ""
            self._tx_fields_form.addRow(f"{field.field_name}{suffix}", editor)
            self._tx_field_inputs[field.field_name] = editor
        self._preview_tx_command()

    def _tx_values(self) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for name, editor in self._tx_field_inputs.items():
            text = editor.text().strip()
            if text:
                values[name] = float(text)
        return values

    def _build_current_tx_packet(self) -> bytes:
        if self._config is None:
            raise CommandBuildError("No configuration loaded")
        return build_tx_command(
            self._config, self._tx_command_combo.currentText(), self._tx_values()
        )

    def _preview_tx_command(self) -> None:
        try:
            packet = self._build_current_tx_packet()
        except (CommandBuildError, ValueError) as exc:
            self._tx_preview.setPlainText(str(exc))
            return
        self._tx_preview.setPlainText(packet.hex(" ").upper())

    def _send_tx_command(self) -> None:
        try:
            packet = self._build_current_tx_packet()
        except (CommandBuildError, ValueError) as exc:
            self._popup_warning("TX command", str(exc))
            return
        if self._serial is None or not self._serial.is_open:
            self._popup_warning("TX command", "Connect a serial port before sending.")
            return
        self._serial.enqueue_priority_tx(packet)
        self._tx_bytes += len(packet)
        if self._raw_logger:
            self._raw_logger.log("TX", packet)
        self._console.appendPlainText(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, TX, {packet.hex(' ').upper()}")
        self._update_counts()
        self._log_activity(
            f"[ACTION] TX command sent: {self._tx_command_combo.currentText()} "
            f"(raw=0x{packet.hex().upper()})"
        )

    # ------------------------------------------------------------------
    # Data feed
    # ------------------------------------------------------------------
    

    def _handle_packet(self, packet: ParsedPacket) -> None:
        self._packet_count += 1
        now = time.perf_counter()
        if self._last_packet_perf is not None:
            self._delta_t_ms = (now - self._last_packet_perf) * 1000.0
        self._last_packet_perf = now
        # Buffer the console line. _flush_ui appends them all in one shot.
        # Falling back to direct append keeps replay (which calls
        # _handle_packet outside the batch path) behaving as before.
        line = self._format_console_row(packet)
        buf = getattr(self, "_console_buffer", None)
        if buf is None:
            self._console.appendPlainText(line)
        else:
            buf.append(line)
        if self._raw_logger:
            self._raw_logger.log("RX", packet.raw, delta_t_ms=self._delta_t_ms)
        if not packet.ok:
            # During live, the worker is the single source of truth for the CRC
            # error count and pushes it via metrics_updated → _on_metrics_updated.
            # Counting again here would double-count and produce a 0↔1 flicker
            # as the two writes race. In replay mode there is no worker, so we
            # do the bookkeeping ourselves.
            if self._serial is None:
                self._error_count += 1
            return

        # Reset LED to green when data is flowing again after a timeout.
        if self._serial is not None:
            current_tooltip = self._led_label.toolTip()
            if current_tooltip == "Connected (No Data)":
                self._led_label.setStyleSheet("color: #66BB6A;")
                self._led_label.setToolTip("Connected")
                self._set_status(f"Connected")

        assert self._config is not None
        decoded = decode_frame(self._config, packet.frame_id, packet.payload)
        self._apply_decoded(decoded)
        if self._decoded_logger:
            # Use the monotonic clock for elapsed_ms — wall-clock arithmetic
            # would skip or go backward if the system clock is corrected by
            # NTP during the session. Fall back to a freshly-sampled baseline
            # only if logging started before _log_started_perf was captured
            # (defensive — should not happen with the current Start path).
            if self._log_started_perf is not None:
                elapsed_ms = int((time.perf_counter() - self._log_started_perf) * 1000)
            else:
                t0 = self._log_started or self._session_started
                elapsed_ms = int((datetime.now() - t0).total_seconds() * 1000)
            self._decoded_logger.log_frame(decoded, elapsed_ms)

    # ------------------------------------------------------------------
    # Table, tabs, and plot maintenance
    # ------------------------------------------------------------------
    
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

    def _populate_editor_table(self) -> None:
        self._editor_table.setRowCount(0)
        # Index: signal_name -> list of value-cell QTableWidgetItem refs.
        # _apply_decoded looks rows up by name on every decoded signal of
        # every packet; a linear scan over rowCount() was O(rows * packets *
        # signals_per_packet) per UI flush. A dict turns that into O(1).
        self._editor_value_items: Dict[str, List[QTableWidgetItem]] = {}
        if not self._config:
            return
        rw_signals = [s for s in self._config.all_signals if s.read_write in ("W", "RW")]
        if not rw_signals:
            # Nothing writable — insert a single informational row
            self._editor_table.insertRow(0)
            lbl = QTableWidgetItem("No writable signals defined in this config (all are read-only).")
            lbl.setFlags(Qt.ItemFlag.NoItemFlags)
            self._editor_table.setItem(0, 0, lbl)
            self._editor_table.setSpan(0, 0, 1, 4)
            return
        _INT_TYPES = {"uint8", "int8", "uint16", "int16", "uint32", "int32"}
        for s in rw_signals:
            row = self._editor_table.rowCount()
            self._editor_table.insertRow(row)
            self._editor_table.setItem(row, 0, QTableWidgetItem(f"0x{s.frame_id:04X}"))
            self._editor_table.setItem(row, 1, QTableWidgetItem(s.signal_name))

            curr_val = QTableWidgetItem("-")
            curr_val.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._editor_table.setItem(row, 2, curr_val)
            self._editor_value_items.setdefault(s.signal_name, []).append(curr_val)

            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(2, 1, 2, 1)
            inp = QLineEdit()
            inp.setPlaceholderText("enter value…")

            lo = s.min_value
            hi = s.max_value
            if s.data_type in _INT_TYPES:
                ilo = int(lo) if lo is not None else -2_147_483_648
                ihi = int(hi) if hi is not None else  2_147_483_647
                inp.setValidator(QIntValidator(ilo, ihi))
                inp.setToolTip(f"Integer  [{ilo} … {ihi}]")
            else:
                flo = lo if lo is not None else -1e18
                fhi = hi if hi is not None else  1e18
                _dv = QDoubleValidator(flo, fhi, 6)
                _dv.setLocale(QLocale(QLocale.Language.C))
                inp.setValidator(_dv)
                inp.setToolTip(f"Float  [{flo:g} … {fhi:g}]")

            btn = QPushButton("Write")
            btn.setFixedWidth(56)
            btn.clicked.connect(lambda _, inp=inp, s=s: self._on_editor_write(s, inp.text()))
            # Allow pressing Enter in the input to trigger write
            inp.returnPressed.connect(lambda inp=inp, s=s: self._on_editor_write(s, inp.text()))
            layout.addWidget(inp)
            layout.addWidget(btn)
            self._editor_table.setCellWidget(row, 3, widget)

    def _on_editor_write(self, signal, text: str) -> None:
        if not self._serial or not self._serial.is_open:
            self._popup_warning("Write", "Not connected")
            return
        try:
            val = float(text)
            if signal.min_value is not None and val < signal.min_value:
                raise ValueError(f"Min value is {signal.min_value}")
            if signal.max_value is not None and val > signal.max_value:
                raise ValueError(f"Max value is {signal.max_value}")
        except ValueError as e:
            self._popup_warning("Invalid Input", str(e))
            return

        from ..protocol.packet_builder import build_packet
        import struct

        try:
            # Step 1: reverse scale/offset → raw = (user_value - offset) / scale
            raw = (val - signal.offset) / signal.scale

            # Step 2: encode raw into bytes per data_type and byte_order
            byteorder: str = signal.endianness   # "little" | "big"
            dt: str = signal.data_type            # "uint8", "int16", "float32", etc.

            if "float" in dt:
                fmt = ("<" if byteorder == "little" else ">") + (
                    "f" if signal.byte_length == 4 else "d"
                )
                encoded = struct.pack(fmt, float(raw))
            elif "int" in dt:
                signed = dt.startswith("int")
                encoded = round(raw).to_bytes(signal.byte_length, byteorder, signed=signed)
            else:
                raise ValueError(f"Unsupported data_type for write: {dt!r}")

            if len(encoded) != signal.byte_length:
                raise ValueError(
                    f"Encoded value is {len(encoded)} bytes but signal expects {signal.byte_length}"
                )

            # Step 3: place encoded bytes at start_byte in a zero-padded payload
            payload = bytearray(signal.end_byte)
            payload[signal.start_byte:signal.end_byte] = encoded

            # Step 4: wrap in the full packet envelope (header + CRC + footer)
            pkt = build_packet(self._config.protocol, signal.frame_id, bytes(payload))

        except (OverflowError, struct.error, ValueError) as exc:
            self._popup_warning("Write Error", str(exc))
            return

        self._serial.enqueue_priority_tx(pkt)
        self._log_activity(
            f"Write: {signal.signal_name} = {val} {signal.unit}  "
            f"(raw=0x{pkt.hex().upper()})"
        )


    def _populate_table_from_config(self) -> None:
        assert self._config is not None
        self._row_index.clear()
        rows = []
        self._signal_unit_map.clear()
        for frame_id, signals in self._config.signals_by_frame.items():
            for signal in signals:
                key = (frame_id, signal.signal_name)
                self._signal_unit_map[key] = signal.unit
                rows.append({
                    "key": key,
                    "Frame": f"0x{frame_id:04X}",
                    "Group": signal.group or "-",
                    "Variable": signal.signal_name,
                    "Start B.": str(signal.start_byte),
                    "Data Type": signal.data_type or "-",
                    "Raw": "-",
                    "Value": "-",
                    "Unit": signal.unit,
                    "Status": "-",
                    "Updated": "-",
                    "is_calculated": False,
                })
        self._table_model.reset_from_config(rows)

    def _add_signal_row(
        self,
        row: int,  # kept for API compatibility but ignored (model appends)
        frame_id: int,
        signal_name: str,
        group: str,
        start_byte: int,
        data_type: str,
        unit: str,
        is_calculated: bool = False,
    ) -> None:
        """Add a new row to the telemetry model (called for runtime-discovered signals)."""
        key = (frame_id, signal_name)
        self._signal_unit_map[key] = unit
        self._table_model.add_row(
            key=key,
            frame_hex=f"0x{frame_id:04X}",
            group=group or "-",
            signal_name=signal_name,
            start_byte=str(start_byte),
            data_type=data_type or "-",
            unit=unit,
            is_calculated=is_calculated,
        )

    def _apply_decoded(self, decoded: DecodedFrame) -> None:
        if decoded.error is not None:
            # Decode-time issues (e.g. "no signals configured for frame_id …")
            # are surfaced in the console for the user to investigate. They are
            # NOT counted in the status-bar "Errors" tally — that field tracks
            # wire-level CRC failures only.
            self._console.appendPlainText(f"[decode] {decoded.error}")
            return
        for w in decoded.warnings:
            key = (w.frame_id, w.kind, w.offset if w.offset is not None else -1)
            if key in self._seen_decode_warnings:
                continue
            self._seen_decode_warnings.add(key)
            tail = f"  tail@byte{w.offset}: {w.extra_hex}" if w.extra_hex else ""
            self._log_activity(f"[DECODE WARN] {w.message}{tail}")
            self._console.appendPlainText(f"[decode warning] {w.message}")

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        elapsed = (datetime.now() - self._session_started).total_seconds()
        for signal in [*decoded.signals, *decoded.calculations]:
            key = (signal.frame_id, signal.signal_name)
            # If the key isn't in the model yet, add it (calculated / late-arriving signals)
            if self._table_model.row_for_key(key) is None:
                spec = next(
                    (s for s in self._config.all_signals
                     if s.frame_id == signal.frame_id and s.signal_name == signal.signal_name),
                    None,
                )
                self._add_signal_row(
                    0,  # ignored by model-backed version
                    signal.frame_id,
                    signal.signal_name,
                    signal.group,
                    spec.start_byte if spec else 0,
                    spec.data_type if spec else "-",
                    signal.unit,
                    signal.is_calculated,
                )

            if signal.raw_value is None:
                continue

            raw_text = "-" if signal.raw_value is None else _format_number(signal.raw_value)
            value_text = "-" if signal.scaled_value is None else _format_number(signal.scaled_value)
            self._table_model.stage_live_cells(
                key,
                raw=raw_text,
                value=signal.display_value or value_text,
                status=self._status_text(signal),
                updated=timestamp,
            )
            self._update_detail_tabs(signal)
            # O(1) editor-row lookup via the index built in
            # _populate_editor_table. setdefault on a missing config keeps
            # this branch a no-op when the editor table isn't initialised.
            for val_item in getattr(self, "_editor_value_items", {}).get(
                signal.signal_name, ()
            ):
                val_item.setText(signal.display_value or value_text)

            if signal.scaled_value is not None and signal.status == "ok":
                xs, ys = self._plot_history[key]
                xs.append(elapsed)
                ys.append(signal.scaled_value)
            # Per-signal decode failures (e.g. "Payload too short") are visible
            # via the row's status pill; we deliberately do NOT increment the
            # status-bar Errors counter for them — that field is reserved for
            # wire-level CRC failures, sourced from the worker.
        # NOTE: _redraw_plot() is intentionally NOT called here.
        # It is called once per batch in _flush_ui() to avoid per-packet redraws.

    def _status_text(self, signal: DecodedSignal) -> str:
        if signal.enum_label:
            return f"{signal.status}: {signal.enum_label}"
        if signal.bit_values:
            active = [name for name, active_state in signal.bit_values.items() if active_state]
            return f"{signal.status}: {', '.join(active) if active else 'None'}"
        return signal.status

    def _update_detail_tabs(self, signal: DecodedSignal) -> None:
        group = self._signal_group_map.get((signal.frame_id, signal.signal_name), "")
        if signal.bit_values:
            bf_selected = (
                self._bitfield_group_combo.selected_groups()
                if hasattr(self, "_bitfield_group_combo") else set()
            )
            bf_visible = self._row_visible_for_group(bf_selected, group)
            for bit_name, active in signal.bit_values.items():
                key = (f"0x{signal.frame_id:04X}", signal.signal_name, bit_name)
                self._upsert_detail_row(
                    self._bitfield_table,
                    self._bitfield_row_index,
                    key,
                    [f"0x{signal.frame_id:04X}", signal.signal_name, bit_name, "ON" if active else "OFF"],
                )
                row = self._bitfield_row_index.get("\x1f".join(key))
                if row is not None:
                    self._bitfield_table.setRowHidden(row, not bf_visible)
        if signal.enum_label:
            en_selected = (
                self._enum_group_combo.selected_groups()
                if hasattr(self, "_enum_group_combo") else set()
            )
            en_visible = self._row_visible_for_group(en_selected, group)
            key = (f"0x{signal.frame_id:04X}", signal.signal_name)
            self._upsert_detail_row(
                self._enum_table,
                self._enum_row_index,
                key,
                [
                    f"0x{signal.frame_id:04X}",
                    signal.signal_name,
                    "" if signal.raw_value is None else str(signal.raw_value),
                    signal.enum_label,
                ],
            )
            row = self._enum_row_index.get("\x1f".join(key))
            if row is not None:
                self._enum_table.setRowHidden(row, not en_visible)

    def _upsert_detail_row(
        self,
        table: QTableWidget,
        row_index: Dict[str, int],
        key: tuple[str, ...],
        values: list[str],
    ) -> None:
        """Insert-or-update a row in *table*, looked up via *row_index* in O(1).

        *row_index* maps the joined-key string to the table row number. The
        caller is responsible for clearing it whenever ``table.setRowCount(0)``
        runs (see :meth:`_on_clear`).
        """
        key_text = "\x1f".join(key)
        row = row_index.get(key_text)
        if row is not None and row < table.rowCount():
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))
            table.item(row, 0).setData(Qt.ItemDataRole.UserRole, key_text)
            return
        row = table.rowCount()
        table.insertRow(row)
        for col, value in enumerate(values):
            table.setItem(row, col, QTableWidgetItem(value))
        table.item(row, 0).setData(Qt.ItemDataRole.UserRole, key_text)
        row_index[key_text] = row

    def _populate_group_selector(self) -> None:
        assert self._config is not None
        groups = sorted({signal.group for signal in self._config.all_signals if signal.group})
        self._group_combo.set_groups(groups)
        # Refresh the per-(frame,signal) → group lookup used by the dock filters.
        self._signal_group_map = {
            (s.frame_id, s.signal_name): (s.group or "")
            for s in self._config.all_signals
        }
        # Each dock combo lists only groups whose signals actually belong to
        # that dock — listing groups that can never produce a row is noise.
        bitfield_keys = set(self._config.bitfields.keys())
        enum_keys = set(self._config.enums.keys())
        bitfield_groups = sorted({
            s.group for s in self._config.all_signals
            if s.group and (s.frame_id, s.signal_name) in bitfield_keys
        })
        enum_groups = sorted({
            s.group for s in self._config.all_signals
            if s.group and (s.frame_id, s.signal_name) in enum_keys
        })
        # Independent combos in each dock — both reset to "All" on config load.
        # After that they behave independently of the main combo.
        if hasattr(self, "_bitfield_group_combo"):
            self._bitfield_group_combo.set_groups(bitfield_groups)
        if hasattr(self, "_enum_group_combo"):
            self._enum_group_combo.set_groups(enum_groups)

    def _row_visible_for_group(self, selected: set, group: str) -> bool:
        return (not selected) or (group in selected)

    def _apply_bitfield_group_filter(self) -> None:
        selected = self._bitfield_group_combo.selected_groups()
        self._bitfield_table.setUpdatesEnabled(False)
        try:
            for key_text, row in self._bitfield_row_index.items():
                parts = key_text.split("\x1f")
                if len(parts) < 2:
                    continue
                try:
                    frame_id = int(parts[0], 16)
                except ValueError:
                    continue
                group = self._signal_group_map.get((frame_id, parts[1]), "")
                self._bitfield_table.setRowHidden(
                    row, not self._row_visible_for_group(selected, group)
                )
        finally:
            self._bitfield_table.setUpdatesEnabled(True)

    def _apply_enum_group_filter(self) -> None:
        selected = self._enum_group_combo.selected_groups()
        self._enum_table.setUpdatesEnabled(False)
        try:
            for key_text, row in self._enum_row_index.items():
                parts = key_text.split("\x1f")
                if len(parts) < 2:
                    continue
                try:
                    frame_id = int(parts[0], 16)
                except ValueError:
                    continue
                group = self._signal_group_map.get((frame_id, parts[1]), "")
                self._enum_table.setRowHidden(
                    row, not self._row_visible_for_group(selected, group)
                )
        finally:
            self._enum_table.setUpdatesEnabled(True)

    def _apply_group_filter(self) -> None:
        selected_groups = self._group_combo.selected_groups()   # empty set = All
        search_text = ""
        if hasattr(self, "_search_input"):
            search_text = self._search_input.text().lower()

        show_calcs = self._show_calcs_check.isChecked()
        n = self._table_model.row_count()
        # Suppress per-row repaints — a single update at the end is 50x cheaper
        # for tables with 500+ signals.
        self._table.setUpdatesEnabled(False)
        try:
            for row in range(n):
                row_group   = self._table_model.group_for_row(row)
                row_name    = self._table_model.signal_name_for_row(row).lower()
                is_calculated = self._table_model.is_calculated_row(row)

                # Empty selected_groups means "All"
                if selected_groups:
                    visible = row_group in selected_groups
                else:
                    visible = True
                if is_calculated and not show_calcs:
                    visible = False
                if search_text and search_text not in row_name:
                    visible = False

                self._table.setRowHidden(row, not visible)
        finally:
            self._table.setUpdatesEnabled(True)



    def _on_plot_range_changed(self, vb, x_range) -> None:
        """Called when any ViewBox X-range changes.

        Guard suppresses changes triggered by our own setXRange calls;
        any other change means the user panned/zoomed → switch to Explore.
        """
        if self._plot_range_changing:
            return
        if self._plot_live:
            # User pan/zoom is functionally the same as Pausing.
            self._set_plot_live(False, source="pan")
            self._log_activity("[ACTION] Plot switched to Explore mode (user pan/zoom)")

    # ------------------------------------------------------------------
    # Pause / Live toggle button
    # ------------------------------------------------------------------
    def _set_plot_live(self, live: bool, *, source: str = "") -> None:
        """Single source of truth for ``_plot_live`` + Pause button + mode label.

        Every code path that wants to flip the plot between Live and
        Explore/Pause goes through here so the three pieces of UI state
        cannot drift. ``source`` is "pan" when the change was triggered by a
        user pan/zoom (so the mode label can mention how to get back); any
        other value renders as plain Paused.
        """
        self._plot_live = live
        paused = not live
        if hasattr(self, "_pause_btn"):
            self._pause_btn.blockSignals(True)
            self._pause_btn.setChecked(paused)
            self._pause_btn.blockSignals(False)
            self._restyle_pause_btn(paused)
        if hasattr(self, "_plot_mode_btn"):
            if live:
                self._plot_mode_btn.setText("📊 Live")
                self._plot_mode_btn.setEnabled(False)
            elif source == "pan":
                self._plot_mode_btn.setText("🔍 Explore")
                self._plot_mode_btn.setEnabled(True)
            else:
                self._plot_mode_btn.setText("⏸ Paused")
                self._plot_mode_btn.setEnabled(True)

    def _restyle_pause_btn(self, paused: bool) -> None:
        """Recolour the toggle so the current mode reads at a glance."""
        if paused:
            text = "▶ Live"
            bg = "#16A34A"   # green = "click to go Live"
        else:
            text = "⏸ Pause"
            bg = "#D97706"   # amber = "click to pause"
        self._pause_btn.setText(text)
        self._pause_btn.setStyleSheet(
            f"QPushButton {{ background:{bg}; color:#fff; border:none;"
            f"               padding:4px 10px; border-radius:4px; font-weight:bold; }}"
            f"QPushButton:hover {{ filter: brightness(1.1); }}"
        )

    def _on_pause_toggled(self, checked: bool) -> None:
        """Space-bar / button toggle: Pause = freeze view, Live = resume scroll."""
        going_live = not checked
        self._set_plot_live(going_live)
        if going_live:
            # Re-enable Y auto-range on panels that want it (pan/zoom during
            # Pause turned it off). X is left for _redraw_plot to handle so the
            # data-aware [oldest_x, current_t] window logic stays in one place.
            if pg is not None and self._plot_panels:
                self._plot_range_changing = True
                try:
                    for panel in self._plot_panels:
                        vb = panel.plot_item.getViewBox()
                        if vb is not None and panel.auto_fit_y:
                            vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
                finally:
                    self._plot_range_changing = False
            self._log_activity("[ACTION] Plot resumed Live")
            self._redraw_plot()
        else:
            self._log_activity("[ACTION] Plot Paused")

    # ------------------------------------------------------------------
    # Hover crosshair + value readout
    # ------------------------------------------------------------------
    def _on_plot_mouse_moved(self, evt, pi) -> None:
        """Handle a rate-limited mouse-move on one panel's scene. Updates the
        crosshair on that panel and writes interpolated values into the
        hover label in the controls bar."""
        if not evt:
            return
        scene_pos = evt[0]
        # Find the panel matching this PlotItem so we can flip its crosshair.
        panel = next((p for p in self._plot_panels if p.plot_item is pi), None)
        if panel is None:
            return
        vb = pi.getViewBox()
        if vb is None or not pi.sceneBoundingRect().contains(scene_pos):
            # Mouse left this panel — hide its crosshair.
            getattr(panel, "vline", None) and panel.vline.setVisible(False)
            getattr(panel, "hline", None) and panel.hline.setVisible(False)
            return
        mouse_point = vb.mapSceneToView(scene_pos)
        t = float(mouse_point.x())
        y = float(mouse_point.y())
        # Position the crosshair lines and make them visible.
        if hasattr(panel, "vline"):
            panel.vline.setPos(t)
            panel.vline.setVisible(True)
        if hasattr(panel, "hline"):
            panel.hline.setPos(y)
            panel.hline.setVisible(True)

        # Build the readout: time + one entry per signal on THIS panel,
        # interpolated to the cursor's x by nearest-sample lookup.
        time_txt = self._format_plot_time(t)
        if self._plot_time_mode == "clock":
            parts: list[str] = [f"time={time_txt}"]
        else:
            parts = [f"t={time_txt}"]
        for key in panel.assigned_keys:
            buf = self._plot_history.get(key)
            if not buf:
                continue
            xs_deque, ys_deque = buf
            if not xs_deque:
                continue
            try:
                if not hasattr(self, "_hover_cache"):
                    self._hover_cache = {}
                cached_lists = self._hover_cache.get(key)
                if cached_lists is None:
                    cached_lists = (list(xs_deque), list(ys_deque))
                    self._hover_cache[key] = cached_lists
                xs_list, ys_list = cached_lists

                import bisect
                idx = bisect.bisect_left(xs_list, t)
                if idx >= len(xs_list):
                    idx = len(xs_list) - 1
                elif idx > 0 and (t - xs_list[idx - 1]) < (xs_list[idx] - t):
                    idx -= 1
                # The cached list stays fast for indexing
                unit = self._signal_unit_map.get(key, "")
                suffix = f" {unit}" if unit else ""
                parts.append(f"{key[1]}={ys_list[idx]:.2f}{suffix}")
            except Exception:
                continue
        if hasattr(self, "_hover_label"):
            # Cap the line length so the control bar doesn't reflow.
            text = "  ·  ".join(parts)
            if len(text) > 120:
                text = text[:117] + "…"
            self._hover_label.setText(text)

    def _on_table_context_menu(self, pos) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        key = self._table_model.key_for_row(row)
        if key is None:
            return

        menu = QMenu(self._table)
        if key in self._plot_keys:
            menu.addAction("Remove from Live Plot").triggered.connect(
                lambda: self._toggle_plot_key(key)
            )
        else:
            n_panels = len(self._plot_panels)
            if n_panels <= 1:
                menu.addAction("Add to Live Plot").triggered.connect(
                    lambda: self._toggle_plot_key(key)
                )
            else:
                add_sub = menu.addMenu("Add to Live Plot")
                for idx in range(n_panels):
                    n_sigs = len(self._plot_panels[idx].assigned_keys)
                    count_str = "empty" if n_sigs == 0 else f"{n_sigs} signal{'s' if n_sigs > 1 else ''}"
                    label = f"Panel {idx + 1}  ({count_str})"
                    add_sub.addAction(label).triggered.connect(
                        lambda _=False, i=idx: self._add_signal_to_panel(i, key)
                    )
        menu.addSeparator()
        copy_action = menu.addAction("Copy Value")
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is copy_action:
            QApplication.clipboard().setText(self._table_model.cell_text(row, 6))

    def _toggle_plot_key(self, key: Tuple[int, str]) -> None:
        """Toggle a signal in Panel 0 (right-click shortcut from data table)."""
        if not self._plot_panels:
            return
        if key in self._plot_keys:
            for idx, panel in enumerate(self._plot_panels):
                if key in panel.assigned_keys:
                    self._remove_signal_from_panel(idx, key)
                    break
        else:
            self._add_signal_to_panel(0, key)


    def _curve_color_icon(self, color_hex: str) -> QIcon:
        cache_key = ("dot", color_hex, "12")
        cached = self._curve_icon_cache.get(cache_key)
        if cached is not None:
            return cached
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(QColor(color_hex)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(1, 1, 10, 10)
        painter.end()
        icon = QIcon(pixmap)
        self._curve_icon_cache[cache_key] = icon
        return icon

    def _refresh_plot_indicators(self) -> None:
        """Update the colored dot icon in the Variable column for plotted signals."""
        palette = self._current_plot_palette()
        key_to_color: Dict[Tuple[int, str], str] = {
            key: palette[idx % len(palette)]
            for idx, key in enumerate(self._plot_keys)
        }
        n = self._table_model.row_count()
        for row in range(n):
            key = self._table_model.key_for_row(row)
            color = key_to_color.get(key) if key is not None else None
            # We pass an icon via the model's DecorationRole, but the model
            # doesn't implement DecorationRole directly — instead we set it
            # directly on the view's persistent model index data via the
            # QSortFilterProxyModel/selection model. The simplest approach
            # for a QTableView is to use model.setData with DecorationRole.
            # Since TelemetryTableModel is read-only for that role, we store
            # the icon on a side dict and override paint via the delegate.
            # For now: skip — the _StatusBadgeDelegate handles col 8.
            # Plot color feedback is provided by the legend in the plot widget.

    def _redraw_plot(self) -> None:
        """Redraw all subplots with current data from _plot_history."""
        self._refresh_plot_indicators()
        if pg is None or not self._plot_panels:
            return
        if hasattr(self, "_plot_dock") and self._plot_dock is not None and not self._plot_dock.isVisible():
            return

        current_t = (datetime.now() - self._session_started).total_seconds()
        palette = self._current_plot_palette()

        color_offset = 0
        # Track the oldest sample still in any ring buffer. The history deques
        # are bounded (_plot_history_maxlen), so on long sessions xs[0] is well
        # past zero — anchoring the live X axis at 0 then leaves most of the
        # plot empty. Pin the left edge to the oldest sample we actually have.
        oldest_x: Optional[float] = None

        for panel in self._plot_panels:
            pi = panel.plot_item
            if hasattr(pi, "isVisible") and not pi.isVisible():
                color_offset += len(panel.assigned_keys)
                continue
            active_keys = set(panel.assigned_keys)

            # Remove curves for keys no longer assigned
            for key in list(panel.curves):
                if key not in active_keys:
                    pi.removeItem(panel.curves.pop(key))

            for local_idx, key in enumerate(panel.assigned_keys):
                buf = self._plot_history.get(key)
                if buf is None:
                    x_values = np.array([], dtype=float)
                    y_values = np.array([], dtype=float)
                else:
                    xs, ys = buf
                    # np.fromiter does a single pass over each deque — no
                    # zip-unpack pass, no tuple churn.
                    if xs:
                        x_values = np.fromiter(xs, dtype=float, count=len(xs))
                        y_values = np.fromiter(ys, dtype=float, count=len(ys))
                        first_x = float(x_values[0])
                        if oldest_x is None or first_x < oldest_x:
                            oldest_x = first_x
                    else:
                        x_values = np.array([], dtype=float)
                        y_values = np.array([], dtype=float)

                color = palette[(color_offset + local_idx) % len(palette)]
                label = f"0x{key[0]:04X} {key[1]}"

                if key not in panel.curves:
                    panel.curves[key] = pi.plot(name=label, pen=pg.mkPen(color, width=1.8))
                    # Cache the colour on the curve itself so we can skip the
                    # setPen + mkPen allocation on every subsequent redraw —
                    # the colour only changes when the assignment shifts.
                    panel.curves[key].__bh_color = color  # type: ignore[attr-defined]
                elif getattr(panel.curves[key], "__bh_color", None) != color:
                    panel.curves[key].setPen(pg.mkPen(color, width=1.8))
                    panel.curves[key].__bh_color = color  # type: ignore[attr-defined]

                panel.curves[key].setData(
                    x_values, y_values,
                    autoDownsample=True,
                    clipToView=True,
                )

            color_offset += len(panel.assigned_keys)

        # Live mode X range. Two cases:
        #   - No data yet: anchor [0, INITIAL_WINDOW] so the axis reads 0 at
        #     the left while waiting for the first packet.
        #   - Data present: anchor [oldest_x, current_t * 1.05] so the curves
        #     fill the panel instead of crowding into the right edge once the
        #     ring buffer has dropped early samples.
        # The re-entrancy guard stops sigXRangeChanged from flipping us to Explore.
        if self._plot_live and self._plot_panels:
            self._plot_range_changing = True
            try:
                first_pi = self._plot_panels[0].plot_item
                if oldest_x is None:
                    x_min = 0.0
                    x_max = _PLOT_INITIAL_WINDOW_S
                else:
                    x_min = oldest_x
                    # Small right padding (5%) so the newest point isn't flush
                    # against the edge. Guard against a near-zero span on the
                    # very first packet by enforcing a minimum window width.
                    span = max(current_t - oldest_x, _PLOT_INITIAL_WINDOW_S)
                    x_max = oldest_x + span * 1.05
                first_pi.setXRange(x_min, x_max, padding=0)
            finally:
                self._plot_range_changing = False

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        if col in (3, 5, 6):
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        elif col == 8:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self._table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def _refresh_config_status(self) -> None:
        if self._config is None:
            return
        protocol = self._config.protocol
        signal_count = len(self._config.all_signals)
        self._config_label.setText(f"Config: {self._config_path}")
        self._protocol_label.setText(
            f"Protocol: header {protocol.header.hex(' ').upper()}, CRC {protocol.crc_type}"
        )
        self._frames_label.setText(
            f"Frames: {len(self._config.signals_by_frame)}   Variables: {signal_count}   TX: {len(self._config.tx_commands)}"
        )

    def _refresh_action_state(self) -> None:
        ready = self._config is not None
        self._load_log_action.setEnabled(ready)
        self._clear_action.setEnabled(ready)
        # Logging requires an active connection; _set_connection_ui controls this.
        # Only set enabled=True here if we're currently connected.
        self._logging_action.setEnabled(ready and self._serial is not None)

    def _set_connection_ui(self, connected: bool) -> None:
        self._connect_action.setText("Disconnect" if connected else "Connect")
        # Connect button: pink = active/danger (disconnect), green = safe/idle
        self._style_action_btn(
            self._connect_action,
            _BTN_PINK if connected else _BTN_GREEN,
        )
        # Logging button: green = connected & ready, yellow = disabled (no device)
        self._style_action_btn(
            self._logging_action,
            _BTN_GREEN if connected else _BTN_YELLOW,
        )
        # Logging action only enabled while connected
        self._logging_action.setEnabled(connected)
        if not connected:
            # Reset polling button colour and state too when disconnecting
            self._style_action_btn(self._polling_action, _BTN_GREEN)
            self._polling_action.setChecked(False)
            self._polling_action.setText("Start Auto-Fetch")
        if connected:
            self._led_label.setStyleSheet("color: #66BB6A;")
            self._led_label.setToolTip("Connected")
        else:
            self._led_label.setStyleSheet("color: #ef5350;")
            self._led_label.setToolTip("Disconnected")

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _toast(self, text: str, timeout_ms: int = 2500) -> None:
        """Show a non-modal transient notification in the bottom-right corner.

        Use for low-stakes confirmations like "Theme changed" or "Layout
        reset" — anything that previously begged for a popup but doesn't
        actually need acknowledgement. ``QMessageBox`` is still right for
        anything the user must read before continuing.
        """
        toast = getattr(self, "_toast_label", None)
        if toast is None:
            toast = QLabel(self)
            toast.setObjectName("bytehoundToast")
            toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Theme-adaptive colours: dark toast on light bg, lighter toast on dark bg.
            theme = str(self._settings.value("ui/theme", "dark"))
            if theme == "light":
                bg_rgba = "rgba(30, 41, 59, 235)"   # Slate-800 @ 92%
                fg = "#F8FAFC"                       # Slate-50
            else:
                bg_rgba = "rgba(241, 245, 249, 230)"  # Slate-100 @ 90%
                fg = "#0F172A"                         # Slate-900
            toast.setStyleSheet(
                f"QLabel#bytehoundToast {{"
                f"  background: {bg_rgba};"
                f"  color: {fg};"
                f"  padding: 8px 14px;"
                f"  border-radius: 6px;"
                f"  font-size: 12px;"
                f"}}"
            )
            toast.hide()
            self._toast_label = toast
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(toast.hide)

        toast.setText(text)
        toast.adjustSize()
        # Anchor near the bottom-right of the main window, above the status
        # bar. Re-position on every show so the toast still appears in the
        # right place after a window resize.
        margin = 16
        sb_height = self.statusBar().height() if self.statusBar() else 0
        x = self.width() - toast.width() - margin
        y = self.height() - toast.height() - sb_height - margin
        toast.move(max(margin, x), max(margin, y))
        toast.raise_()
        toast.show()
        self._toast_timer.start(max(500, int(timeout_ms)))

    def _log_activity(self, text: str) -> None:
        if not hasattr(self, "_activity_log") or self._activity_log is None:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self._activity_log.appendPlainText(f"{timestamp}  {text}")

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
        QMessageBox.information(self, title, message)

    def _popup_warning(self, title: str, message: str) -> None:
        self._log_popup("WARN", title, message)
        QMessageBox.warning(self, title, message)

    def _popup_critical(self, title: str, message: str) -> None:
        self._log_popup("ERROR", title, message)
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


    def _format_console_row(self, packet: ParsedPacket) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        hex_text = packet.raw.hex(" ").upper()
        if packet.ok:
            return f"{timestamp}, RX, {hex_text}"
        return f"{timestamp}, ERR, {packet.error or 'unknown'}, {hex_text}"

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._log_activity("[SESSION] Close requested by user")
        # Warn if logging is active — data is safe (flushed per-frame) but
        # the user may not realise they are about to stop a recording.
        if self._logging:
            reply = QMessageBox.question(
                self,
                "Active Log Session",
                "A log session is currently recording.\n\n"
                "Stop logging and close the application?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        # _disconnect() guarantees: stop timer → flush logs → stop worker → null.
        self._disconnect(reason="Application closed")
        self._save_window_state()
        super().closeEvent(event)


def _format_number(value) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
