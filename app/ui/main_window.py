"""PySide6 main window for the Serial monitor."""

from __future__ import annotations

import os
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
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

APP_ORG = "Decibels"
APP_NAME = "Serial-MonitorApp"
APP_DISPLAY_NAME = "Serial Monitor"


def _project_root() -> Path:
    """Return the dir to look for runtime assets (branding/, version.json).

    Frozen build: next to Serial-MonitorApp.exe (build.py copies branding/ here).
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


_PLOT_PALETTE = (
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#17becf", "#bcbd22",
    "#ff9896", "#98df8a", "#c5b0d5", "#393b79",
)


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


class _StatusBadgeDelegate(QStyledItemDelegate):
    """Paint the Status column as a rounded pill badge.

    Green for "ok", red for "error"/"fail", orange for everything else
    non-empty/non-dash. Falls back to the default delegate for empty / "-".
    Colors mirror the LED status palette for visual consistency.
    """

    _GREEN = QColor("#10B981")   # Tailwind emerald-500
    _RED = QColor("#EF4444")     # Tailwind rose-500
    _ORANGE = QColor("#F59E0B")  # Tailwind amber-500

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        if not text or text == "-":
            super().paint(painter, option, index)
            return

        # Honor selection highlight from the style first.
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        lower = text.lower()
        if "ok" in lower and "error" not in lower:
            color = self._GREEN
        elif "error" in lower or "fail" in lower:
            color = self._RED
        else:
            color = self._ORANGE

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
    ("Frame", 100),
    ("Group", 90),
    ("Variable", 190),
    ("Start B.", 60),
    ("Data Type", 75),
    ("Raw", 95),
    ("Value", 95),
    ("Unit", 70),
    ("Status", 190),
    ("Updated", 110),
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
QToolButton#primaryAction:disabled { background-color: #555; color: #aaa; }
QMenu { padding: 5px; }
QMenu::item {
    padding: 6px 24px 6px 24px;
    border-radius: 4px;
}
QMenu::item:selected { background-color: #2563EB; color: white; }
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
"""


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
    """
    plot_item: object                                     # pg.PlotItem
    assigned_keys: List[Tuple[int, str]] = field(default_factory=list)
    curves:        Dict[Tuple[int, str], object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Configuration dialogs
# ---------------------------------------------------------------------------

class ConnectionDialog(QDialog):
    """Modal dialog for configuring and opening a serial connection.

    Pre-populates all fields from ``QSettings`` so the user's last-used
    port/baud/etc. are remembered between sessions.  On Accept the chosen
    values are persisted back to ``QSettings`` and exposed via
    ``get_settings()``.
    """

    def __init__(self, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Serial Connection Settings")
        self.setMinimumWidth(360)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Port row with inline Refresh button
        port_row = QWidget(self)
        port_hl = QHBoxLayout(port_row)
        port_hl.setContentsMargins(0, 0, 0, 0)
        self._port_combo = QComboBox(port_row)
        self._port_combo.setMinimumWidth(180)
        refresh_btn = QPushButton("⟳", port_row)
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh port list")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_hl.addWidget(self._port_combo, 1)
        port_hl.addWidget(refresh_btn)

        self._baud_combo = QComboBox(self)
        self._baud_combo.addItems(["9600", "19200", "38400", "57600", "115200",
                                    "230400", "460800", "921600"])

        self._data_bits_combo = QComboBox(self)
        self._data_bits_combo.addItems(["8", "7"])

        self._stop_bits_combo = QComboBox(self)
        self._stop_bits_combo.addItems(["1", "1.5", "2"])

        self._parity_combo = QComboBox(self)
        self._parity_combo.addItems(["N", "E", "O"])

        self._timeout_combo = QComboBox(self)
        self._timeout_combo.addItems(["20", "50", "100", "250", "500", "1000"])

        form.addRow("Port", port_row)
        form.addRow("Baud rate", self._baud_combo)
        form.addRow("Data bits", self._data_bits_combo)
        form.addRow("Stop bits", self._stop_bits_combo)
        form.addRow("Parity", self._parity_combo)
        form.addRow("Timeout (ms)", self._timeout_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_ports()
        self._restore_from_settings()

    # ------------------------------------------------------------------
    def _refresh_ports(self) -> None:
        current = self._port_combo.currentData(Qt.ItemDataRole.UserRole) or ""
        ports = list(available_ports())
        self._port_combo.clear()
        if ports:
            for device, description in ports:
                label = description if device in description else f"{device} \u2013 {description}"
                self._port_combo.addItem(label, userData=device)
            for i in range(self._port_combo.count()):
                if self._port_combo.itemData(i, Qt.ItemDataRole.UserRole) == current:
                    self._port_combo.setCurrentIndex(i)
                    break
        else:
            self._port_combo.addItem("No ports found", userData="")

    def _restore_from_settings(self) -> None:
        s = self._settings
        saved_port = s.value("conn/port", "")
        for i in range(self._port_combo.count()):
            if self._port_combo.itemData(i, Qt.ItemDataRole.UserRole) == saved_port:
                self._port_combo.setCurrentIndex(i)
                break
        self._baud_combo.setCurrentText(str(s.value("conn/baud", "115200")))
        self._data_bits_combo.setCurrentText(str(s.value("conn/data_bits", "8")))
        self._stop_bits_combo.setCurrentText(str(s.value("conn/stop_bits", "1")))
        self._parity_combo.setCurrentText(str(s.value("conn/parity", "N")))
        self._timeout_combo.setCurrentText(str(s.value("conn/timeout_ms", "50")))

    def _on_accept(self) -> None:
        s = self._settings
        s.setValue("conn/port",       self._port_combo.currentData(Qt.ItemDataRole.UserRole) or "")
        s.setValue("conn/baud",       self._baud_combo.currentText())
        s.setValue("conn/data_bits",  self._data_bits_combo.currentText())
        s.setValue("conn/stop_bits",  self._stop_bits_combo.currentText())
        s.setValue("conn/parity",     self._parity_combo.currentText())
        s.setValue("conn/timeout_ms", self._timeout_combo.currentText())
        self.accept()

    def get_settings(self) -> "SerialSettings":
        return SerialSettings(
            port=self._port_combo.currentData(Qt.ItemDataRole.UserRole) or self._port_combo.currentText(),
            baud_rate=int(self._baud_combo.currentText()),
            data_bits=int(self._data_bits_combo.currentText()),
            stop_bits=float(self._stop_bits_combo.currentText()),
            parity=self._parity_combo.currentText(),
            timeout_ms=int(self._timeout_combo.currentText()),
        )


class PollingConfigDialog(QDialog):
    """Modal dialog for selecting which polling targets are active.

    Each target from the loaded ``FrameConfig.polling_schedules`` is shown
    as a labelled checkbox.  Selections are persisted per ``target_id`` in
    ``QSettings`` so they survive between sessions.
    """

    def __init__(self, schedules, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Poll Schedule")
        self.setMinimumWidth(320)
        self._settings = settings
        self._schedules = schedules

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel("Select which targets to poll automatically:", self)
        header.setWordWrap(True)
        layout.addWidget(header)

        self._list = QListWidget(self)
        for sched in schedules:
            key = f"poll/enabled/0x{sched.target_id:04X}"
            # Default to whatever the config says, but QSettings overrides it.
            default_checked = sched.enabled
            checked = settings.value(key, default_checked, type=bool)
            label = f"0x{sched.target_id:04X}  —  every {sched.interval_ms} ms"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, sched.target_id)
            self._list.addItem(item)
        layout.addWidget(self._list)

        # Select-all / none shortcuts
        btn_row = QHBoxLayout()
        all_btn = QPushButton("Select All", self)
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn = QPushButton("Select None", self)
        none_btn.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start Polling")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(state)

    def _on_accept(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            target_id = item.data(Qt.ItemDataRole.UserRole)
            key = f"poll/enabled/0x{target_id:04X}"
            self._settings.setValue(key, item.checkState() == Qt.CheckState.Checked)
        self.accept()

    def get_enabled_ids(self) -> set:
        """Return the set of target_ids whose checkbox is checked."""
        result = set()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.add(item.data(Qt.ItemDataRole.UserRole))
        return result


class MainWindow(QMainWindow):

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
        self._delta_t_ms = 0.0
        self._row_index: Dict[Tuple[int, str], int] = {}
        self._packet_count = 0
        self._error_count = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._logging = False
        self._raw_logger: Optional[RawLogger] = None
        self._decoded_logger: Optional[DecodedLogger] = None
        self._settings = QSettings(APP_ORG, APP_NAME)
        self._tx_field_inputs: Dict[str, QLineEdit] = {}

        # Timer removed; using PollingWorker QThread

        self._plot_history: Dict[Tuple[int, str], Deque[Tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=250_000)
        )
        # Multi-grid plot state
        self._plot_panels: List[PlotPanel] = []   # one entry per subplot cell
        self._gl_widget = None                     # pg.GraphicsLayoutWidget
        self._plot_widget = None                   # alias → panels[0].plot_item (compat)
        self._plot_curves: Dict = {}               # compat shim (unused after refactor)
        self._plot_keys: List[Tuple[int, str]] = []  # union of all panel keys
        self._curve_icon_cache: Dict[Tuple[int, str, str], QIcon] = {}
        self._session_started = datetime.now()
        self._plot_rolling: bool = True
        self._plot_range_changing: bool = False


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
          - ``_QSS_DARK_OVERRIDES`` only when ``theme == "dark"`` — explicit hex
            codes that fix dock title bars, separators, table body, and inputs.
        """
        qss = _QSS_BASE
        if theme == "dark":
            qss += "\n" + _QSS_DARK_OVERRIDES
        self.setStyleSheet(qss)


    def _build_actions(self) -> None:

        # Pick icon tint color based on the saved theme for secondary actions.
        # Primary actions (Connect / Poll / Log) always get white icons because
        # they always sit on a coloured background (_BTN_GREEN / YELLOW / PINK).
        _saved_theme = str(self._settings.value("ui/theme", "dark"))
        _ic = "#F8FAFC" if _saved_theme == "dark" else "#1F2937"
        _PRIMARY = "#FFFFFF"   # always white on coloured button backgrounds

        self._connect_action = QAction(_icon("mdi6.usb-port", _PRIMARY), "Connect", self)
        self._connect_action.triggered.connect(self._on_toggle_connect)

        self._polling_action = QAction(_icon("mdi6.play-circle-outline", _PRIMARY), "Start Auto-Fetch", self)
        self._polling_action.setCheckable(True)
        self._polling_action.setChecked(False)
        self._polling_action.triggered.connect(self._on_toggle_polling)

        self._logging_action = QAction(_icon("mdi6.record-rec", _PRIMARY), "Start Logging", self)
        self._logging_action.triggered.connect(self._on_toggle_logging)

        self._load_config_action = QAction(_icon("mdi6.folder-upload-outline", _ic), "Import Config", self)
        self._load_config_action.triggered.connect(self._on_load_config)

        self._export_template_action = QAction(_icon("mdi6.file-export-outline", _ic), "Export Template", self)
        self._export_template_action.triggered.connect(self._on_export_template)

        self._load_log_action = QAction(_icon("mdi6.history", _ic), "Load Raw Log", self)
        self._load_log_action.triggered.connect(self._on_load_log)

        self._clear_action = QAction(_icon("mdi6.broom", _ic), "Clear Console / Log", self)
        self._clear_action.triggered.connect(self._on_clear)

        self._copy_value_action = QAction(_icon("mdi6.content-copy", _ic), "Copy Value", self)
        self._copy_value_action.setShortcut("Ctrl+Shift+C")
        self._copy_value_action.triggered.connect(self._on_copy_value)

        self._exit_action = QAction(_icon("mdi6.exit-to-app", _ic), "Exit", self)
        self._exit_action.triggered.connect(self.close)

        self._info_action = QAction(_icon("mdi6.information-outline", _ic), "About Serial Monitor", self)
        self._info_action.triggered.connect(self._on_info)

        self._docs_action = QAction(_icon("mdi6.book-open-page-variant-outline", _ic), "View Documentation", self)
        self._docs_action.triggered.connect(self._on_view_docs)

        self._update_action = QAction(_icon("mdi6.cloud-download-outline", _ic), "Check for Updates", self)
        self._update_action.triggered.connect(self._on_check_updates)

        self._analysis_action = QAction(_icon("mdi6.chart-line", _ic), "Analysis Suite", self)
        self._analysis_action.triggered.connect(self._on_analysis_suite)


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
        _add_sep()

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._docs_action)
        help_menu.addAction(self._update_action)
        help_menu.addSeparator()
        help_menu.addAction(self._info_action)

    def _on_check_updates(self) -> None:
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
        if not hasattr(self, "_analysis_window") or self._analysis_window is None:
            from .analysis_suite import AnalysisSuiteWindow
            self._analysis_window = AnalysisSuiteWindow(self)
        self._analysis_window.show()
        self._analysis_window.raise_()
        self._analysis_window.activateWindow()

    def _on_update_available(self, version: str, url: str, release_notes: str) -> None:
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
            self._download_update(url)

    def _download_update(self, url: str) -> None:
        self._progress = QProgressDialog("Downloading update...", "Cancel", 0, 100, self)
        self._progress.setWindowTitle("Updater")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.show()

        dest_path = str(Path(os.environ.get("TEMP", ".")) / f"{APP_NAME}_Update.exe")
        self._downloader = UpdateDownloader(url, dest_path)
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

    def _on_info(self) -> None:
        self._popup_about(
            "About Serial Monitor",
            (
                f"{APP_DISPLAY_NAME} App\n\n"
                "Version: 0.1.0\n"
                "Publisher: Decibels\n"
                "Build Date: May 2026\n"
                "Website: https://lms.decibelslab.com/\n\n"
                "Serial Data Logger and Visualizer.\n"
                "Configuration-driven decoding."
            ),
        )

    def _on_view_docs(self) -> None:
        docs_path = Path(__file__).resolve().parents[1] / "resources" / "index.html"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(docs_path)))

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
        self._logo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logo_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://lms.decibelslab.com/")))
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
        self._status_delegate = _StatusBadgeDelegate(self._table)
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

        self._group_combo = QComboBox(center_widget)
        self._group_combo.addItem("All")
        self._group_combo.setMinimumWidth(150)
        self._group_combo.currentTextChanged.connect(self._apply_group_filter)

        self._show_calcs_check = QCheckBox("Show calculations", center_widget)
        self._show_calcs_check.setChecked(True)
        self._show_calcs_check.toggled.connect(lambda: self._apply_group_filter(self._group_combo.currentText()))

        self._search_input.textChanged.connect(lambda: self._apply_group_filter(self._group_combo.currentText()))

        top_row.addWidget(self._search_input, 1)
        top_row.addWidget(QLabel("Group", center_widget))
        top_row.addWidget(self._group_combo)
        top_row.addWidget(self._show_calcs_check)

        center_layout.addLayout(top_row)
        center_layout.addWidget(self._table)
        
        self.setCentralWidget(center_widget)

        self._settings_dock = QDockWidget("Connection", self)
        self._settings_dock.setObjectName("SettingsDock")
        self._settings_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._settings_dock.setWidget(self._build_left_panel())
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._settings_dock)

        self._plot_dock = QDockWidget("Live Plot", self)
        self._plot_dock.setObjectName("PlotDock")
        self._plot_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._plot_dock.setWidget(self._build_plot_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._plot_dock)

        self._bitfields_dock = QDockWidget("Bitfields", self)
        self._bitfields_dock.setObjectName("BitfieldsDock")
        self._bitfields_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._bitfields_dock.setWidget(self._build_bitfield_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._bitfields_dock)
        self.tabifyDockWidget(self._plot_dock, self._bitfields_dock)

        self._enums_dock = QDockWidget("Enums", self)
        self._enums_dock.setObjectName("EnumsDock")
        self._enums_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._enums_dock.setWidget(self._build_enum_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._enums_dock)
        self.tabifyDockWidget(self._plot_dock, self._enums_dock)

        self._tx_dock = QDockWidget("TX Commands", self)
        self._tx_dock.setObjectName("TxDock")
        self._tx_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._tx_dock.setWidget(self._build_tx_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tx_dock)
        self.tabifyDockWidget(self._plot_dock, self._tx_dock)

        self._editor_dock = QDockWidget("Parameter Editor", self)
        self._editor_dock.setObjectName("EditorDock")
        self._editor_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._editor_dock.setWidget(self._build_editor_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._editor_dock)
        self.tabifyDockWidget(self._plot_dock, self._editor_dock)



        self._plot_dock.raise_()

        self._console = QPlainTextEdit(self)
        self._console.setReadOnly(True)
        self._console.setPlaceholderText("Raw RX/TX frames will appear here...")
        self._console.setMaximumBlockCount(3000)
        self._console.setFont(QFont("Consolas", 10))

        self._console_dock = QDockWidget("Raw Console", self)
        self._console_dock.setObjectName("ConsoleDock")
        self._console_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self._console_dock.setWidget(self._console)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._console_dock)

        self._activity_log = QPlainTextEdit(self)
        self._activity_log.setReadOnly(True)
        self._activity_log.setPlaceholderText("Application activity will appear here...")
        self._activity_log.setMaximumBlockCount(5000)
        self._activity_log.setFont(QFont("Consolas", 10))

        self._activity_dock = QDockWidget("Activity Log", self)
        self._activity_dock.setObjectName("ActivityDock")
        self._activity_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self._activity_dock.setWidget(self._activity_log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._activity_dock)
        self.tabifyDockWidget(self._console_dock, self._activity_dock)
        self._console_dock.raise_()

        for dock in (
            self._settings_dock,
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

        panels_menu = menu.addMenu("Panels")
        for dock, label in (
            (self._settings_dock, "Connection"),
            (self._plot_dock, "Live Plot"),
            (self._bitfields_dock, "Bitfields"),
            (self._enums_dock, "Enums"),
            (self._tx_dock, "TX Commands"),
            (self._editor_dock, "Parameter Editor"),
            (self._console_dock, "Raw Console"),
            (self._activity_dock, "Activity Log"),
        ):
            action = dock.toggleViewAction()
            action.setText(label)
            panels_menu.addAction(action)

        theme_menu = menu.addMenu("Theme")
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

        reset_layout_action = QAction(_icon("mdi6.view-grid-outline", ic), "Reset Window Layout", self)
        reset_layout_action.triggered.connect(self._reset_window_layout)
        menu.addAction(reset_layout_action)

        menu.addSeparator()

        reset_plot_action = QAction(_icon("mdi6.image-auto-adjust", ic), "Auto-Range Plot", self)
        reset_plot_action.setShortcut("Ctrl+R")
        reset_plot_action.triggered.connect(self._reset_plot_view)
        menu.addAction(reset_plot_action)

    def _apply_theme(self, theme: str) -> None:
        if qdarktheme is None:
            return
        try:
            qdarktheme.setup_theme(theme, corner_shape="rounded")
        except Exception as exc:
            self._popup_warning("Theme", f"Failed to apply theme: {exc}")
            return
        # Re-apply our card + dark-override QSS on top of the fresh qdarktheme base.
        self._apply_card_qss(theme)
        # Rebuild qtawesome icons with the correct tint for the new theme.
        self._rebuild_action_icons(theme)
        self._settings.setValue("ui/theme", theme)
        from PySide6.QtWidgets import QApplication
        # Schedule title-bar update via singleShot so the native HWND is stable.
        dark = (theme == "dark")
        for w in QApplication.topLevelWidgets():
            QTimer.singleShot(0, lambda _w=w, _d=dark: _apply_windows_dark_titlebar(_w, _d))
        self._set_status(f"Theme: {theme}")

    def _rebuild_action_icons(self, theme: str) -> None:
        """Re-tint all QAction icons to match the current theme.

        qtawesome bakes the color into the QPixmap at icon() creation time, so
        we must recreate the icons whenever the theme changes.

        Primary actions (Connect / Poll / Log) sit on coloured backgrounds so
        their icons are *always* white — independent of the app theme.
        Secondary actions (file/edit/help) use the standard theme tint.
        """
        color = "#F8FAFC" if theme == "dark" else "#1F2937"

        # Primary: always white (coloured button background)
        for action, name in [
            (self._connect_action,  "mdi6.usb-port"),
            (self._polling_action,  "mdi6.play-circle-outline"),
            (self._logging_action,  "mdi6.record-rec"),
        ]:
            action.setIcon(_icon(name, "#FFFFFF"))

        # Secondary: follow the active theme
        for action, name in [
            (self._load_config_action,      "mdi6.folder-upload-outline"),
            (self._export_template_action,  "mdi6.file-export-outline"),
            (self._load_log_action,         "mdi6.history"),
            (self._clear_action,            "mdi6.broom"),
            (self._copy_value_action,       "mdi6.content-copy"),
            (self._exit_action,             "mdi6.exit-to-app"),
            (self._info_action,             "mdi6.information-outline"),
            (self._analysis_action,         "mdi6.chart-line"),
            (self._docs_action,             "mdi6.book-open-variant"),
            (self._update_action,           "mdi6.update"),
        ]:
            action.setIcon(_icon(name, color))

        # View menu is rebuilt from scratch each time — call it with the new tint
        self._populate_view_menu()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        theme = str(self._settings.value("ui/theme", "dark"))
        # Use singleShot(0) so the native HWND is fully created before we call
        # DwmSetWindowAttribute — calling it synchronously in showEvent can
        # return a non-zero (failure) result because the handle isn't stable yet.
        QTimer.singleShot(0, lambda: _apply_windows_dark_titlebar(self, dark=(theme == "dark")))

    def _reset_plot_view(self) -> None:
        """Ctrl+R / Reset View: auto-range all panels so all data is visible
        (including t=0), then switch to Explore mode so it stays put.
        """
        if pg is None or not self._plot_panels:
            return
        for panel in self._plot_panels:
            panel.plot_item.getViewBox().autoRange()
        self._plot_rolling = False
        self._plot_mode_label.setText("🔍 Explore  (Ctrl+R = Rolling)")

    def _reset_window_layout(self) -> None:
        self.restoreGeometry(self._default_geometry)
        self.restoreState(self._default_state)
        for dock in (
            self._settings_dock,
            self._plot_dock,
            self._bitfields_dock,
            self._enums_dock,
            self._tx_dock,
            self._editor_dock,
            self._editor_dock,
            self._console_dock,
            self._activity_dock,
        ):
            dock.setVisible(True)
        self._toolbar.setVisible(True)

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

    def _build_left_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- Serial Connection status card ----------------------------------

        proto_card, proto_layout = self._card("Protocol Config", panel)

        recent_row = QHBoxLayout()
        self._recent_config_combo = QComboBox(proto_card)
        self._recent_config_combo.setMinimumWidth(120)
        recent_load = QPushButton("Load", proto_card)
        recent_load.clicked.connect(self._on_load_recent_config)
        recent_row.addWidget(self._recent_config_combo, 1)
        recent_row.addWidget(recent_load)
        proto_layout.addLayout(recent_row)

        self._config_label = QLabel("No config loaded", proto_card)
        self._protocol_label = QLabel("-", proto_card)
        self._frames_label = QLabel("-", proto_card)
        for lbl in (self._config_label, self._protocol_label, self._frames_label):
            lbl.setWordWrap(True)
            proto_layout.addWidget(lbl)

        logging_row = QHBoxLayout()
        self._logging_label = QLabel("Logging: stopped", proto_card)
        self._logging_label.setWordWrap(True)
        logging_row.addWidget(self._logging_label, 1)
        self._open_log_btn = QPushButton("\U0001f4c2")
        self._open_log_btn.setToolTip("Open Log Folder")
        self._open_log_btn.setFixedWidth(28)
        self._open_log_btn.clicked.connect(self._on_open_log_folder)
        logging_row.addWidget(self._open_log_btn)
        proto_layout.addLayout(logging_row)
        layout.addWidget(proto_card)

        # --- Poll Schedule status card --------------------------------------
        poll_card, poll_layout = self._card("Poll Schedule", panel)
        self._poll_status_label = QLabel("No targets loaded", poll_card)
        self._poll_status_label.setWordWrap(True)
        poll_layout.addWidget(self._poll_status_label)

        # Read-only list shows which targets are active (updated on config load
        # and after each PollingConfigDialog accept).
        self._polling_list = QListWidget(poll_card)
        self._polling_list.setMaximumHeight(130)
        self._polling_list.setEnabled(False)   # display only in sidebar
        poll_layout.addWidget(self._polling_list)

        poll_configure_btn = QPushButton("Configure\u2026", poll_card)
        poll_configure_btn.setToolTip("Open polling target selector")
        poll_configure_btn.clicked.connect(self._open_poll_config_dialog)
        poll_layout.addWidget(poll_configure_btn)
        layout.addWidget(poll_card)

        layout.addStretch(1)
        panel.setMinimumWidth(240)
        return panel

    def _build_plot_tab(self) -> QWidget:
        outer = QWidget(self)
        root_layout = QVBoxLayout(outer)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        # ── Top control bar ────────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(8)

        hint = QLabel("Right-click a table row → Add to Plot  |  Ctrl+R = Reset view")
        hint.setEnabled(False)
        hint.setStyleSheet("font-size: 11px;")
        controls.addWidget(hint)
        controls.addStretch(1)

        controls.addWidget(QLabel("Window (s):"))
        self._plot_window_combo = QComboBox(outer)
        self._plot_window_combo.addItems(["30", "60", "120", "300", "600"])
        saved_w = str(self._settings.value("plot/window", "60"))
        self._plot_window_combo.setCurrentText(saved_w)
        self._plot_window_combo.currentIndexChanged.connect(self._on_plot_window_changed)
        controls.addWidget(self._plot_window_combo)

        controls.addWidget(QLabel("Layout:"))
        self._layout_combo = QComboBox(outer)
        self._layout_combo.addItems(list(GRID_LAYOUTS.keys()))
        saved_layout = str(self._settings.value("plot/layout", "2×1"))
        self._layout_combo.setCurrentText(saved_layout if saved_layout in GRID_LAYOUTS else "2×1")
        self._layout_combo.currentTextChanged.connect(self._on_layout_changed)
        controls.addWidget(self._layout_combo)

        reset_btn = QPushButton("⟳ Reset View", outer)
        reset_btn.setToolTip("Snap all subplots back to rolling mode (Ctrl+R)")
        reset_btn.clicked.connect(self._reset_plot_view)
        controls.addWidget(reset_btn)

        clear_btn = QPushButton("Clear", outer)
        clear_btn.clicked.connect(self._clear_plot)
        controls.addWidget(clear_btn)

        export_btn = QPushButton("Export", outer)
        export_btn.clicked.connect(self._export_plot_data)
        controls.addWidget(export_btn)

        self._plot_mode_label = QLabel("🔄 Rolling", outer)
        self._plot_mode_label.setToolTip(
            "Rolling: X-axis auto-scrolls.\n"
            "Explore: You panned/zoomed. Click Reset View or Ctrl+R to return."
        )
        controls.addWidget(self._plot_mode_label)

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
        self._gl_widget.setBackground(pg.mkColor("#1e1e1e"))
        root_layout.addWidget(self._gl_widget, 1)

        # Build the initial grid from saved (or default) layout
        rows, cols = GRID_LAYOUTS.get(self._layout_combo.currentText(), (2, 1))
        self._rebuild_plot_grid(rows, cols, restore=True)

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
                    decoded = [tuple(k) for k in raw if isinstance(k, (list, tuple)) and len(k) == 2]
                else:
                    decoded = []
                panel_keys.append(decoded)
        else:
            # Spread old keys: panel i gets old_keys[i] if it exists
            panel_keys = [old_keys[i] if i < len(old_keys) else [] for i in range(n)]

        # Build PlotItems and variable strips
        first_vb = None
        for idx in range(n):
            row_idx, col_idx = divmod(idx, cols)
            pi = self._gl_widget.addPlot(row=row_idx, col=col_idx)
            pi.showGrid(x=True, y=True, alpha=0.25)
            pi.addLegend(offset=(10, 10))
            pi.getViewBox().setMouseEnabled(x=True, y=True)

            # Share X-axis with the first subplot (oscilloscope-style)
            if first_vb is None:
                first_vb = pi.getViewBox()
            else:
                pi.getViewBox().setXLink(first_vb)

            # Detect user pan/zoom → switch to Explore mode
            pi.getViewBox().sigXRangeChanged.connect(self._on_plot_range_changed)

            panel = PlotPanel(plot_item=pi, assigned_keys=list(panel_keys[idx]))
            self._plot_panels.append(panel)

            # Redraw existing curves for this panel
            for key in panel.assigned_keys:
                label = f"0x{key[0]:04X} {key[1]}"
                color_idx = sum(len(p.assigned_keys) for p in self._plot_panels[:-1]) + len(panel.curves)
                color = _PLOT_PALETTE[color_idx % len(_PLOT_PALETTE)]
                panel.curves[key] = pi.plot(name=label, pen=pg.mkPen(color, width=2))

            # Build variable-strip widget for this panel
            if hasattr(self, "_panel_strip_layout") and self._panel_strip_layout is not None:
                strip = self._make_panel_strip(idx)
                self._panel_strip_layout.addWidget(strip, 1)

        # Update aggregate _plot_keys
        self._sync_plot_keys()
        # Persist new layout
        self._settings.setValue("plot/layout", self._layout_combo.currentText())

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
        hl.addStretch(1)
        return strip

    def _refresh_panel_strip_contents(self, panel_idx: int, layout: QHBoxLayout) -> None:
        """Add chip labels for each assigned key in the panel strip."""
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        color_offset = sum(len(self._plot_panels[i].assigned_keys) for i in range(panel_idx))
        for local_idx, key in enumerate(panel.assigned_keys):
            color = _PLOT_PALETTE[(color_offset + local_idx) % len(_PLOT_PALETTE)]
            chip = QPushButton(f"● {key[1]}  ✕")
            chip.setFixedHeight(22)
            chip.setStyleSheet(
                f"font-size:10px; padding:0 5px; border-radius:4px;"
                f"background:{color}; color:#fff; border:none;"
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
        self._rebuild_plot_grid(rows, cols, restore=False)
        self._redraw_plot()

    def _on_panel_add_signal(self, panel_idx: int) -> None:
        """Open a dialog to pick a signal to assign to panel *panel_idx*."""
        if self._config is None:
            self._popup_warning("Add Signal", "Load a configuration first.")
            return
        all_keys = [(sig.frame_id, sig.signal_name) for sig in self._config.all_signals]
        already: Set[Tuple[int, str]] = {k for p in self._plot_panels for k in p.assigned_keys}
        choices = [f"0x{fid:04X}  {nm}" for fid, nm in all_keys]
        if not choices:
            self._popup_information("Add Signal", "No signals available in the loaded config.")
            return
        text, ok = QInputDialog.getItem(
            self, f"Add signal to Panel {panel_idx + 1}",
            "Choose a signal:", choices, 0, False
        )
        if not ok:
            return
        chosen_idx = choices.index(text)
        key = all_keys[chosen_idx]
        self._add_signal_to_panel(panel_idx, key)

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
        self._bitfield_table = QTableWidget(0, 4, self)
        self._bitfield_table.setHorizontalHeaderLabels(["Frame", "Variable", "Bit", "State"])
        self._bitfield_table.verticalHeader().setVisible(False)
        self._bitfield_table.horizontalHeader().setStretchLastSection(True)
        return self._bitfield_table

    def _build_enum_tab(self) -> QWidget:
        self._enum_table = QTableWidget(0, 4, self)
        self._enum_table.setHorizontalHeaderLabels(["Frame", "Variable", "Raw", "Label"])
        self._enum_table.verticalHeader().setVisible(False)
        self._enum_table.horizontalHeader().setStretchLastSection(True)
        return self._enum_table

    
    def _build_editor_tab(self) -> QWidget:
        self._editor_table = QTableWidget(0, 4, self)
        self._editor_table.setHorizontalHeaderLabels(["Target ID", "Variable", "Current", "Action"])
        self._editor_table.verticalHeader().setVisible(False)
        self._editor_table.horizontalHeader().setStretchLastSection(True)
        return self._editor_table

    
    def _build_editor_tab(self) -> QWidget:
        self._editor_table = QTableWidget(0, 4, self)
        self._editor_table.setHorizontalHeaderLabels(["Target ID", "Variable", "Current", "Action"])
        self._editor_table.verticalHeader().setVisible(False)
        self._editor_table.horizontalHeader().setStretchLastSection(True)
        return self._editor_table

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

    def _load_config_from_path(self, path: Path) -> None:
        self._config = load_config(path)
        self._config_path = path
        self._parser = create_parser(self._config.protocol)
        self._session_started = datetime.now()
        self._plot_history.clear()
        self._packet_count = 0
        self._error_count = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._console.clear()
        self._populate_table_from_config()
        self._populate_group_selector()
        self._plot_keys.clear()
        self._populate_tx_commands()
        self._update_poll_status_sidebar()   # refresh sidebar read-only list
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
        if self._config_path is None:
            self._popup_information("Export template", "Load a config first.")
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export Excel template",
            str(Path.home() / "frame_config_template.xlsx"),
            "Excel workbook (*.xlsx)",
        )
        if not target:
            return
        try:
            export_excel_template(self._config_path, target)
        except Exception as exc:
            self._popup_critical("Export template", str(exc))
            return
        self._set_status(f"Exported Excel template to {target}")

    def _on_load_log(self) -> None:
        if self._config is None or self._parser is None:
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select raw log file", "", "Log files (*.csv *.txt *.log);;All files (*)"
        )
        if not path_str:
            return

        rows, errors = parse_log_file(path_str)
        if errors:
            self._popup_warning(
                "Log parse warnings",
                f"{len(errors)} line(s) skipped:\n" + "\n".join(errors[:5]),
            )
        for chunk in replay_bytes(rows):
            self._rx_bytes += len(chunk)
            self._parser.feed(chunk)
            for pkt in self._parser.extract_all():
                self._handle_packet(pkt)
        self._set_status(f"Replayed {len(rows)} log row(s) from {Path(path_str).name}")



    def _on_toggle_connect(self) -> None:
        # --- Already connected: disconnect immediately -----------------------
        if self._serial is not None and self._serial.is_open:
            self._ui_timer.stop()
            # Auto-stop logging before releasing the port
            if self._logging:
                self._stop_logging()
                self._log_activity("[INFO] Logging auto-stopped on disconnect")
            self._serial.close()
            self._serial = None
            self._set_connection_ui(False)
            self._set_status("Disconnected")
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
        self._set_status(f"Error: {err}")
        self._ui_timer.stop()
        if self._logging:
            self._stop_logging()
            self._log_activity("[INFO] Logging auto-stopped on serial error")
        if self._serial:
            self._serial.close()
            self._serial = None
        self._set_connection_ui(False)

    def _on_packets_received(self, batch: list) -> None:
        """Slot called by the worker's batch signal. Queues for the 60Hz UI timer.

        The underlying deque is bounded (maxlen=10_000) so a stalled Qt event
        loop cannot cause an OOM crash — oldest packets are silently dropped.
        """
        self._pending_packets.extend(batch)

    def _flush_ui(self) -> None:
        """Drain the pending packet queue and refresh the UI at 60 Hz."""
        if not self._pending_packets:
            return
        # Swap atomically: take all pending packets, reset the deque.
        packets = list(self._pending_packets)
        self._pending_packets.clear()
        for packet in packets:
            self._handle_packet(packet)
        # Commit all staged model cell updates in ONE dataChanged per row.
        self._table_model.commit_staged()
        # Redraw the plot once for the entire batch.
        self._redraw_plot()

    def _on_connection_lost(self) -> None:
        """Called when the worker detects a physical USB unplug."""
        self._ui_timer.stop()
        # Auto-stop logging so files are flushed and the button resets.
        if self._logging:
            self._stop_logging()
            self._log_activity("[INFO] Logging auto-stopped on USB disconnect")
        self._serial = None  # worker already cleaned up the port
        self._set_connection_ui(False)
        self._set_status("USB device disconnected")
        self._log_activity("[WARN] Connection lost — USB device was disconnected")

    def _on_device_timeout(self) -> None:
        """Called when the device is connected but has sent no data for ≥ 3 s."""
        # Amber LED — connected but silent
        self._led_label.setStyleSheet("color: #F59E0B;")
        self._led_label.setToolTip("Connected (No Data)")
        self._set_status("Connected (No Data)")

    def _on_metrics_updated(self, timeouts: int, crc: int, rx_bytes: int) -> None:
        self._rx_bytes = rx_bytes
        self._error_count = crc
        buffered = self._parser.buffered_bytes if self._parser else 0
        self._counts_label.setText(
            f"frames: {self._packet_count}   errors/crc: {self._error_count}   "
            f"timeouts: {timeouts}   "
            f"RX: {self._rx_bytes}B   TX: {self._tx_bytes}B   lat: {self._delta_t_ms:.1f}ms"
        )

    def _update_counts(self) -> None:
        if hasattr(self, "_counts_label"):
            self._counts_label.setText(
                f"frames: {self._packet_count}   errors/crc: {self._error_count}   "
                f"RX: {self._rx_bytes}B   TX: {self._tx_bytes}B   lat: {self._delta_t_ms:.1f}ms"
            )
        
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

        default_dir = Path(os.path.expanduser("~")) / "Documents" / "Decibels" / APP_NAME
        default_dir.mkdir(parents=True, exist_ok=True)
        default_file = default_dir / "serial_log.csv"

        target, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            str(default_file),
            "CSV files (*.csv);;All files (*)",
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
            decoded_path = base.with_name(f"{base_stem}_decoded.csv")
        elif log_raw:
            raw_path = base.with_name(f"{base_stem}.csv")
        else:
            decoded_path = base.with_name(f"{base_stem}.csv")

        self._raw_logger = RawLogger(raw_path) if raw_path else None
        self._decoded_logger = DecodedLogger(decoded_path) if decoded_path else None

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

    def _stop_logging(self) -> None:
        if self._raw_logger:
            self._raw_logger.close()
        if self._decoded_logger:
            self._decoded_logger.close()
        self._raw_logger = None
        self._decoded_logger = None
        self._logging = False
        self._logging_action.setText("Start Logging")
        self._style_action_btn(self._logging_action, _BTN_YELLOW)   # back to yellow
        self._logging_label.setText("Logging: stopped")
        self._set_status("Logging stopped")

    def _on_open_log_folder(self) -> None:
        default_dir = Path(os.path.expanduser("~")) / "Documents" / "Decibels" / APP_NAME
        if default_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(default_dir)))
        else:
            self._popup_information("Logs", f"Log directory does not exist yet:\n{default_dir}")

    def _on_clear(self) -> None:
        self._console.clear()
        self._packet_count = 0
        self._error_count = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._plot_history.clear()
        self._bitfield_table.setRowCount(0)
        self._enum_table.setRowCount(0)
        self._table_model.clear_live_columns()
        self._redraw_plot()
        self._update_counts()
        self._set_status("Cleared decoded values and console")

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

    # ------------------------------------------------------------------
    # Data feed
    # ------------------------------------------------------------------
    

    def _handle_packet(self, packet: ParsedPacket) -> None:
        self._packet_count += 1
        self._console.appendPlainText(self._format_console_row(packet))
        if self._raw_logger:
            self._raw_logger.log("RX", packet.raw, delta_t_ms=self._delta_t_ms)
        if not packet.ok:
            self._error_count += 1
            self._update_counts()
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
            self._decoded_logger.log_frame(self._packet_count, decoded)
        self._update_counts()

    # ------------------------------------------------------------------
    # Table, tabs, and plot maintenance
    # ------------------------------------------------------------------
    
    def _populate_polling_list(self) -> None:
        """Deprecated shim — delegates to the new status-sidebar updater."""
        self._update_poll_status_sidebar()

    def _on_toggle_polling(self) -> None:
        enabled = self._polling_action.isChecked()
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

    def _open_poll_config_dialog(self) -> None:
        """Sidebar Configure… button — opens dialog without toggling the action."""
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
            item.setForeground(QColor("#66BB6A") if is_on else QColor("#9CA3AF"))
            self._polling_list.addItem(item)
            if is_on:
                active += 1
        if hasattr(self, "_poll_status_label"):
            total = len(self._config.polling_schedules)
            self._poll_status_label.setText(f"{active} of {total} targets active")

    def _populate_editor_table(self) -> None:
        self._editor_table.setRowCount(0)
        if not self._config:
            return
        rw_signals = [s for s in self._config.all_signals if s.read_write in ("W", "RW")]
        # Integer data types — use QIntValidator
        _INT_TYPES = {"uint8", "int8", "uint16", "int16", "uint32", "int32"}
        for s in rw_signals:
            row = self._editor_table.rowCount()
            self._editor_table.insertRow(row)
            self._editor_table.setItem(row, 0, QTableWidgetItem(f"0x{s.frame_id:04X}"))
            self._editor_table.setItem(row, 1, QTableWidgetItem(s.signal_name))

            curr_val = QTableWidgetItem("-")
            self._editor_table.setItem(row, 2, curr_val)

            # Action layout: LineEdit (with validator) + Write Button
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            inp = QLineEdit()

            # --- Input Validation (Step 8) ---
            lo = s.min_value
            hi = s.max_value
            if s.data_type in _INT_TYPES:
                ilo = int(lo) if lo is not None else -2_147_483_648
                ihi = int(hi) if hi is not None else  2_147_483_647
                inp.setValidator(QIntValidator(ilo, ihi))
                inp.setPlaceholderText(f"{ilo}\u2026{ihi}")
            else:
                flo = lo if lo is not None else -1e18
                fhi = hi if hi is not None else  1e18
                # Fix: force "C" locale so the validator always uses a dot as
                # the decimal separator regardless of the OS regional format.
                _dv = QDoubleValidator(flo, fhi, 6)
                _dv.setLocale(QLocale(QLocale.Language.C))
                inp.setValidator(_dv)
                inp.setPlaceholderText(f"{flo:g}\u2026{fhi:g}")

            btn = QPushButton("Write")
            btn.clicked.connect(lambda _, inp=inp, s=s: self._on_editor_write(s, inp.text()))
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
            
        # Build write packet
        from ..protocol.packet_builder import build_packet, build_modbus_packet
        if self._config.protocol.parser_type == "modbus_rtu":
            # For FC06 write single register (simplified: convert val to 2 bytes)
            payload = int(val).to_bytes(2, "big", signed=True)
            pkt = build_modbus_packet(self._config.protocol, signal.frame_id, payload)
        else:
            self._popup_warning(
                "Write",
                "Parameter editing for framed protocol not yet fully implemented",
            )
            return
            
        self._serial.enqueue_priority_tx(pkt)
        self._log_activity(f"Priority Write: {signal.signal_name} = {val}")

    def _populate_table_from_config(self) -> None:
        assert self._config is not None
        self._row_index.clear()
        rows = []
        for frame_id, signals in self._config.signals_by_frame.items():
            for signal in signals:
                key = (frame_id, signal.signal_name)
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
            self._console.appendPlainText(f"[decode] {decoded.error}")
            self._error_count += 1
            return
        for warning in decoded.warnings:
            self._console.appendPlainText(f"[decode warning] {warning}")

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
            # Update editor table current-value column
            for erow in range(self._editor_table.rowCount()):
                if self._editor_table.item(erow, 1).text() == signal.signal_name:
                    self._editor_table.item(erow, 2).setText(signal.display_value or value_text)

            if signal.scaled_value is not None and signal.status == "ok":
                self._plot_history[key].append((elapsed, signal.scaled_value))
            if signal.status != "ok":
                self._error_count += 1
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
        if signal.bit_values:
            for bit_name, active in signal.bit_values.items():
                self._upsert_detail_row(
                    self._bitfield_table,
                    (f"0x{signal.frame_id:04X}", signal.signal_name, bit_name),
                    [f"0x{signal.frame_id:04X}", signal.signal_name, bit_name, "ON" if active else "OFF"],
                )
        if signal.enum_label:
            self._upsert_detail_row(
                self._enum_table,
                (f"0x{signal.frame_id:04X}", signal.signal_name),
                [
                    f"0x{signal.frame_id:04X}",
                    signal.signal_name,
                    "" if signal.raw_value is None else str(signal.raw_value),
                    signal.enum_label,
                ],
            )

    def _upsert_detail_row(self, table: QTableWidget, key: tuple[str, ...], values: list[str]) -> None:
        key_text = "\x1f".join(key)
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == key_text:
                for col, value in enumerate(values):
                    table.setItem(row, col, QTableWidgetItem(value))
                table.item(row, 0).setData(Qt.ItemDataRole.UserRole, key_text)
                return
        row = table.rowCount()
        table.insertRow(row)
        for col, value in enumerate(values):
            table.setItem(row, col, QTableWidgetItem(value))
        table.item(row, 0).setData(Qt.ItemDataRole.UserRole, key_text)

    def _populate_group_selector(self) -> None:
        assert self._config is not None
        current = self._group_combo.currentText()
        groups = sorted({signal.group for signal in self._config.all_signals if signal.group})
        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem("All")
        self._group_combo.addItems(groups)
        index = self._group_combo.findText(current)
        self._group_combo.setCurrentIndex(max(0, index))
        self._group_combo.blockSignals(False)

    def _apply_group_filter(self, group: str) -> None:
        search_text = ""
        if hasattr(self, "_search_input"):
            search_text = self._search_input.text().lower()

        n = self._table_model.row_count()
        for row in range(n):
            row_group = self._table_model.group_for_row(row)
            row_name = self._table_model.signal_name_for_row(row).lower()
            is_calculated = self._table_model.is_calculated_row(row)

            visible = group in ("", "All") or row_group == group
            if is_calculated and not self._show_calcs_check.isChecked():
                visible = False
            if search_text and search_text not in row_name:
                visible = False

            self._table.setRowHidden(row, not visible)

    def _clear_plot(self) -> None:
        self._plot_history.clear()
        for panel in self._plot_panels:
            for curve in panel.curves.values():
                panel.plot_item.removeItem(curve)
            panel.curves.clear()
        self._plot_rolling = True
        self._plot_mode_label.setText("🔄 Rolling")
        self._redraw_plot()

    def _on_plot_window_changed(self) -> None:
        """Re-enter Rolling mode and persist the chosen window duration."""
        self._settings.setValue("plot/window", self._plot_window_combo.currentText())
        self._plot_rolling = True
        self._plot_mode_label.setText("🔄 Rolling")
        self._redraw_plot()

    def _on_plot_range_changed(self, vb, x_range) -> None:
        """Called when any ViewBox X-range changes.  Guard suppresses our own calls."""
        if self._plot_range_changing:
            return
        if self._plot_rolling:
            self._plot_rolling = False
            self._plot_mode_label.setText("🔍 Explore  (Ctrl+R = Rolling)")

    def _export_plot_data(self) -> None:
        selected_keys = list(self._plot_keys)
        if not selected_keys:
            self._popup_information("Export plot", "No variables selected for plotting.")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Export plot data", "plot_data.csv", "CSV files (*.csv)"
        )
        if not target:
            return
        with Path(target).open("w", encoding="utf-8", newline="") as fp:
            for key in selected_keys:
                values = list(self._plot_history.get(key, []))
                if not values:
                    continue
                fp.write(f"--- {key[1]} (0x{key[0]:04X}) ---\n")
                fp.write("seconds,value\n")
                for seconds, value in values:
                    fp.write(f"{seconds:.3f},{value:.12g}\n")
                fp.write("\n")
        self._set_status(f"Exported plot data to {target}")

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
                # Single panel — just one action
                menu.addAction("Add to Live Plot").triggered.connect(
                    lambda: self._toggle_plot_key(key)
                )
            else:
                # Multiple panels — offer a sub-menu
                add_sub = menu.addMenu("Add to Live Plot")
                for idx in range(n_panels):
                    label = f"Panel {idx + 1}"
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
        key_to_color: Dict[Tuple[int, str], str] = {
            key: _PLOT_PALETTE[idx % len(_PLOT_PALETTE)]
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

        current_t = (datetime.now() - self._session_started).total_seconds()
        try:
            window = float(self._plot_window_combo.currentText())
        except ValueError:
            window = 60.0

        has_any_data = False
        color_offset = 0

        for panel in self._plot_panels:
            pi = panel.plot_item
            active_keys = set(panel.assigned_keys)

            # Remove curves for keys no longer assigned
            for key in list(panel.curves):
                if key not in active_keys:
                    pi.removeItem(panel.curves.pop(key))

            for local_idx, key in enumerate(panel.assigned_keys):
                values = list(self._plot_history.get(key, []))
                x_values, y_values = (zip(*values) if values else ([], []))

                color = _PLOT_PALETTE[(color_offset + local_idx) % len(_PLOT_PALETTE)]
                label = f"0x{key[0]:04X} {key[1]}"

                if key not in panel.curves:
                    panel.curves[key] = pi.plot(name=label, pen=pg.mkPen(color, width=2))
                else:
                    panel.curves[key].setPen(pg.mkPen(color, width=2))

                panel.curves[key].setData(
                    list(x_values), list(y_values),
                    autoDownsample=True,
                    clipToView=True,
                )
                if values:
                    has_any_data = True

            color_offset += len(panel.assigned_keys)

        # Rolling: clamp x_min to 0 so the origin is always visible.
        if self._plot_rolling and has_any_data and self._plot_panels:
            self._plot_range_changing = True
            try:
                x_min = max(0.0, current_t - window)
                first_pi = self._plot_panels[0].plot_item
                first_pi.setXRange(x_min, current_t, padding=0)
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
        # Stop the 60 Hz UI flush timer first.
        self._ui_timer.stop()
        # Signal the worker thread to exit and wait up to 2 s for the COM
        # port to be released cleanly (avoids zombie processes on Windows).
        if self._serial:
            self._serial.stop()
            self._serial.wait(2000)
            try:
                self._serial.close()
            except Exception:
                pass
        if self._logging:
            self._stop_logging()  # flushes final buffered log data
        self._save_window_state()
        super().closeEvent(event)


def _format_number(value) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
