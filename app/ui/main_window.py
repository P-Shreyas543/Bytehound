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


def _configure_live_curve(curve) -> None:
    """Apply per-curve perf flags so paint time stays sublinear in buffer length.

    Why: profiling at 100 Hz showed QPainter.drawPath dominating CPU (>25% of
    runtime) because every live-plot redraw painted every sample in the ring
    buffer, even when many samples collapsed onto the same pixel. Mirrors the
    flags the Analysis Suite already uses on its plots.
    """
    if pg is None:
        return
    try:
        curve.setClipToView(True)
        curve.setDownsampling(auto=True, method='peak')
        # Antialiasing dominates QPainter.drawPath cost at high refresh rates;
        # disable it per-curve on the live plot only (Analysis Suite keeps AA).
        curve.opts['antialias'] = False
    except Exception:  # pragma: no cover - older pyqtgraph fallbacks
        pass

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
    _CheckableGroupCombo,
    _StatusBadgeDelegate,
    _apply_windows_dark_titlebar,
    _icon,
    _pad_dock_content,
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
from ..serial_io.replay_source import parse_log_file, replay_bytes
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


from app.ui.plot_panel import (
    PlotPanel,
    _RingBuffer,
    _TimeAxisItem,
    _EMPTY_F64,
    _format_elapsed_time,
)


# ---------------------------------------------------------------------------
# Configuration dialogs
# ---------------------------------------------------------------------------

from app.ui.popups import PopupsMixin
from app.ui.theming import ThemingMixin, _PLOT_PALETTE_DARK, build_card_qss
from app.ui.tx_panel import TxPanelMixin
from app.ui.ui_builders import UIBuildersMixin
from app.ui.updater_wiring import UpdaterWiringMixin


class MainWindow(UIBuildersMixin, ThemingMixin, TxPanelMixin, UpdaterWiringMixin, PopupsMixin, QMainWindow):
    def _make_history_buffer(self) -> "_RingBuffer":
        """Factory for the ring-buffer entries in ``self._plot_history``.

        Fixed-capacity numpy-backed ring buffer keyed by signal. Capacity is
        read from ``self._plot_history_maxlen`` so it can be changed at
        runtime; existing buffers keep their original capacity until a new
        signal is first plotted.
        """
        n = getattr(self, "_plot_history_maxlen", 6_000)
        return _RingBuffer(n)


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

        # Live-plot history. One _RingBuffer per signal — pre-allocated
        # numpy storage that exposes ordered slices for setData with zero
        # per-tick fromiter loops. Was previously two bounded deques per
        # signal; the deque version paid a Python-level loop on every
        # redraw to convert to numpy.
        self._plot_history_maxlen: int = int(
            self._settings.value("plot/history_maxlen", 6_000))
        self._plot_history: Dict[Tuple[int, str], _RingBuffer] = (
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

        # 2 Hz Y-axis autofit. Y-autorange on every packet forces a full axis
        # tick regeneration + QPicture replay (10s of profile time at 100 Hz);
        # throttling to 500 ms is visually indistinguishable for telemetry and
        # cuts the axis-paint cost roughly proportionally.
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

    def _throttled_y_autofit(self) -> None:
        """Periodically refit Y for panels with auto_fit_y=True.

        Replaces pyqtgraph's continuous auto-range (which fires on every
        setData call → tick regeneration → QPicture replay) with a 2 Hz
        recompute. Skips when the computed range matches the current view
        so the axis only repaints when bounds actually changed.
        """
        if pg is None or not self._plot_panels:
            return
        if not self._plot_live:
            return  # paused — leave the user's view alone
        for panel in self._plot_panels:
            if not panel.auto_fit_y:
                continue
            self._fit_panel_y_now(panel)

    def _fit_panel_y_now(self, panel) -> None:
        if pg is None:
            return
        vb = panel.plot_item.getViewBox()
        if vb is None:
            return
        y_min: float | None = None
        y_max: float | None = None
        for key in panel.assigned_keys:
            buf = self._plot_history.get(key)
            if buf is None or len(buf) == 0:
                continue
            _, ys = buf.arrays()
            if ys.size == 0:
                continue
            local_min = float(np.nanmin(ys))
            local_max = float(np.nanmax(ys))
            if y_min is None or local_min < y_min:
                y_min = local_min
            if y_max is None or local_max > y_max:
                y_max = local_max
        if y_min is None or y_max is None:
            return
        if y_min == y_max:
            pad = max(abs(y_min) * 0.05, 1.0)
            y_min -= pad
            y_max += pad
        cur_range = vb.viewRange()[1]
        if cur_range and len(cur_range) == 2:
            span = max(y_max - y_min, 1e-9)
            if abs(cur_range[0] - y_min) / span < 0.01 and abs(cur_range[1] - y_max) / span < 0.01:
                return  # bounds unchanged — skip the repaint
        vb.setYRange(y_min, y_max, padding=0.05)

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
            vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
            self._fit_panel_y_now(panel)
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
            if not buf or len(buf) <= 1:
                continue
            last = buf.last_x()
            first = buf.first_x()
            if last is not None and first is not None:
                key_span = last - first
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
                buf.clear()
        if hasattr(self, "_hover_cache"):
            self._hover_cache.clear()
        self._redraw_plot()


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
            # Throttled auto-Y: we run our own 2 Hz fit (see _throttled_y_autofit)
            # so pyqtgraph's per-update auto-range stays off regardless of preference.
            vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
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
                curve = pi.plot(name=label, pen=pg.mkPen(color, width=1.8))
                _configure_live_curve(curve)
                panel.curves[key] = curve

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
        # Don't enable pyqtgraph's continuous auto-Y — the 2 Hz throttled
        # fitter handles it. Just trigger an immediate fit when turning on.
        vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        if checked:
            self._fit_panel_y_now(panel)
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
        # Items may be either bare ParsedPacket (replay / legacy) or
        # (ParsedPacket, DecodedFrame|None) tuples (live, post worker-side
        # decode). Normalise here so _handle_packet doesn't branch.
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
        # Falling back to direct append keeps replay (which calls
        # _handle_packet outside the batch path) behaving as before.
        # Skip the whole console pipeline when the dock is hidden: the
        # datetime.strftime + hex.upper formatting is ~10 µs per packet
        # which dominates the per-packet UI cost at 1 kHz. Same UX
        # contract as the plot — re-opening shows fresh content from
        # re-open time forward.
        console_dock = getattr(self, "_console_dock", None)
        if console_dock is None or console_dock.isVisible():
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
                self._set_status("Connected")

        assert self._config is not None
        # Live path: the worker thread already decoded for us so the GUI
        # thread doesn't block on decode work. Replay (no worker) and the
        # rare worker-decode-error fallback path go through decode_frame here.
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

    def _update_detail_tabs(
        self,
        signal: DecodedSignal,
        *,
        bf_visible: bool = True,
        en_visible: bool = True,
    ) -> None:
        """Refresh the Bitfields / Enums dock rows for *signal*.

        Each branch is gated on the caller-supplied visibility flag so a
        hidden dock pays no QTableWidgetItem allocations. The caller
        (``_apply_decoded``) reads the flags once per packet and forwards
        them; that keeps the visibility check off the inner loop's hot
        per-signal path even when the call IS made.
        """
        if bf_visible and signal.bit_values:
            group = self._signal_group_map.get((signal.frame_id, signal.signal_name), "")
            bf_selected = (
                self._bitfield_group_combo.selected_groups()
                if hasattr(self, "_bitfield_group_combo") else set()
            )
            bf_row_visible = self._row_visible_for_group(bf_selected, group)
            for bit_name, active in signal.bit_values.items():
                key = (f"0x{signal.frame_id:04X}", signal.signal_name, bit_name)
                self._upsert_detail_row(
                    self._bitfield_table,
                    self._bitfield_row_index,
                    key,
                    [f"0x{signal.frame_id:04X}", signal.signal_name, bit_name, "ON" if active else "OFF"],
                    last_values=self._bitfield_last_values,
                )
                row = self._bitfield_row_index.get("\x1f".join(key))
                if row is not None:
                    self._bitfield_table.setRowHidden(row, not bf_row_visible)
        if en_visible and signal.enum_label:
            group = self._signal_group_map.get((signal.frame_id, signal.signal_name), "")
            en_selected = (
                self._enum_group_combo.selected_groups()
                if hasattr(self, "_enum_group_combo") else set()
            )
            en_row_visible = self._row_visible_for_group(en_selected, group)
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
                last_values=self._enum_last_values,
            )
            row = self._enum_row_index.get("\x1f".join(key))
            if row is not None:
                self._enum_table.setRowHidden(row, not en_row_visible)

    def _upsert_detail_row(
        self,
        table: QTableWidget,
        row_index: Dict[str, int],
        key: tuple[str, ...],
        values: list[str],
        last_values: Optional[Dict[str, tuple[str, ...]]] = None,
    ) -> None:
        """Insert-or-update a row in *table*, looked up via *row_index* in O(1).

        *row_index* maps the joined-key string to the table row number. The
        caller is responsible for clearing it whenever ``table.setRowCount(0)``
        runs (see :meth:`_on_clear`).

        When *last_values* is supplied, the row's previous value tuple is
        cached there and unchanged updates short-circuit before touching Qt —
        critical at 100 Hz where most bitfield bits stay stable packet-to-packet.
        """
        key_text = "\x1f".join(key)
        values_tuple = tuple(values)
        if last_values is not None and last_values.get(key_text) == values_tuple:
            return
        row = row_index.get(key_text)
        if row is not None and row < table.rowCount():
            # Update existing items in place instead of allocating new
            # QTableWidgetItems every packet. Falls back to setItem only if
            # an item happens to be missing.
            for col, value in enumerate(values):
                item = table.item(row, col)
                if item is None:
                    table.setItem(row, col, QTableWidgetItem(value))
                elif item.text() != value:
                    item.setText(value)
            first = table.item(row, 0)
            if first is not None:
                first.setData(Qt.ItemDataRole.UserRole, key_text)
            if last_values is not None:
                last_values[key_text] = values_tuple
            return
        row = table.rowCount()
        table.insertRow(row)
        for col, value in enumerate(values):
            table.setItem(row, col, QTableWidgetItem(value))
        table.item(row, 0).setData(Qt.ItemDataRole.UserRole, key_text)
        row_index[key_text] = row
        if last_values is not None:
            last_values[key_text] = values_tuple

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
            try:
                if not hasattr(self, "_hover_cache"):
                    self._hover_cache = {}
                cached_arrays = self._hover_cache.get(key)
                if cached_arrays is None:
                    xs_view, ys_view = buf.arrays()
                    # Copy so a later ring-buffer wrap can't mutate storage
                    # behind the cached arrays — the pre-wrap arrays() path
                    # returns views into the underlying numpy storage. The
                    # cache is cleared every redraw flush, so copies don't
                    # accumulate.
                    cached_arrays = (xs_view.copy(), ys_view.copy())
                    self._hover_cache[key] = cached_arrays
                xs_arr, ys_arr = cached_arrays
                if len(xs_arr) == 0:
                    continue

                # np.searchsorted is C-level and works directly on the
                # ring-buffer slice. No bisect / list() conversion needed.
                idx = int(np.searchsorted(xs_arr, t))
                if idx >= len(xs_arr):
                    idx = len(xs_arr) - 1
                elif idx > 0 and (t - xs_arr[idx - 1]) < (xs_arr[idx] - t):
                    idx -= 1
                unit = self._signal_unit_map.get(key, "")
                suffix = f" {unit}" if unit else ""
                parts.append(f"{key[1]}={float(ys_arr[idx]):.2f}{suffix}")
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
        # Intentional no-op: plot-color feedback is provided by the plot
        # legend, and the table-cell dot indicator was never wired up
        # (TelemetryTableModel is read-only for DecorationRole). Kept as
        # a named hook so a future delegate can surface plotted-signal
        # color in the Variable column without churning the call site.
        return

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
                xs_len = len(buf) if buf is not None else 0
                # Compute oldest_x from the cheap ring-buffer accessor — no
                # need to build the numpy array just for the live X-range
                # anchor.
                if buf is not None and xs_len:
                    first_x = buf.first_x()
                    if first_x is not None and (oldest_x is None or first_x < oldest_x):
                        oldest_x = first_x

                color = palette[(color_offset + local_idx) % len(palette)]
                label = f"0x{key[0]:04X} {key[1]}"

                curve = panel.curves.get(key)
                if curve is None:
                    curve = pi.plot(name=label, pen=pg.mkPen(color, width=1.8))
                    _configure_live_curve(curve)
                    panel.curves[key] = curve
                    # Cache the colour on the curve itself so we can skip the
                    # setPen + mkPen allocation on every subsequent redraw —
                    # the colour only changes when the assignment shifts.
                    curve.__bh_color = color  # type: ignore[attr-defined]
                elif getattr(curve, "__bh_color", None) != color:
                    curve.setPen(pg.mkPen(color, width=1.8))
                    curve.__bh_color = color  # type: ignore[attr-defined]

                # Skip setData when this curve's ring buffer hasn't changed
                # since the last redraw. The buffer is bounded, so len alone
                # goes stale once it saturates — combine length with the
                # right-most timestamp, which increases monotonically with
                # every appended sample. At 60 Hz over many curves this
                # dominates the redraw cost when only a few signals are
                # actively producing data.
                last_x = buf.last_x() if (buf is not None and xs_len) else None
                signature = (xs_len, last_x)
                if getattr(curve, "__bh_last_sig", None) == signature:
                    continue
                curve.__bh_last_sig = signature  # type: ignore[attr-defined]

                if buf is None or xs_len == 0:
                    x_values, y_values = _EMPTY_F64, _EMPTY_F64
                else:
                    # Ring buffer returns ordered numpy slices/copies; no
                    # Python-level fromiter loop required.
                    x_values, y_values = buf.arrays()

                curve.setData(
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

    def _wait_for_logger_drain(self, drainers: list) -> None:
        """Show a progress dialog and poll each logger until its writer
        thread exits (data on disk), the cap elapses, or the user
        cancels. ``drainers`` is a list of (name, logger) tuples for
        loggers where ``is_draining()`` returned True.
        """
        total_rows = sum(lg.pending_rows() for _, lg in drainers)
        dlg = QProgressDialog(
            f"Finishing log — {total_rows} row(s) remaining…",
            "Skip (may lose data)",
            0,
            max(total_rows, 1),
            self,
        )
        dlg.setWindowTitle("Closing")
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)

        deadline = time.monotonic() + self._DRAIN_CAP_SECONDS
        poll_s = self._DRAIN_POLL_MS / 1000.0
        try:
            while time.monotonic() < deadline:
                if dlg.wasCanceled():
                    self._log_activity(
                        "[SESSION] User skipped log drain; some rows may be lost"
                    )
                    break
                # Re-check all drainers each iteration; remove finished ones.
                still_draining = []
                remaining = 0
                for name, lg in drainers:
                    if lg.await_drain(timeout=poll_s):
                        continue
                    still_draining.append((name, lg))
                    remaining += lg.pending_rows()
                if not still_draining:
                    break
                drainers = still_draining
                written = max(0, total_rows - remaining)
                dlg.setValue(written)
                dlg.setLabelText(
                    f"Finishing {', '.join(n for n, _ in drainers)} — "
                    f"{remaining} row(s) remaining…"
                )
                QApplication.processEvents()
            else:
                # Cap reached; log which loggers gave up.
                names = ", ".join(n for n, _ in drainers if n)
                self._log_activity(
                    f"[SESSION] Log drain cap ({self._DRAIN_CAP_SECONDS}s) "
                    f"reached for {names}; some rows may be lost"
                )
        finally:
            dlg.close()


def _format_number(value) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
