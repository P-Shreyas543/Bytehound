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

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, QUrl, QObject, Signal, QLocale
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
    # useOpenGL offloads QPainter primitives to the GPU — meaningful CPU reduction
    # at high refresh rates with multiple panels.
    pg.setConfigOptions(antialias=True, useOpenGL=True)


try:
    import qdarktheme
except ImportError:  # pragma: no cover
    qdarktheme = None

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


from app.ui.widgets import (
    TitleBarThemeFilter,
    _BTN_GREEN,
    _BTN_PINK,
    _BTN_YELLOW,
    _CheckableGroupCombo,
    _StatusBadgeDelegate,
    _apply_windows_dark_titlebar,
    _contrast_text_color,
    _icon,
    _pad_dock_content,
)



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

from .telemetry_model import TelemetryTableModel, COLUMNS as _MODEL_COLUMNS
from .dialogs import ConnectionDialog, LoggingSettingsDialog, PollingConfigDialog
from ..decoder.config_loader import ConfigError, load_config
from ..decoder.frame_decoder import DecodedFrame, DecodedSignal, decode_frame
from ..decoder.template_io import export_excel_template, snapshot_config
from ..decoder.types import FrameConfig
from ..serial_logging.decoded_logger import DecodedLogger
from ..serial_logging.raw_logger import RawLogger
from ..protocol.packet_parser import create_parser, ParserProtocol, ParsedPacket
from ..serial_io.serial_worker import PollingWorker

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







# ---------------------------------------------------------------------------


from app.ui.plot_panel import (
    GRID_LAYOUTS,
    PlotPanel,
    TimeSeriesBuffer,
    _TimeAxisItem,
    _EMPTY_F64,
    _PLOT_INITIAL_WINDOW_S,
    _configure_live_curve,
    _format_elapsed_time,
)


# ---------------------------------------------------------------------------
# Configuration dialogs
# ---------------------------------------------------------------------------

from app.ui.config_loader import ConfigLoaderMixin
from app.ui.detail_tabs import DetailTabsMixin
from app.ui.logging_session import LoggingSessionMixin, _format_number
from app.ui.plot_orchestration import PlotOrchestrationMixin
from app.ui.polling_session import PollingSessionMixin
from app.ui.popups import PopupsMixin
from app.ui.theming import ThemingMixin, _PLOT_PALETTE_DARK, build_card_qss
from app.ui.tx_panel import TxPanelMixin
from app.ui.ui_builders import UIBuildersMixin
from app.ui.updater_wiring import UpdaterWiringMixin


class MainWindow(
    UIBuildersMixin,
    ThemingMixin,
    PlotOrchestrationMixin,
    ConfigLoaderMixin,
    LoggingSessionMixin,
    PollingSessionMixin,
    DetailTabsMixin,
    TxPanelMixin,
    UpdaterWiringMixin,
    PopupsMixin,
    QMainWindow,
):
    def _make_history_buffer(self) -> "TimeSeriesBuffer":
        """Factory for per-signal entries in ``self._plot_history``.

        Append-only chunked store. ``_plot_history_max_samples`` acts as a
        soft cap (``None`` = unbounded — keep every sample for the whole
        session). Existing buffers keep their cap until cleared; the cap
        is reapplied when the user changes the display window.
        """
        cap = getattr(self, "_plot_history_max_samples", None)
        return TimeSeriesBuffer(cap)


    def __init__(self) -> None:
        super().__init__()
        self._version = _read_version()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} v{self._version}")
        self.resize(1280, 780)
        # Explicit minimum so the user can snap the window to half-screen on
        # a 1080p display without Qt blocking the resize. The actual floor
        # is still set by child widgets' implicit minimums; this just
        # documents the supported lower bound and matches the targets we
        # tuned in _build_plot_tab (hover/hint width relaxation).
        self.setMinimumSize(640, 480)

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

        # Live-plot history. One TimeSeriesBuffer per signal — append-only
        # chunked storage that retains every sample since session start.
        # The display "Window" combo (Last 1 min / 5 min / … / All) controls
        # how much of the buffer is rendered, not what is stored. The soft
        # cap below is a marathon-run safety valve; ``None`` keeps everything.
        # 0 in QSettings is interpreted as "unbounded" so users who already
        # have the default persisted don't suddenly get a different cap.
        raw_cap = self._settings.value("plot/history_max_samples", 0)
        try:
            cap_int = int(raw_cap)
        except (TypeError, ValueError):
            cap_int = 0
        self._plot_history_max_samples: Optional[int] = cap_int if cap_int > 0 else None
        # Display window in seconds. 0 / None means "All session".
        raw_window = self._settings.value("plot/window_seconds", 300)  # default 5 min
        try:
            window_int = int(raw_window)
        except (TypeError, ValueError):
            window_int = 300
        self._plot_window_seconds: Optional[int] = window_int if window_int > 0 else None
        self._plot_history: Dict[Tuple[int, str], TimeSeriesBuffer] = (
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

        # 2 Hz Y-axis autofit. Y-autorange on every packet costs ~10s of profile
        # time at 100 Hz; throttling to 500 ms is visually indistinguishable for
        # telemetry and cuts the axis-paint cost roughly proportionally.
        self._y_autofit_timer = QTimer(self)
        self._y_autofit_timer.setInterval(500)
        self._y_autofit_timer.timeout.connect(self._throttled_y_autofit)
        self._y_autofit_timer.start()

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






    def _on_analysis_suite(self) -> None:
        self._log_activity("[ACTION] Open Analysis Suite")
        if not hasattr(self, "_analysis_window") or self._analysis_window is None:
            from .analysis_suite import AnalysisSuiteWindow
            self._analysis_window = AnalysisSuiteWindow(self)
        self._analysis_window.show()
        self._analysis_window.raise_()
        self._analysis_window.activateWindow()

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


    def _populate_view_menu(self) -> None:
        menu = self._view_menu
        menu.clear()
        from .theming import resolve_theme
        theme = str(self._settings.value("ui/theme", "dark"))
        ic = "#F8FAFC" if resolve_theme(theme) == "dark" else "#1F2937"

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




















    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        from .theming import resolve_theme
        theme = str(self._settings.value("ui/theme", "dark"))
        dark = (resolve_theme(theme) == "dark")
        QTimer.singleShot(0, lambda: _apply_windows_dark_titlebar(self, dark=dark))
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
        # The captured _default_state is whatever Qt happened to lay out at
        # construction time — usually fine but the Live Plot ends up wider
        # than ideal and the right column too narrow. Apply explicit
        # proportions so Reset always produces a tidy, useable layout.
        QTimer.singleShot(0, self._apply_tidy_dock_proportions)
        self._toast("Window layout reset")

    def _apply_tidy_dock_proportions(self) -> None:
        """Tune dock widths/heights to a sensible split.

        Right column ≈ 36% of width, bottom plot ≈ 38% of height. Right
        column's vertical split: panels 65% / logs 35%. Deferred via
        singleShot so the geometry restore has settled before we resize.
        """
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        # Width: pull the right column wider so the bottom plot dock has
        # less width to fill — addresses the "plot stretched on x" feel.
        right_docks = [
            self._bitfields_dock, self._enums_dock, self._tx_dock, self._editor_dock,
            self._console_dock, self._activity_dock,
        ]
        right_w = max(360, int(w * 0.36))
        self.resizeDocks(right_docks, [right_w] * len(right_docks), Qt.Orientation.Horizontal)
        # Height: bottom Live Plot gets ~38% of window height.
        self.resizeDocks([self._plot_dock], [int(h * 0.38)], Qt.Orientation.Vertical)
        # Right column vertical split: panels 65% / logs 35%.
        self.resizeDocks(
            [self._bitfields_dock, self._console_dock],
            [int(h * 0.65), int(h * 0.35)],
            Qt.Orientation.Vertical,
        )
        # Make sure the user's preferred tabs come back to the front.
        self._tx_dock.raise_()
        self._activity_dock.raise_()

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



    # ------------------------------------------------------------------
    # Grid management
    # ------------------------------------------------------------------






    def _on_layout_changed(self, label: str) -> None:
        rows, cols = GRID_LAYOUTS.get(label, (2, 1))
        self._clear_saved_y_ranges()
        self._rebuild_plot_grid(rows, cols, restore=False)
        self._redraw_plot()
        self._log_activity(f"[ACTION] Plot layout changed to {label} ({rows}x{cols})")


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
        hint.setObjectName("hintLabel")
        hint.setStyleSheet("font-size:11px;")
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





    def _mouseMoved(self, evt):
        """Crosshair handler — disabled in multi-panel mode (panels use their own)."""
        pass







    # ------------------------------------------------------------------
    # Config and toolbar handlers
    # ------------------------------------------------------------------







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

        dlg = ConnectionDialog(
            self._settings,
            parent=self,
            config_defaults=self._config.serial_defaults,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        settings = dlg.get_settings()
        if not settings.port:
            self._popup_warning("Connect", "No port selected. Please plug in a device and refresh.")
            return

        self._seen_decode_warnings.clear()
        try:
            self._serial = PollingWorker(
                settings,
                self._config.protocol,
                self._config.polling_schedules,
                decode_config=self._config,
            )
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
        # Worker pushes (ParsedPacket, DecodedFrame|None) tuples; legacy
        # bare-ParsedPacket items are normalised here so _handle_packet
        # doesn't have to branch.
        for item in packets:
            if isinstance(item, tuple):
                packet, pre_decoded = item
            else:
                packet, pre_decoded = item, None
            self._handle_packet(packet, pre_decoded=pre_decoded)
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


    def _log_flush_interval(self) -> float:
        value = self._settings.value("logging/flush_interval_s", 0.5)
        try:
            interval = float(value)
        except (TypeError, ValueError):
            interval = 0.5
        if interval < 0:
            interval = 0.0
        return interval


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
        self._bitfield_last_values.clear()
        self._enum_last_values.clear()
        self._table_model.clear_live_columns()
        self._seen_decode_warnings.clear()
        self._redraw_plot()
        self._update_counts()
        self._set_status("Cleared decoded values and console")
        self._log_activity("[ACTION] Cleared console and decoded values")

    # ------------------------------------------------------------------
    # Data feed
    # ------------------------------------------------------------------


    def _handle_packet(
        self,
        packet: ParsedPacket,
        pre_decoded: Optional[DecodedFrame] = None,
    ) -> None:
        self._packet_count += 1
        now = time.perf_counter()
        if self._last_packet_perf is not None:
            self._delta_t_ms = (now - self._last_packet_perf) * 1000.0
        self._last_packet_perf = now
        # Buffer the console line. _flush_ui appends them all in one shot.
        # Skip the whole console pipeline when the dock is hidden: the
        # datetime.strftime + hex.upper formatting is ~10 µs per packet
        # which dominates the per-packet UI cost at 1 kHz. Same UX
        # contract as the plot — re-opening shows fresh content from
        # re-open time forward.
        console_dock = getattr(self, "_console_dock", None)
        if console_dock is None or console_dock.isVisible():
            self._console_buffer.append(self._format_console_row(packet))
        if self._raw_logger:
            self._raw_logger.log("RX", packet.raw, delta_t_ms=self._delta_t_ms)
        if not packet.ok:
            # Worker is the single source of truth for the CRC error count
            # and pushes it via metrics_updated → _on_metrics_updated.
            return

        # Reset LED to green when data is flowing again after a timeout.
        if self._serial is not None:
            current_tooltip = self._led_label.toolTip()
            if current_tooltip == "Connected (No Data)":
                self._led_label.setStyleSheet("color: #66BB6A;")
                self._led_label.setToolTip("Connected")
                self._set_status("Connected")

        assert self._config is not None
        # The worker thread already decoded for us so the GUI thread doesn't
        # block on decode work. The rare worker-decode-error fallback path
        # goes through decode_frame here.
        decoded = pre_decoded if pre_decoded is not None else decode_frame(
            self._config, packet.frame_id, packet.payload
        )
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





    def _populate_editor_table(self) -> None:
        self._editor_table.setRowCount(0)
        # Index: signal_name -> list of value-cell QTableWidgetItem refs.
        # _apply_decoded looks rows up by name on every decoded signal of
        # every packet; a linear scan over rowCount() was O(rows * packets *
        # signals_per_packet) per UI flush. A dict turns that into O(1).
        self._editor_value_items: Dict[str, List[QTableWidgetItem]] = {}
        if not self._config:
            return
        # Filter out signals on rx-only frames — direction='rx' means we are
        # never supposed to TX to that frame, so the Parameter Editor must
        # not even surface those signals as writable. Unknown frames default
        # to rxtx (auto-created entries) so they stay visible.
        frames = self._config.frames
        rw_signals = [
            s for s in self._config.all_signals
            if s.read_write in ("W", "RW")
            and (frames.get(s.frame_id) is None or frames[s.frame_id].is_tx_capable)
        ]
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
        # Skip per-signal work whose target dock is hidden. Each visibility
        # check is a single Qt property read; doing them ONCE up here lets
        # the inner loop branch directly on cached bools.
        plot_dock = getattr(self, "_plot_dock", None)
        plot_visible = plot_dock is None or plot_dock.isVisible()
        bf_dock = getattr(self, "_bitfields_dock", None)
        en_dock = getattr(self, "_enums_dock", None)
        bf_visible = bf_dock is None or bf_dock.isVisible()
        en_visible = en_dock is None or en_dock.isVisible()
        # When both detail docks are hidden, _update_detail_tabs is pure
        # waste: it allocates QTableWidgetItems that no one will see.
        # Configs with many bitfields paid this every packet.
        detail_tabs_visible = bf_visible or en_visible
        elapsed = (
            (datetime.now() - self._session_started).total_seconds()
            if plot_visible
            else 0.0
        )
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
            if detail_tabs_visible:
                self._update_detail_tabs(signal, bf_visible=bf_visible, en_visible=en_visible)
            # O(1) editor-row lookup via the index built in
            # _populate_editor_table. setdefault on a missing config keeps
            # this branch a no-op when the editor table isn't initialised.
            for val_item in getattr(self, "_editor_value_items", {}).get(
                signal.signal_name, ()
            ):
                val_item.setText(signal.display_value or value_text)

            if plot_visible and signal.scaled_value is not None and signal.status == "ok":
                self._plot_history[key].append(elapsed, signal.scaled_value)
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











    # ------------------------------------------------------------------
    # Pause / Live toggle button
    # ------------------------------------------------------------------

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
                        if vb is not None and panel.y_scale_mode != "manual":
                            # Trigger an immediate one-shot fit; the 2 Hz
                            # timer handles steady-state.
                            self._fit_panel_y_now(panel)
                finally:
                    self._plot_range_changing = False
            self._log_activity("[ACTION] Plot resumed Live")
            self._redraw_plot()
        else:
            self._log_activity("[ACTION] Plot Paused")

    # ------------------------------------------------------------------
    # Hover crosshair + value readout
    # ------------------------------------------------------------------

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


    def _refresh_action_state(self) -> None:
        ready = self._config is not None
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
            from .theming import resolve_theme
            theme = str(self._settings.value("ui/theme", "dark"))
            if resolve_theme(theme) == "light":
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
        # Capture logger refs BEFORE _disconnect() nulls them in
        # _stop_logging(). After logger.close() returns, the writer thread
        # may still be draining a slow disk — we own the only handle that
        # lets us wait for it before the interpreter kills the daemon
        # thread mid-flush.
        loggers = [
            (name, lg) for name, lg in (
                ("raw log", self._raw_logger),
                ("decoded log", self._decoded_logger),
            ) if lg is not None
        ]
        # _disconnect() guarantees: stop timer → flush logs → stop worker → null.
        self._disconnect(reason="Application closed")
        # Block on any logger writer threads that didn't drain within their
        # bounded close() join — without this, Python's interpreter exit
        # kills daemon threads with rows still in the queue.
        drainers = [(name, lg) for name, lg in loggers if lg.is_draining()]
        if drainers:
            self._wait_for_logger_drain(drainers)
        self._save_window_state()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Logger drain helper — used by closeEvent to honour the data-loss
    # guarantee on slow disks (USB sticks, network shares) where the
    # writer-thread queue couldn't be flushed within the bounded
    # logger.close() join.
    # ------------------------------------------------------------------
    _DRAIN_CAP_SECONDS = 60.0
    _DRAIN_POLL_MS = 200

