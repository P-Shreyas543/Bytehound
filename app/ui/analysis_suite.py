"""Analysis Suite — Multi-log comparison tool with overlay plots.

Launched from the Data menu as a non-modal QMainWindow.  All Excel loading
runs in a QThread so the live test is never blocked.  Plots use OpenGL
acceleration via pyqtgraph for lag-free pan/zoom even with many data points.

Module split (helpers extracted to keep this file focused on the main window):
    * ``analysis_theme``   – :data:`THEME` provider + colour palettes + dirs
    * ``log_io``           – :class:`LogEntry` + :class:`LogLoaderThread`
    * ``analysis_widgets`` – :class:`TimeAxisItem` / :class:`CursorReadoutPanel`
                              / :class:`StatisticsPanel`
    * ``xy_plot``          – :class:`XYPlotWindow`
"""
import csv
import json
import logging
import os
import re
import uuid
from typing import Optional

# Module-level logger. Routing to stderr / files is left to the host
# application's logging config — we only emit. The existing _log_activity
# calls into the main window's activity log remain in place; this is an
# additional channel so terminal users and crash reports see context.
_log = logging.getLogger("bytehound.analysis_suite")

import numpy as np
import pyqtgraph as pg

# ── Global pyqtgraph config (must run before any PlotWidget is created) ──
pg.setConfigOptions(antialias=True, useOpenGL=True)
from PySide6.QtCore import Qt, QSettings, QTimer, QThread, Signal
from PySide6.QtGui import (
    QAction, QColor, QFont, QKeySequence, QPainter,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox,
    QDoubleSpinBox, QFileDialog, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QInputDialog, QHeaderView,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QStatusBar, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

# Helper modules — see file docstring above for the full split rationale.
from .analysis_theme import (
    APP_NAME, APP_ORG, CURSOR_COLORS, LOG_COLORS, SELECTED_CURSOR_COLOR,
    THEME, get_analysis_dir, get_datalogs_dir,
)
from .analysis_widgets import CursorReadoutPanel, StatisticsPanel, TimeAxisItem, OverlayViewBox
from .log_io import (
    LogEntry, LogLoaderThread, _CSV_CACHE,
)
from .xy_plot import XYPlotWindow

# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════
DEFAULT_PARAMS = [
    "Vehicle Speed (Kmph)", "Dyno Act Torque (Nm)",
    "Vehicle Power (W)", "Roller Speed (RPM)",
]

SESSION_VERSION = 4
MIN_PLOT_HEIGHT = 80
MAX_PLOT_HEIGHT = 600
DEFAULT_PLOT_HEIGHT = 250


# ─────────────────────────────────────────────────────────────────────
# Multi-param subplot visual encoding
# ─────────────────────────────────────────────────────────────────────
# When several parameters share one subplot we need TWO independent visual
# channels — one for the parameter and one for the log. Lightness shifts of
# the same hue are not enough (a "lighter blue" vs "darker blue" still reads
# as blue in a small legend swatch), so we use distinct channels:
#
#     color       = parameter slot   (matplotlib tab10 — high-contrast hues)
#     line style  = log slot         (solid / dashed / dotted / dash-dot …)
#
# In a single-parameter subplot we revert to the original "color = log"
# convention so the curve color still matches the log swatch in the sidebar.
_PARAM_COLORS = [
    '#1f77b4',  # blue
    '#ff7f0e',  # orange
    '#2ca02c',  # green
    '#d62728',  # red
    '#9467bd',  # purple
    '#8c564b',  # brown
    '#e377c2',  # pink
    '#17becf',  # cyan
    '#bcbd22',  # olive
    '#7f7f7f',  # gray
]

# Line styles cycled per log within a multi-param subplot.
_LOG_LINE_STYLES = [Qt.SolidLine, Qt.DashLine, Qt.DotLine, Qt.DashDotLine, Qt.DashDotDotLine]


def _curve_visuals(group: list[str], param: str, log_index: int, log_color: str
                    ) -> tuple[str, Qt.PenStyle]:
    """Return (color, line_style) for a single (param, log) curve.

    Single-param subplot  → (log_color, solid).
    Multi-param subplot   → (param-slot color, log-slot line style).
    """
    if len(group) <= 1:
        return log_color, Qt.SolidLine
    try:
        slot = group.index(param)
    except ValueError:
        slot = 0
    color = _PARAM_COLORS[slot % len(_PARAM_COLORS)]
    style = _LOG_LINE_STYLES[log_index % len(_LOG_LINE_STYLES)]
    return color, style


# ═══════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════
# LogEntry, _is_time_like_param, _test_name_from_path, _CSV_CACHE, and
# LogLoaderThread now live in ``log_io``. CursorReadoutPanel,
# StatisticsPanel, TimeAxisItem now live in ``analysis_widgets``.
# XYPlotWindow lives in ``xy_plot``. Imports at the top of this file
# re-expose the names so existing code keeps working unchanged.



class CSVExportThread(QThread):
    """Background thread to align, interpolate, and write visible log curves to CSV."""
    sigProgress = Signal(int)
    sigFinished = Signal(str, int)
    sigError = Signal(str)

    def __init__(self, path: str, rows: list[dict], rate: int, parent=None):
        super().__init__(parent)
        self.path = path
        self.rows = rows
        self.rate = rate

    def run(self):
        try:
            # Slices and extracts x arrays
            masters = []
            for r in self.rows:
                x = r["x"]
                x_range = r.get("x_range")
                if x_range is not None:
                    mask = (x >= x_range[0]) & (x <= x_range[1])
                    masters.append(x[mask])
                else:
                    masters.append(x)
            
            if not masters:
                self.sigError.emit("No samples found to export.")
                return

            merged = np.unique(np.concatenate(masters))
            if merged.size == 0:
                self.sigError.emit("No samples in the selected view range.")
                return

            if self.rate > 1:
                merged = merged[::self.rate]

            headers = ["time"]
            data_cols = []
            for r in self.rows:
                if self.isInterruptionRequested():
                    return
                x = r["x"]
                y = r["y"]
                order = np.argsort(x)
                x_sorted = x[order]
                y_sorted = y[order]
                interp = np.interp(merged, x_sorted, y_sorted, left=np.nan, right=np.nan)
                headers.append(r["curve"])
                data_cols.append(interp)

            total_rows = merged.size
            if self.isInterruptionRequested():
                return

            with open(self.path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(headers)
                
                # Write in chunks of 500 rows to support cancellation & progress dialogs
                chunk_size = 500
                for start_idx in range(0, total_rows, chunk_size):
                    if self.isInterruptionRequested():
                        f.close()
                        try:
                            os.remove(self.path)
                        except Exception:
                            pass
                        return
                    
                    end_idx = min(start_idx + chunk_size, total_rows)
                    for i in range(start_idx, end_idx):
                        row = [f"{merged[i]:.6f}"]
                        for col in data_cols:
                            v = col[i]
                            row.append("" if not np.isfinite(v) else f"{v:.6g}")
                        w.writerow(row)
                    
                    progress_pct = int((end_idx / total_rows) * 100)
                    self.sigProgress.emit(progress_pct)
                    
            self.sigFinished.emit(self.path, total_rows)
        except Exception as e:
            self.sigError.emit(str(e))


class SessionSaveThread(QThread):
    """Background thread to write session state JSON file."""
    sigFinished = Signal(str)
    sigError = Signal(str)

    def __init__(self, path: str, data: dict, parent=None):
        super().__init__(parent)
        self.path = path
        self.data = data

    def run(self):
        try:
            with open(self.path, 'w') as f:
                json.dump(self.data, f, indent=2)
            self.sigFinished.emit(self.path)
        except Exception as e:
            self.sigError.emit(str(e))


class SessionLoadThread(QThread):
    """Background thread to read and parse session state JSON file."""
    sigFinished = Signal(dict)
    sigError = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            with open(self.path, 'r') as f:
                data = json.load(f)
            self.sigFinished.emit(data)
        except Exception as e:
            self.sigError.emit(str(e))


class PlotImageExportThread(QThread):
    """Background thread to stitch, format, and compile composite images and PDFs."""
    sigFinished = Signal(str)
    sigError = Signal(str)

    def __init__(self, path: str, mode: str, images: list, plot_bg: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.mode = mode
        self.images = images  # List of QImage objects
        self.plot_bg = plot_bg

    def run(self):
        try:
            from PySide6.QtGui import QImage, QColor, QPainter, QPixmap
            from PySide6.QtCore import QMarginsF, Qt
            
            if self.mode == "PDF":
                from PySide6.QtPrintSupport import QPrinter
                from PySide6.QtGui import QPageSize, QPageLayout
                
                # Stitch vertically onto one canvas with white bg
                export_width = 1600
                total_h = sum(img.height() for img in self.images) + 8 * max(len(self.images) - 1, 0)
                canvas = QImage(export_width, total_h, QImage.Format_ARGB32)
                canvas.fill(QColor('#ffffff'))
                
                painter_c = QPainter(canvas)
                y = 0
                for img in self.images:
                    painter_c.drawImage(0, y, img)
                    y += img.height() + 8
                painter_c.end()

                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(self.path)
                printer.setPageSize(QPageSize(QPageSize.A4))
                printer.setPageOrientation(QPageLayout.Landscape)
                printer.setPageMargins(QMarginsF(10, 10, 10, 10))

                painter = QPainter()
                painter.begin(printer)
                page_rect = printer.pageRect(QPrinter.DevicePixel)
                pixmap = QPixmap.fromImage(canvas)
                # Scale to fit page preserving aspect ratio
                scaled = pixmap.scaled(
                    page_rect.width(), page_rect.height(),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x_off = int((page_rect.width() - scaled.width()) / 2)
                y_off = int((page_rect.height() - scaled.height()) / 2)
                painter.drawPixmap(x_off, y_off, scaled)
                painter.end()
            else:
                # PNG composite
                total_height = 0
                width = 0
                for img in self.images:
                    total_height += img.height() + 10
                    width = max(width, img.width())

                composite = QImage(width, total_height, QImage.Format_ARGB32)
                composite.fill(QColor(self.plot_bg))
                painter = QPainter(composite)
                y_offset = 0
                for img in self.images:
                    painter.drawImage(0, y_offset, img)
                    y_offset += img.height() + 10
                painter.end()
                composite.save(self.path)
                
            self.sigFinished.emit(self.path)
        except Exception as e:
            self.sigError.emit(str(e))


# ═══════════════════════════════════════════════════════════════════════
# Main analysis window
# ═══════════════════════════════════════════════════════════════════════
class AnalysisSuiteWindow(QMainWindow):
    """Multi-log comparison analysis tool."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window)
        self.setWindowTitle(f"Analysis Suite — {APP_NAME}")
        self.resize(1500, 900)
        self.setMinimumSize(600, 400)

        self._logs: dict[str, LogEntry] = {}
        self._color_index = 0
        self._loader_threads: list[LogLoaderThread] = []

        # Plot management.
        # _plot_groups[i] holds the list of parameter names rendered on
        # _plot_widgets[i]. A single-param subplot has a list of length 1.
        self._plot_widgets: list[pg.PlotWidget] = []
        self._plot_groups: list[list[str]] = []
        # Last position the mouse hovered over a subplot, set by _on_mouse_moved.
        # Initialised to None up-front so the cursor-add right-click actions
        # (_add_horizontal_cursor_at_mouse, _anchor_pw_and_t, etc.) can safely
        # read them before the user has ever hovered a plot. Without these,
        # opening the context menu before any mouse-move raised
        # AttributeError on the lookup.
        self._last_mouse_pw: Optional[pg.PlotWidget] = None
        self._last_mouse_pos = None
        # Persists the user-defined subplot layout (list of param lists) even
        # when params are unchecked or new logs are loaded.
        self._subplot_layout: list[list[str]] = []
        # Per-subplot toggles keyed by ``frozenset(params)`` so they survive
        # subplot reorder, splitting, and merging.
        self._normalized_subplots: set[frozenset[str]] = set()
        # Per-subplot smoothing — value is a moving-average window size; missing
        # entries mean "raw, no smoothing".
        self._smoothed_subplots: set[frozenset[str]] = set()
        self._smoothing_window: int = 5
        # Auto-fit Y when the x-range changes (toolbar toggle).
        self._auto_fit_y: bool = False
        # Recent files (Phase 2) — populated lazily from QSettings.
        self._recent_files: list[str] = []
        # Settings (window geometry, recent files, theme prefs, etc.)
        self._qsettings = QSettings(APP_ORG, APP_NAME)
        # Legacy compat: _plot_height was used by an older slider-based UI.
        # Session files may still contain it; default to DEFAULT_PLOT_HEIGHT.
        self._plot_height = int(
            self._qsettings.value("analysis/plot_height", DEFAULT_PLOT_HEIGHT)
        )
        # Guard: True while we're programmatically populating the tree so the
        # model's rowsInserted signal (used to detect drag-drop) doesn't
        # mistake our own inserts for user drops.
        self._populating_tree: bool = False
        self._curves: dict[str, dict[str, pg.PlotDataItem]] = {}
        self._v_cursors: list[dict] = []
        self._h_cursors: list[dict] = []
        self._crosshair_lines: dict[pg.PlotWidget, tuple] = {}
        self._selected_v_cursor: str = ''   # cursor ID string, '' = none
        self._selected_h_cursor: str = ''   # cursor ID string, '' = none
        self._cursor_dots: dict[str, list] = {}   # cursor_id → [{'pw', 'item'}]
        self._v_cursor_counter: int = 0          # ever-increasing label counter
        self._xy_window = None                   # keep reference to non-modal XY window
        self._wall_clock_mode: bool = False       # X-axis: elapsed vs wall-clock
        self._persisted_x_range = self._qsettings.value("analysis/x_range")
        self._persisted_cursors = self._qsettings.value(
            "analysis/cursor_positions", [])

        persisted_math = self._qsettings.value("analysis/math_channels")
        if isinstance(persisted_math, dict):
            self._math_channels = {str(k): str(v) for k, v in persisted_math.items()}
        else:
            self._math_channels = {}

        # Log sidebar UI elements
        self._log_entries_ui: dict[str, dict] = {}  # log_id → {checkbox, spin, container, ...}

        self._build_ui()
        self._build_menus()
        # Apply the shared app QSS (cards, docks, tables, tabs) so this window
        # visually matches the MainWindow. qdarktheme's palette is already
        # applied app-wide, but the custom QSS is per-top-level-window.
        self.apply_theme(str(QSettings(APP_ORG, APP_NAME).value("ui/theme", "dark")))
        THEME.theme_changed.connect(self._apply_theme)

    def _log_activity(self, text: str) -> None:
        """Forward Activity Log events to the main app window if available."""
        parent = self.parent()
        # Walk up the Qt parent chain looking for MainWindow._log_activity.
        while parent is not None:
            if hasattr(parent, "_log_activity"):
                try:
                    parent._log_activity(text)  # type: ignore[attr-defined]
                except Exception:
                    pass
                return
            parent = parent.parent() if hasattr(parent, "parent") else None

    def _log_popup(self, kind: str, title: str, message: str) -> None:
        message_text = "" if message is None else str(message)
        lines = message_text.splitlines()
        tag = f"Analysis Suite/{kind}"
        if not lines:
            self._log_activity(f"[{tag}] {title}")
            return
        if len(lines) == 1:
            self._log_activity(f"[{tag}] {title}: {lines[0]}")
            return
        self._log_activity(f"[{tag}] {title}:")
        for line in lines:
            self._log_activity(f"    {line}")

    def _popup_information(self, title: str, message: str) -> None:
        self._log_popup("INFO", title, message)
        _log.info("[%s] %s", title, message.replace("\n", " · "))
        QMessageBox.information(self, title, message)

    def _popup_warning(self, title: str, message: str) -> None:
        self._log_popup("WARN", title, message)
        _log.warning("[%s] %s", title, message.replace("\n", " · "))
        QMessageBox.warning(self, title, message)

    # ──────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Vertical split: top row holds the param-tree sidebar + plot area
        # (a horizontal child splitter); bottom row holds the analyst tabs
        # (Cursors + Statistics). Previously the tabs sat in a third column
        # on the right, which left them too narrow on smaller monitors and
        # forced the plot area to fight for horizontal room.
        outer = QSplitter(Qt.Vertical)
        outer.setContentsMargins(4, 4, 4, 4)
        self.setCentralWidget(outer)

        self._splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(self._splitter)
        self._outer_splitter = outer

        # ── Left sidebar ─────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setMinimumWidth(200)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(4, 4, 4, 4)
        side_layout.setSpacing(4)

        # Loaded logs group (with inline time offsets)
        log_group = QGroupBox("Loaded Logs")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 12, 4, 4)
        log_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        btn_row = QHBoxLayout()
        self._btn_load = QPushButton("Load Logs")
        self._btn_load.clicked.connect(self._on_load_logs)
        btn_row.addWidget(self._btn_load)
        self._btn_remove = QPushButton("Remove")
        self._btn_remove.clicked.connect(self._on_remove_selected)
        btn_row.addWidget(self._btn_remove)
        btn_row.addStretch(1)
        log_layout.addLayout(btn_row)

        # Log list — each row: checkbox + color swatch + name + offset spin
        self._log_list_widget = QWidget()
        self._log_list_layout = QVBoxLayout(self._log_list_widget)
        self._log_list_layout.setContentsMargins(0, 0, 0, 0)
        self._log_list_layout.setSpacing(2)
        self._log_list_layout.addStretch()

        log_scroll = QScrollArea()
        log_scroll.setWidgetResizable(True)
        log_scroll.setFrameShape(QFrame.NoFrame)
        log_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_scroll.setWidget(self._log_list_widget)
        log_layout.addWidget(log_scroll, 1)
        side_layout.addWidget(log_group, 1)

        # Plot layout combo
        from .plot_panel import GRID_LAYOUTS
        layout_row = QHBoxLayout()
        layout_row.addWidget(QLabel("Layout:"))
        self._layout_combo = QComboBox()
        self._layout_combo.addItems(list(GRID_LAYOUTS.keys()))
        saved_layout = str(self._qsettings.value("analysis/layout", "2×1")).lower().replace("x", "×")
        self._layout_combo.setCurrentText(saved_layout if saved_layout in GRID_LAYOUTS else "2×1")
        self._layout_combo.currentTextChanged.connect(self._on_layout_changed)
        layout_row.addWidget(self._layout_combo)
        layout_row.addStretch(1)
        side_layout.addLayout(layout_row)

        # Parameter selector group — pushed to bottom
        param_group = QGroupBox("Parameters (Subplots)")
        param_layout = QVBoxLayout(param_group)
        param_layout.setContentsMargins(4, 12, 4, 4)

        # Search row: filter box + live hit count.
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self._param_search = QLineEdit()
        self._param_search.setPlaceholderText("Search parameters…")
        self._param_search.setClearButtonEnabled(True)
        self._param_search.textChanged.connect(self._on_param_search_changed)
        search_row.addWidget(self._param_search, 1)
        self._param_hit_count = QLabel("")
        self._param_hit_count.setStyleSheet("color: palette(mid); padding: 0 4px;")
        self._param_hit_count.setMinimumWidth(48)
        search_row.addWidget(self._param_hit_count)
        param_layout.addLayout(search_row)

        # Subplot settings toolbar
        subplot_settings_layout = QHBoxLayout()
        subplot_settings_layout.setSpacing(4)

        self._subplot_settings_combo = QComboBox()
        self._subplot_settings_combo.setFont(QFont("PT Sans", 8))
        self._subplot_settings_combo.setToolTip("Select subplot to configure settings below")
        self._subplot_settings_combo.currentTextChanged.connect(self._on_subplot_settings_combo_changed)
        subplot_settings_layout.addWidget(QLabel("Subplot:"))
        subplot_settings_layout.addWidget(self._subplot_settings_combo, 1)

        self._subplot_normalize_cb = QCheckBox("Norm")
        self._subplot_normalize_cb.setFont(QFont("PT Sans", 8))
        self._subplot_normalize_cb.setToolTip("Normalize curves on the selected subplot to 0-1")
        self._subplot_normalize_cb.stateChanged.connect(self._on_subplot_normalize_toggled)
        subplot_settings_layout.addWidget(self._subplot_normalize_cb)

        self._subplot_smooth_cb = QCheckBox("Smooth")
        self._subplot_smooth_cb.setFont(QFont("PT Sans", 8))
        self._subplot_smooth_cb.setToolTip("Enable rolling average smoothing on the selected subplot")
        self._subplot_smooth_cb.stateChanged.connect(self._on_subplot_smooth_toggled)
        subplot_settings_layout.addWidget(self._subplot_smooth_cb)

        self._subplot_up_btn = QPushButton("▲")
        self._subplot_up_btn.setStyleSheet("padding: 0px;")
        self._subplot_up_btn.setToolTip("Move selected subplot up")
        self._subplot_up_btn.setFixedWidth(24)
        self._subplot_up_btn.clicked.connect(self._on_subplot_move_up)
        subplot_settings_layout.addWidget(self._subplot_up_btn)

        self._subplot_down_btn = QPushButton("▼")
        self._subplot_down_btn.setStyleSheet("padding: 0px;")
        self._subplot_down_btn.setToolTip("Move selected subplot down")
        self._subplot_down_btn.setFixedWidth(24)
        self._subplot_down_btn.clicked.connect(self._on_subplot_move_down)
        subplot_settings_layout.addWidget(self._subplot_down_btn)

        self._subplot_delete_btn = QPushButton("✕")
        self._subplot_delete_btn.setStyleSheet("padding: 0px;")
        self._subplot_delete_btn.setToolTip("Clear / delete selected subplot")
        self._subplot_delete_btn.setFixedWidth(24)
        self._subplot_delete_btn.clicked.connect(self._on_subplot_delete)
        subplot_settings_layout.addWidget(self._subplot_delete_btn)

        param_layout.addLayout(subplot_settings_layout)

        # Global actions
        sec_btn_row = QHBoxLayout()
        sec_btn_row.setSpacing(4)
        btn_all = QPushButton("Check All")
        btn_all.clicked.connect(lambda: self._set_all_params(True))
        sec_btn_row.addWidget(btn_all)
        btn_none = QPushButton("Clear")
        btn_none.setToolTip("Uncheck all parameters")
        btn_none.clicked.connect(lambda: self._set_all_params(False))
        sec_btn_row.addWidget(btn_none)
        sec_btn_row.addStretch(1)
        param_layout.addLayout(sec_btn_row)

        # Flat tree layout
        self._param_tree = QTreeWidget()
        self._param_tree.setFont(QFont("PT Sans", 9))
        self._param_tree.setColumnCount(2)
        self._param_tree.setHeaderLabels(["Parameter", "Subplot"])
        self._param_tree.setHeaderHidden(False)
        self._param_tree.setRootIsDecorated(False)
        self._param_tree.setDragEnabled(False)
        self._param_tree.setAcceptDrops(False)
        self._param_tree.setDropIndicatorShown(False)
        self._param_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._param_tree.setContextMenuPolicy(Qt.NoContextMenu)
        self._param_tree.itemChanged.connect(self._on_param_changed)

        # Configure columns stretch
        self._param_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._param_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        param_layout.addWidget(self._param_tree)

        tip = QLabel(
            "Tip: Select subplot in dropdown to display curve, or Off to hide. Use checkbox for quick toggle."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: palette(mid); font-size: 9pt; padding: 2px 0;")
        param_layout.addWidget(tip)

        side_layout.addWidget(param_group, 2)

        self._splitter.addWidget(sidebar)

        # ── Middle: plot area ────────────────────────────────────────
        from PySide6.QtWidgets import QGridLayout
        self._plot_scroll = QScrollArea()
        self._plot_scroll.setWidgetResizable(True)
        self._plot_scroll.setFrameShape(QFrame.NoFrame)
        self._plot_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._plot_container = QWidget()
        self._plot_layout = QGridLayout(self._plot_container)
        # Generous outer padding + spacing so axis tick labels at the edges
        # don't collide with the sidebar/scrollbar or the next subplot below.
        self._plot_layout.setContentsMargins(8, 8, 8, 8)
        self._plot_layout.setSpacing(10)

        self._plot_scroll.setWidget(self._plot_container)
        self._splitter.addWidget(self._plot_scroll)

        # ── Bottom: tabbed analyst panels (cursor readout + statistics) ──
        # Moved out of the right column into the vertical outer splitter so
        # they get full window width — readouts now show all values for two
        # cursors side-by-side without horizontal scrolling.
        bottom_tabs = QTabWidget()
        bottom_tabs.setMinimumHeight(140)
        self._cursor_readout = CursorReadoutPanel()
        bottom_tabs.addTab(self._cursor_readout, "Cursors")
        self._stats_panel = StatisticsPanel()
        bottom_tabs.addTab(self._stats_panel, "Statistics")
        self._right_tabs = bottom_tabs  # name retained for callers
        self._outer_splitter.addWidget(bottom_tabs)

        # Horizontal split: sidebar | plots. No third right column anymore.
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        # Vertical split: plot row takes the lion's share, bottom tabs are
        # collapsible but default to ~25% of the window height.
        self._outer_splitter.setStretchFactor(0, 4)
        self._outer_splitter.setStretchFactor(1, 1)

        # Debounced stats refresh — sigRangeChanged fires continuously while
        # the user pans/zooms; 150ms is short enough to feel live but stops
        # us from recomputing on every mouse-move tick.
        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(150)
        self._stats_timer.timeout.connect(self._refresh_stats_panel)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — load test logs to begin analysis.")

    def _build_menus(self):
        mb = self.menuBar()

        # ── File ─────────────────────────────────────────────────────
        file_menu = mb.addMenu("File")
        file_menu.addAction("Load Logs...", self._on_load_logs,
                            QKeySequence("Ctrl+L"))
        # Recent-files submenu — refreshed on aboutToShow so it always
        # reflects the latest list (writes happen in _on_log_loaded).
        self._recent_menu = file_menu.addMenu("Recent Logs")
        self._recent_menu.aboutToShow.connect(self._rebuild_recent_menu)
        file_menu.addSeparator()
        file_menu.addAction("Save Session", self._save_session,
                            QKeySequence.Save)
        file_menu.addAction("Load Session...", self._load_session,
                            QKeySequence.Open)
        file_menu.addSeparator()
        file_menu.addAction("Export Visible Data as CSV...",
                            self._export_visible_csv, QKeySequence("Ctrl+E"))
        file_menu.addAction("Export Plots as Image...", self._export_image)
        file_menu.addAction("Export Plots as PDF...", self._export_pdf)
        file_menu.addSeparator()
        file_menu.addAction("Open Data Logs Folder", self._open_datalogs_folder)
        file_menu.addAction("Open Analysis Folder", self._open_analysis_folder)
        file_menu.addSeparator()
        file_menu.addAction("Close", self.close, QKeySequence("Ctrl+W"))

        # ── View ─────────────────────────────────────────────────────
        view_menu = mb.addMenu("View")
        self._auto_fit_action = QAction("Auto-Fit Y to Visible Range", self)
        self._auto_fit_action.setCheckable(True)
        self._auto_fit_action.setShortcut(QKeySequence("F"))
        self._auto_fit_action.setToolTip(
            "When on, panning/zooming the X axis automatically rescales the "
            "Y axis to fit the visible data on every subplot."
        )
        self._auto_fit_action.toggled.connect(self._on_auto_fit_y_toggled)
        view_menu.addAction(self._auto_fit_action)
        view_menu.addAction("Reset Zoom", self._reset_zoom, QKeySequence("Ctrl+0"))
        view_menu.addSeparator()
        view_menu.addAction("Show Statistics Panel",
                            lambda: self._right_tabs.setCurrentIndex(1))
        view_menu.addAction("Show Cursors Panel",
                            lambda: self._right_tabs.setCurrentIndex(0))
        view_menu.addSeparator()
        view_menu.addAction("Smoothing Window…",
                            self._prompt_smoothing_window)
        view_menu.addSeparator()
        self._wallclock_action = QAction("Wall Clock Time (X-Axis)", self)
        self._wallclock_action.setCheckable(True)
        self._wallclock_action.setToolTip(
            "Display X-axis as wall-clock time (HH:MM:SS) using the log's "
            "start timestamp.  Uncheck to revert to elapsed mm:ss."
        )
        self._wallclock_action.toggled.connect(self._on_wallclock_toggled)
        view_menu.addAction(self._wallclock_action)

        # ── Layout ───────────────────────────────────────────────────
        # The grouping operations are first-class: keyboard shortcuts make
        # them practical for daily use. The buttons in the sidebar do the
        # exact same thing — these just put hands on keys.




        # ── Tools ────────────────────────────────────────────────────
        # V adds a cursor that lives ONLY on the subplot under the mouse —
        # users were confused when a cursor placed on one subplot appeared
        # on every other subplot too. Shift+V keeps the old "all subplots"
        # behaviour for cross-subplot timing comparisons.
        tools_menu = mb.addMenu("Tools")
        tools_menu.addAction("Add Vertical Cursor (this subplot)",
                     self._add_plot_vertical_cursor, QKeySequence("V"))
        tools_menu.addAction("Add Vertical Cursor (all subplots)",
                             self._add_vertical_cursor, QKeySequence("Shift+V"))
        tools_menu.addAction("Add Horizontal Cursor at Mouse",
                             self._add_horizontal_cursor_at_mouse, QKeySequence("H"))
        tools_menu.addSeparator()
        tools_menu.addAction("Clear All Cursors", self._clear_all_cursors)
        tools_menu.addSeparator()
        tools_menu.addAction("Custom Math Channel...", self._add_custom_math_channel, QKeySequence("M"))
        tools_menu.addAction("Remove Custom Math Channel...", self._remove_custom_math_channel)
        tools_menu.addSeparator()
        tools_menu.addAction("Import Schema Mapper...", self._configure_import_schema)

        # ── Scatter ──────────────────────────────────────────────────
        scatter_menu = mb.addMenu("Scatter")
        scatter_menu.addAction("X-Y Plotter...", self._open_xy_plotter)

    # ──────────────────────────────────────────────────────────────────
    # Key events (Delete to remove selected cursor)
    # ──────────────────────────────────────────────────────────────────
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            if self._selected_v_cursor:
                self._delete_v_cursor(self._selected_v_cursor)
                return
            if self._selected_h_cursor:
                self._delete_h_cursor(self._selected_h_cursor)
                return
        super().keyPressEvent(event)

    # ──────────────────────────────────────────────────────────────────
    # Theme
    # ──────────────────────────────────────────────────────────────────
    def apply_theme(self, theme: str) -> None:
        """Public entry point — called by MainWindow when the app theme changes.

        Installs the shared card/dock/table/tab QSS on this window and repaints
        the pyqtgraph plots to match the new theme.
        """
        try:
            from .theming import build_card_qss
            self.setStyleSheet(build_card_qss(theme))
        except Exception:
            pass
        self._apply_theme(theme)
        if self._xy_window is not None:
            try:
                self._xy_window.apply_theme(theme)
            except Exception:
                pass

    def _apply_theme(self, _mode: str = ""):
        bg = THEME.c('plot_bg')
        fg = THEME.c('plot_fg')
        alpha = THEME.plot_grid_alpha()
        border_color = THEME.c('border')

        if hasattr(self, '_plot_scroll') and self._plot_scroll is not None:
            self._plot_scroll.setStyleSheet(f"QScrollArea {{ background-color: {bg}; border: none; }}")
            if self._plot_scroll.viewport() is not None:
                self._plot_scroll.viewport().setStyleSheet(f"background-color: {bg};")
        if hasattr(self, '_plot_container') and self._plot_container is not None:
            self._plot_container.setStyleSheet(f"background-color: {bg};")

        for pw in self._plot_widgets:
            pw.setBackground(bg)
            pw.setStyleSheet(f"border: 1px solid {border_color}; border-radius: 4px;")
            for axis_name in ('left', 'bottom'):
                ax = pw.getAxis(axis_name)
                pen = pg.mkPen(fg)
                ax.setPen(pen)
                ax.setTextPen(pen)
                if hasattr(ax, 'labelStyle'):
                    style = dict(ax.labelStyle)
                    style['color'] = fg
                    pw.setLabel(axis_name, **style)
            
            if hasattr(pw, 'right_axis') and pw.right_axis is not None:
                pen = pg.mkPen(fg)
                pw.right_axis.setPen(pen)
                pw.right_axis.setTextPen(pen)
                if hasattr(pw.right_axis, 'labelStyle'):
                    style = dict(pw.right_axis.labelStyle)
                    style['color'] = fg
                    pw.setLabel('right', **style)

            pw.showGrid(x=True, y=True, alpha=alpha)
            # Update legend styling
            try:
                legend = pw.getPlotItem().legend
                if legend is not None:
                    legend.setLabelTextColor(fg)
                    legend_bg = THEME.c('legend_bg')
                    if isinstance(legend_bg, tuple):
                        legend.setBrush(pg.mkBrush(*legend_bg))
                    else:
                        legend.setBrush(pg.mkBrush(legend_bg))
            except Exception:
                pass

        # Update crosshair pen styling
        try:
            crosshair_pen = pg.mkPen(THEME.c('crosshair'), width=1, style=Qt.DashLine)
            for lines in self._crosshair_lines.values():
                for line in lines:
                    line.setPen(crosshair_pen)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    # Log loading
    # ──────────────────────────────────────────────────────────────────
    def _next_color(self) -> str:
        c = LOG_COLORS[self._color_index % len(LOG_COLORS)]
        self._color_index += 1
        return c

    def _on_load_logs(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Load Test Log Files", get_datalogs_dir(),
            "Log Files (*.xlsx *.csv);;Excel Files (*.xlsx);;CSV Files (*.csv)")
        if not paths:
            return
        for path in paths:
            if any(l.path == path for l in self._logs.values()):
                continue
            log_id = uuid.uuid4().hex[:8]
            color = self._next_color()
            thread = LogLoaderThread(path, log_id, color, self)
            thread.sigFinished.connect(self._on_log_loaded)
            thread.sigProgress.connect(self._on_load_progress)
            thread.error.connect(self._on_load_error)
            thread.finished.connect(lambda t=thread: self._cleanup_thread(t))
            self._loader_threads.append(thread)
            thread.start()

        n = len(self._loader_threads)
        if n:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._status.showMessage(f"Loading {n} file(s)... please wait")

    def _on_load_progress(self, percent: int):
        n = len(self._loader_threads)
        if n > 0:
            self._status.showMessage(f"Loading {n} file(s)... {percent}%")

    def _cleanup_thread(self, t):
        if t in self._loader_threads:
            self._loader_threads.remove(t)
        if not self._loader_threads:
            QApplication.restoreOverrideCursor()

    def _on_log_loaded(self, log_id: str, path: str, entry: LogEntry):
        self._logs[log_id] = entry
        self._push_recent_file(path)
        self._add_log_to_sidebar(entry)
        self._compute_math_channels(entry)
        self._rebuild_param_list()
        self._rebuild_plots()
        self._status.showMessage(
            f"Loaded: {entry.name}  ({len(entry.elapsed)} rows)", 5000)

    def _on_load_error(self, path: str, msg: str):
        self._status.showMessage(f"Error loading {os.path.basename(path)}: {msg}", 8000)
        QApplication.restoreOverrideCursor()  # restore on error too
        _log.error("Log load failed: path=%s err=%s", path, msg)
        self._popup_warning("Load Error", f"Could not load:\n{path}\n\n{msg}")

    def _add_custom_math_channel(self):
        name, ok = QInputDialog.getText(self, "Math Channel", "Channel Name (e.g. Power):")
        if not ok or not name.strip():
            return
        name = name.strip()

        # Check if already exists in loaded logs? Overwriting is fine.
        expr, ok = QInputDialog.getText(
            self, "Math Channel",
            "Formula (e.g. [Voltage] * [Current] / 1000, diff([Speed]), integral([Power])/3600):"
        )
        if not ok or not expr.strip():
            return

        self._math_channels[name] = expr.strip()
        self._qsettings.setValue("analysis/math_channels", self._math_channels)

        for log in self._logs.values():
            self._compute_math_channels(log)

        self._rebuild_param_list()
        self._rebuild_plots()
        self._status.showMessage(f"Added Math Channel: {name}", 5000)

    def _remove_custom_math_channel(self):
        from PySide6.QtWidgets import QMessageBox
        if not self._math_channels:
            QMessageBox.information(self, "Remove Math Channel", "No custom math channels exist.")
            return

        items = list(self._math_channels.keys())
        item, ok = QInputDialog.getItem(self, "Remove Math Channel", "Select channel to remove:", items, 0, False)
        if not ok or not item:
            return

        del self._math_channels[item]
        self._qsettings.setValue("analysis/math_channels", self._math_channels)

        for log in self._logs.values():
            if item in log.columns:
                del log.columns[item]

        self._rebuild_param_list()
        self._rebuild_plots()
        self._status.showMessage(f"Removed Math Channel: {item}", 5000)

    def _configure_import_schema(self):
        from .dialogs import SchemaMapperDialog
        from PySide6.QtWidgets import QDialog
        dlg = SchemaMapperDialog(self._qsettings, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._status.showMessage("Import schema mapping configuration saved.", 5000)

    def _compute_math_channels(self, log: LogEntry):
        def diff_func(y):
            if len(log.elapsed) <= 1:
                return np.zeros_like(y)
            return np.gradient(y, log.elapsed)

        def integral_func(y):
            if len(log.elapsed) <= 1:
                return np.zeros_like(y)
            dt = np.diff(log.elapsed)
            y_avg = 0.5 * (y[:-1] + y[1:])
            integrand = y_avg * dt
            return np.insert(np.cumsum(integrand), 0, 0.0)

        for name, expr in self._math_channels.items():
            py_expr = re.sub(r'\[(.*?)\]', r'data["\1"]', expr)
            try:
                # Evaluate expression vectorised over numpy arrays.
                # All signals for a log are already uniform length from log_io!
                res = eval(
                    py_expr,
                    {
                        "__builtins__": None,
                        "np": np,
                        "diff": diff_func,
                        "deriv": diff_func,
                        "derivative": diff_func,
                        "integral": integral_func,
                        "int": integral_func,
                        "cumsum": integral_func,
                    },
                    {"data": log.columns}
                )
                log.columns[name] = res
            except Exception as e:
                _log.warning(f"Math channel '{name}' failed to compute for log {log.name}: {e}")

    def _add_log_to_sidebar(self, entry: LogEntry):
        """Add a log entry as an inline row: [checkbox] [color swatch] name [offset spin]"""
        row = QHBoxLayout()
        row.setContentsMargins(2, 1, 2, 1)
        row.setSpacing(4)

        cb = QCheckBox()
        cb.setChecked(entry.visible)
        cb.stateChanged.connect(lambda state, lid=entry.id:
                                self._on_log_visibility_toggled(lid, state == 2))
        row.addWidget(cb)

        swatch = QLabel("\u25cf")
        swatch.setFont(QFont("PT Sans", 12))
        swatch.setStyleSheet(f"color: {entry.color};")
        swatch.setFixedWidth(16)
        swatch.setCursor(Qt.PointingHandCursor)
        swatch.mousePressEvent = lambda e, lid=entry.id: self._change_log_color(lid)
        row.addWidget(swatch)

        name_lbl = QLabel(entry.name)
        name_lbl.setFont(QFont("PT Sans", 8))
        name_lbl.setToolTip(entry.path)
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.addWidget(name_lbl, stretch=1)

        spin = QDoubleSpinBox()
        spin.setRange(-999.0, 999.0)
        spin.setSingleStep(0.1)
        spin.setDecimals(2)
        spin.setSuffix(" s")
        spin.setValue(entry.time_offset)
        spin.setFont(QFont("PT Sans", 8))
        spin.setFixedWidth(80)
        spin.setToolTip("Time offset")
        spin.valueChanged.connect(lambda v, lid=entry.id: self._on_offset_changed(lid, v))
        row.addWidget(spin)

        container = QWidget()
        container.setLayout(row)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Insert before the stretch
        idx = self._log_list_layout.count() - 1
        self._log_list_layout.insertWidget(idx, container)

        self._log_entries_ui[entry.id] = {
            'checkbox': cb, 'spin': spin, 'container': container,
            'swatch': swatch, 'name_lbl': name_lbl,
        }

    def _on_remove_selected(self):
        if not self._logs:
            return
        last_id = list(self._logs.keys())[-1]
        self._remove_log(last_id)

    def _remove_log(self, log_id: str):
        entry = self._logs.pop(log_id, None)
        # Free cached parsed data so memory is released
        if entry is not None:
            _CSV_CACHE.pop(entry.path, None)
            entry.elapsed = np.zeros(0)
            entry.columns.clear()
        ui = self._log_entries_ui.pop(log_id, None)
        if ui:
            ui['container'].deleteLater()
        self._curves.pop(log_id, None)
        self._rebuild_param_list()
        self._rebuild_plots()

    def _change_log_color(self, log_id: str):
        entry = self._logs.get(log_id)
        if not entry:
            return
        c = QColorDialog.getColor(QColor(entry.color), self, "Log Color")
        if c.isValid():
            entry.color = c.name()
            ui = self._log_entries_ui.get(log_id)
            if ui:
                ui['swatch'].setStyleSheet(f"color: {c.name()};")
            self._rebuild_plots()

    def _on_log_visibility_toggled(self, log_id: str, visible: bool):
        if log_id not in self._logs:
            return
        self._logs[log_id].visible = visible
        self._update_curve_visibility(log_id, visible)

    def _update_curve_visibility(self, log_id: str, visible: bool):
        if log_id in self._curves:
            for curve in self._curves[log_id].values():
                curve.setVisible(visible)
        self._update_cursor_dots()
        self._update_cursor_readout()

    # ──────────────────────────────────────────────────────────────────
    # Time offset
    # ──────────────────────────────────────────────────────────────────
    def _on_offset_changed(self, log_id: str, value: float):
        entry = self._logs.get(log_id)
        if not entry:
            return
        entry.time_offset = value
        self._update_curves_for_log(log_id)
        self._update_cursor_dots()
        self._update_cursor_readout()

    def _update_curves_for_log(self, log_id: str):
        entry = self._logs.get(log_id)
        if not entry:
            return
        x = entry.elapsed + entry.time_offset
        if log_id in self._curves:
            for param, curve in self._curves[log_id].items():
                if param in entry.columns:
                    y = entry.columns[param]
                    mask = ~np.isnan(y)
                    curve.setData(x[mask], y[mask])

    # ──────────────────────────────────────────────────────────────────
    # Plot Layout
    # ──────────────────────────────────────────────────────────────────
    def _on_layout_changed(self, layout: str):
        self._qsettings.setValue("analysis/layout", layout)
        self._rebuild_plots()

    # ──────────────────────────────────────────────────────────────────
    # Parameter selector
    # ──────────────────────────────────────────────────────────────────
    # ------------------------------------------------------------------
    # Subplot/parameter tree helpers
    # ------------------------------------------------------------------
    def _collect_available_params(self) -> list[str]:
        """Union of parameter names across all loaded logs (order preserved)."""
        out: list[str] = []
        seen = set()
        for entry in self._logs.values():
            for p in entry.available_params():
                if p not in seen:
                    seen.add(p)
                    out.append(p)
        return out

    def _rebuild_param_list(self, uncheck_params: set[str] = None):
        """Rebuild the flat parameter list with inline dropdowns."""
        tree = self._param_tree
        scrollbar = tree.verticalScrollBar()
        scroll_pos = scrollbar.value()
        tree.blockSignals(True)
        self._populating_tree = True

        # Snapshot prior check state by param name
        prev_checked: set[str] = set()
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                prev_checked.add(item.text(0))

        if uncheck_params:
            prev_checked.difference_update(uncheck_params)

        all_params = self._collect_available_params()

        # Build working layout: keep existing layout groups that are still in all_params
        layout: list[list[str]] = []
        placed: set[str] = set()
        for grp in self._subplot_layout:
            kept = [p for p in grp if p in all_params]
            if kept:
                layout.append(kept)
                placed.update(kept)
        for p in all_params:
            if p not in placed:
                layout.append([p])

        first_build = not self._subplot_layout and not prev_checked
        self._subplot_layout = layout

        # If first build, pre-check DEFAULT_PARAMS
        if first_build:
            for p in DEFAULT_PARAMS:
                if p in all_params:
                    prev_checked.add(p)

        tree.clear()

        # Sort alphabetically for list readability
        sorted_params = sorted(all_params)

        for p in sorted_params:
            item = QTreeWidgetItem(tree, [p, ""])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)

            is_checked = p in prev_checked
            item.setCheckState(0, Qt.Checked if is_checked else Qt.Unchecked)
            item.setData(0, Qt.UserRole, "param")

            # Create combobox for Column 1
            combo = QComboBox()
            combo.setFont(QFont("PT Sans", 8))

            # Populate dropdown
            N = len(self._subplot_layout)
            for si in range(N):
                combo.addItem(f"Subplot {si + 1}")
            combo.addItem("+ New Subplot")
            combo.addItem("Off")

            # Select current subplot or Off
            sub_idx = -1
            for si, grp in enumerate(self._subplot_layout):
                if p in grp:
                    sub_idx = si
                    break

            if not is_checked:
                combo.setCurrentIndex(N + 1)
            else:
                if sub_idx != -1:
                    combo.setCurrentIndex(sub_idx)
                else:
                    combo.setCurrentIndex(0)

            # Connect combo activation signal
            combo.activated.connect(lambda idx, param=p, cb=item: self._on_param_subplot_changed(param, cb, idx))

            tree.addTopLevelItem(item)
            tree.setItemWidget(item, 1, combo)

        tree.blockSignals(False)
        self._populating_tree = False

        # Re-apply the active filter to newly added rows
        self._apply_param_filter(self._param_search.text())

        # Rebuild settings combo choices
        self._rebuild_subplot_settings_combo()
        scrollbar.setValue(scroll_pos)

    @staticmethod
    def _strip_units(name: str) -> str:
        """Strip a trailing ' (Unit)' from a param name so the short label fits.
        Keeps interior parens intact (rare). ``Vehicle Speed (Kmph)`` → ``Vehicle Speed``."""
        return re.sub(r'\s*\([^()]*\)\s*$', '', name).strip() or name

    @staticmethod
    def _extract_unit(name: str) -> str:
        match = re.search(r'\(([^()]*)\)\s*$', name)
        return match.group(1).strip() if match else ""


    def _axis_title_for_group(self, group: list[str]) -> str:
        """Compact label suitable for a rotated Y-axis title — strips units
        and tops out at two params + '+N' so it never overshoots vertically."""
        if not group:
            return ""
        names = [self._strip_units(p) for p in group]
        head = ", ".join(names[:2])
        if len(names) > 2:
            head += f"  +{len(names) - 2}"
        return head

    def _get_subplot_groups(self) -> list[list[str]]:
        """Return list of param lists for currently checked items, skipping
        any subplot whose params are all unchecked."""
        tree = self._param_tree
        checked_params = set()
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                checked_params.add(item.text(0))

        groups: list[list[str]] = []
        for grp in self._subplot_layout:
            checked_in_grp = [p for p in grp if p in checked_params]
            if checked_in_grp:
                groups.append(checked_in_grp)
        return groups

    def _set_all_params(self, checked: bool):
        tree = self._param_tree
        tree.blockSignals(True)
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if not item.isHidden():
                item.setCheckState(0, state)
                combo = tree.itemWidget(item, 1)
                if isinstance(combo, QComboBox):
                    N = len(self._subplot_layout)
                    if checked:
                        param = item.text(0)
                        sub_idx = -1
                        for si, grp in enumerate(self._subplot_layout):
                            if param in grp:
                                sub_idx = si
                                break
                        if sub_idx != -1:
                            combo.setCurrentIndex(sub_idx)
                        else:
                            combo.setCurrentIndex(0)
                    else:
                        combo.setCurrentIndex(N + 1)
        tree.blockSignals(False)
        self._rebuild_plots()
        self._refresh_subplot_control_states()

    def _on_param_changed(self, item: QTreeWidgetItem, column: int = 0):
        if self._populating_tree:
            return
        role = item.data(0, Qt.UserRole)
        if role == "param":
            param = item.text(0)
            is_checked = item.checkState(0) == Qt.Checked

            combo = self._param_tree.itemWidget(item, 1)
            if isinstance(combo, QComboBox):
                N = len(self._subplot_layout)
                if is_checked:
                    sub_idx = -1
                    for si, grp in enumerate(self._subplot_layout):
                        if param in grp:
                            sub_idx = si
                            break
                    if sub_idx != -1:
                        combo.setCurrentIndex(sub_idx)
                    else:
                        combo.setCurrentIndex(0)
                else:
                    combo.setCurrentIndex(N + 1)

            self._rebuild_plots()
            self._refresh_subplot_control_states()

    def _on_param_subplot_changed(self, param: str, item: QTreeWidgetItem, combo_idx: int):
        """Callback when the user changes a parameter's subplot combobox."""
        N = len(self._subplot_layout)

        if combo_idx == N + 1:
            # "Off" selected
            item.setCheckState(0, Qt.Unchecked)
        else:
            # Subplot 1..N or + New Subplot
            item.setCheckState(0, Qt.Checked)

            for grp in self._subplot_layout:
                if param in grp:
                    grp.remove(param)

            if combo_idx == N:
                self._subplot_layout.append([param])
            else:
                if combo_idx < len(self._subplot_layout):
                    self._subplot_layout[combo_idx].append(param)
                else:
                    self._subplot_layout.append([param])

            # Prune empty subplots
            self._subplot_layout = [grp for grp in self._subplot_layout if len(grp) > 0]

        self._rebuild_param_list()
        self._rebuild_plots()

    def _rebuild_subplot_settings_combo(self):
        """Populate the Subplot settings dropdown with all active subplots."""
        combo = self._subplot_settings_combo
        combo.blockSignals(True)
        prev_selection = combo.currentText()
        combo.clear()
        N = len(self._subplot_layout)
        for si in range(N):
            combo.addItem(f"Subplot {si + 1}")
        index = combo.findText(prev_selection)
        if index != -1:
            combo.setCurrentIndex(index)
        elif N > 0:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)
        self._refresh_subplot_control_states()

    def _refresh_subplot_control_states(self):
        """Update checkbox states and button enabled/disabled states based on selected subplot."""
        combo = self._subplot_settings_combo
        text = combo.currentText()
        if not text:
            self._subplot_normalize_cb.setEnabled(False)
            self._subplot_normalize_cb.setChecked(False)
            self._subplot_smooth_cb.setEnabled(False)
            self._subplot_smooth_cb.setChecked(False)
            self._subplot_up_btn.setEnabled(False)
            self._subplot_down_btn.setEnabled(False)
            self._subplot_delete_btn.setEnabled(False)
            return

        try:
            sub_idx = int(text.split()[-1]) - 1
        except Exception:
            return

        N = len(self._subplot_layout)
        if not (0 <= sub_idx < N):
            return

        self._subplot_normalize_cb.setEnabled(True)
        self._subplot_smooth_cb.setEnabled(True)
        self._subplot_delete_btn.setEnabled(True)

        self._subplot_up_btn.setEnabled(sub_idx > 0)
        self._subplot_down_btn.setEnabled(sub_idx < N - 1)

        grp = self._subplot_layout[sub_idx]
        key = frozenset(grp)

        self._subplot_normalize_cb.blockSignals(True)
        self._subplot_normalize_cb.setChecked(key in self._normalized_subplots)
        self._subplot_normalize_cb.blockSignals(False)

        self._subplot_smooth_cb.blockSignals(True)
        self._subplot_smooth_cb.setChecked(key in self._smoothed_subplots)
        self._subplot_smooth_cb.blockSignals(False)

    def _on_subplot_settings_combo_changed(self, text: str):
        self._refresh_subplot_control_states()

    def _on_subplot_normalize_toggled(self, state: int):
        sub_idx = self._subplot_settings_combo.currentIndex()
        if 0 <= sub_idx < len(self._subplot_layout):
            grp = self._subplot_layout[sub_idx]
            key = frozenset(grp)
            if state == 2:
                self._normalized_subplots.add(key)
            else:
                self._normalized_subplots.discard(key)
            self._rebuild_plots()

    def _on_subplot_smooth_toggled(self, state: int):
        sub_idx = self._subplot_settings_combo.currentIndex()
        if 0 <= sub_idx < len(self._subplot_layout):
            grp = self._subplot_layout[sub_idx]
            key = frozenset(grp)
            if state == 2:
                self._smoothed_subplots.add(key)
            else:
                self._smoothed_subplots.discard(key)
            self._rebuild_plots()

    def _on_subplot_move_up(self):
        sub_idx = self._subplot_settings_combo.currentIndex()
        if sub_idx > 0 and sub_idx < len(self._subplot_layout):
            self._subplot_layout[sub_idx], self._subplot_layout[sub_idx - 1] = \
                self._subplot_layout[sub_idx - 1], self._subplot_layout[sub_idx]
            self._rebuild_param_list()
            self._subplot_settings_combo.setCurrentIndex(sub_idx - 1)
            self._rebuild_plots()

    def _on_subplot_move_down(self):
        sub_idx = self._subplot_settings_combo.currentIndex()
        if sub_idx >= 0 and sub_idx < len(self._subplot_layout) - 1:
            self._subplot_layout[sub_idx], self._subplot_layout[sub_idx + 1] = \
                self._subplot_layout[sub_idx + 1], self._subplot_layout[sub_idx]
            self._rebuild_param_list()
            self._subplot_settings_combo.setCurrentIndex(sub_idx + 1)
            self._rebuild_plots()

    def _on_subplot_delete(self):
        sub_idx = self._subplot_settings_combo.currentIndex()
        if 0 <= sub_idx < len(self._subplot_layout):
            grp = self._subplot_layout[sub_idx]
            ret = QMessageBox.question(
                self, "Delete Subplot",
                f"Are you sure you want to delete Subplot {sub_idx + 1}?\n"
                f"This will uncheck/hide its {len(grp)} parameters.",
                QMessageBox.Yes | QMessageBox.No
            )
            if ret == QMessageBox.Yes:
                uncheck = set(grp)
                self._subplot_layout.pop(sub_idx)
                self._rebuild_param_list(uncheck_params=uncheck)
                self._rebuild_plots()

    def _on_param_search_changed(self, text: str):
        self._apply_param_filter(text)

    def _apply_param_filter(self, text: str):
        query = (text or "").strip().lower()
        tree = self._param_tree
        total = 0
        matches = 0
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            total += 1
            is_hit = (not query) or (query in item.text(0).lower())
            item.setHidden(not is_hit)
            if is_hit:
                matches += 1

        if not query:
            self._param_hit_count.setText("")
        else:
            self._param_hit_count.setText(f"{matches}/{total}")

    def _is_subplot_normalized(self, group: list[str]) -> bool:
        return frozenset(group) in self._normalized_subplots

    @staticmethod
    def _normalize_series(y: np.ndarray) -> np.ndarray:
        """Min-max scale a 1-D array to [0,1]. Constant or all-NaN series
        return zeros (so they plot flat instead of crashing)."""
        finite = y[np.isfinite(y)]
        if finite.size == 0:
            return np.zeros_like(y)
        lo = float(np.min(finite))
        hi = float(np.max(finite))
        if hi - lo < 1e-12:
            return np.zeros_like(y)
        return (y - lo) / (hi - lo)

    def _is_subplot_smoothed(self, group: list[str]) -> bool:
        return frozenset(group) in self._smoothed_subplots

    def _prompt_smoothing_window(self):
        from PySide6.QtWidgets import QInputDialog
        new_n, ok = QInputDialog.getInt(
            self, "Smoothing Window",
            "Rolling-average window size (samples).\n"
            "Applies to subplots with smoothing enabled.",
            self._smoothing_window, 1, 999, 1)
        if not ok:
            return
        self._smoothing_window = int(new_n)
        if self._smoothed_subplots:
            self._rebuild_plots()
        else:
            self._status.showMessage(
                f"Smoothing window set to {new_n}. Toggle Smooth on subplot toolbar to enable it.", 6000)

    @staticmethod
    def _moving_average(y: np.ndarray, window: int) -> np.ndarray:
        """NaN-aware centered rolling mean. Window < 2 returns the input."""
        if window is None or window < 2:
            return y
        y = np.asarray(y, dtype=float)
        if y.size == 0:
            return y
        finite = np.isfinite(y)
        y_clean = np.where(finite, y, 0.0)
        weights = np.ones(int(window))
        summed = np.convolve(y_clean, weights, mode='same')
        counted = np.convolve(finite.astype(float), weights, mode='same')
        with np.errstate(invalid='ignore', divide='ignore'):
            out = np.where(counted > 0, summed / counted, np.nan)
        return out

    def _on_auto_fit_y_toggled(self, on: bool):
        self._auto_fit_y = bool(on)
        if on:
            self._apply_auto_fit_y()

    def _apply_auto_fit_y(self):
        """For each subplot, compute the Y range over the currently visible
        X window across all visible curves, then set the y view-range with
        a small padding. No-op when there are no plots."""
        if not self._plot_widgets:
            return
        for pi, pw in enumerate(self._plot_widgets):
            if pi >= len(self._plot_groups):
                continue
            group = self._plot_groups[pi]
            try:
                x_range = tuple(pw.getPlotItem().vb.viewRange()[0])
            except Exception:
                continue
            normalized = self._is_subplot_normalized(group)
            left_unit = getattr(pw, 'left_unit', None)
            right_unit = getattr(pw, 'right_unit', None)

            ymin_left, ymax_left = np.inf, -np.inf
            ymin_right, ymax_right = np.inf, -np.inf

            for param in group:
                unit = self._extract_unit(param)
                is_right = (hasattr(pw, 'right_vb') and pw.right_vb is not None and right_unit is not None and unit != left_unit)
                for entry in self._logs.values():
                    if not entry.visible or param not in entry.columns:
                        continue
                    x = entry.elapsed + entry.time_offset
                    y = entry.columns[param]
                    if normalized:
                        y = self._normalize_series(y)
                    if x.size == 0:
                        continue
                    mask = (x >= x_range[0]) & (x <= x_range[1]) & np.isfinite(y)
                    if not np.any(mask):
                        continue
                    val_min = float(np.min(y[mask]))
                    val_max = float(np.max(y[mask]))
                    if is_right:
                        ymin_right = min(ymin_right, val_min)
                        ymax_right = max(ymax_right, val_max)
                    else:
                        ymin_left = min(ymin_left, val_min)
                        ymax_left = max(ymax_left, val_max)

            if ymin_left != np.inf and ymax_left != -np.inf:
                if ymax_left - ymin_left < 1e-12:
                    pad = max(abs(ymax_left) * 0.05, 0.5)
                    ymin_left -= pad
                    ymax_left += pad
                else:
                    pad = (ymax_left - ymin_left) * 0.05
                    ymin_left -= pad
                    ymax_left += pad
                pw.getPlotItem().vb.setYRange(ymin_left, ymax_left, padding=0)

            if hasattr(pw, 'right_vb') and pw.right_vb is not None and ymin_right != np.inf and ymax_right != -np.inf:
                if ymax_right - ymin_right < 1e-12:
                    pad = max(abs(ymax_right) * 0.05, 0.5)
                    ymin_right -= pad
                    ymax_right += pad
                else:
                    pad = (ymax_right - ymin_right) * 0.05
                    ymin_right -= pad
                    ymax_right += pad
                pw.right_vb.setYRange(ymin_right, ymax_right, padding=0)

    def _export_visible_csv(self):
        """Wide-format CSV export of every visible (log, param) curve, sliced
        to the current x view range. All series are interpolated onto a
        common time grid (the union of visible-range timestamps of the first
        log) so the file opens cleanly in Excel/pandas."""
        rows = self._visible_curve_rows()
        if not rows:
            self._popup_information(
                "Nothing to Export",
                "Load logs and check parameters before exporting.")
            return

        x_range = rows[0].get("x_range")
        masters: list[np.ndarray] = []
        for r in rows:
            x = r["x"]
            if x_range is not None:
                mask = (x >= x_range[0]) & (x <= x_range[1])
                masters.append(x[mask])
            else:
                masters.append(x)
        if not masters:
            self._popup_information("Nothing to Export", "No samples in range.")
            return
        merged = np.unique(np.concatenate(masters))
        if merged.size == 0:
            self._popup_information("Nothing to Export", "No samples in range.")
            return

        rate, ok = QInputDialog.getInt(
            self,
            "Decimate Export",
            "Export 1 out of every N samples?\n(1 = export every sample)",
            value=1,
            minValue=1,
            maxValue=100000,
        )
        if not ok:
            return

        suggested = os.path.join(
            get_analysis_dir(),
            f"{APP_NAME}_visible_data.csv")
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export Visible Data", suggested, "CSV Files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        from PySide6.QtWidgets import QProgressDialog
        progress_dlg = QProgressDialog(
            "Preparing export...", "Cancel", 0, 100, self
        )
        progress_dlg.setWindowTitle("Exporting CSV")
        progress_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setAutoClose(True)
        progress_dlg.setAutoReset(True)
        progress_dlg.setValue(0)
        progress_dlg.show()

        thread = CSVExportThread(path, rows, rate, self)
        thread.sigProgress.connect(progress_dlg.setValue)

        def on_error(err_msg):
            progress_dlg.close()
            self._popup_warning("Export Failed", err_msg)

        def on_finished(out_path, total_rows_written):
            progress_dlg.close()
            self._status.showMessage(
                f"Exported {len(rows)} curve(s) × {total_rows_written} rows to "
                f"{os.path.basename(out_path)}", 6000)

        thread.sigError.connect(on_error)
        thread.sigFinished.connect(on_finished)
        progress_dlg.canceled.connect(thread.requestInterruption)

        self._export_thread = thread
        thread.finished.connect(lambda: setattr(self, "_export_thread", None))
        thread.start()

    # ──────────────────────────────────────────────────────────────────
    # Recent files (Phase 2)
    # ──────────────────────────────────────────────────────────────────
    _RECENT_KEY = "analysis/recent_files"
    _RECENT_MAX = 10

    def _load_recent_files(self) -> list[str]:
        raw = self._qsettings.value(self._RECENT_KEY, [])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raw = []
        return [p for p in raw if p and os.path.isfile(p)]

    def _save_recent_files(self):
        self._qsettings.setValue(self._RECENT_KEY, self._recent_files)

    def _push_recent_file(self, path: str):
        if not path:
            return
        path = os.path.abspath(path)
        if not self._recent_files:
            self._recent_files = self._load_recent_files()
        self._recent_files = [p for p in self._recent_files if p != path]
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:self._RECENT_MAX]
        self._save_recent_files()

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        recent = self._load_recent_files()
        self._recent_files = recent
        if not recent:
            act = self._recent_menu.addAction("(no recent files)")
            act.setEnabled(False)
            return
        for path in recent:
            act = self._recent_menu.addAction(os.path.basename(path))
            act.setToolTip(path)
            act.triggered.connect(lambda _checked=False, p=path:
                                   self._load_single_path(p))
        self._recent_menu.addSeparator()
        clear_act = self._recent_menu.addAction("Clear Recent Files")
        clear_act.triggered.connect(self._clear_recent_files)

    def _clear_recent_files(self):
        self._recent_files = []
        self._save_recent_files()

    def _load_single_path(self, path: str):
        """Load a single log path via the same LogLoaderThread used by the
        file picker. Skips files already loaded."""
        if any(l.path == path for l in self._logs.values()):
            self._status.showMessage(f"Already loaded: {os.path.basename(path)}", 4000)
            return
        if not os.path.isfile(path):
            self._popup_warning("File Not Found", path)
            return
        log_id = uuid.uuid4().hex[:8]
        color = self._next_color()
        thread = LogLoaderThread(path, log_id, color, self)
        thread.sigFinished.connect(self._on_log_loaded)
        thread.error.connect(self._on_load_error)
        thread.finished.connect(lambda t=thread: self._cleanup_thread(t))
        self._loader_threads.append(thread)
        thread.start()


    # ──────────────────────────────────────────────────────────────────
    # Plot management
    # ──────────────────────────────────────────────────────────────────
    def _rebuild_plots(self):
        """Tear down and rebuild all subplots based on current state."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._do_rebuild_plots()
        finally:
            QApplication.restoreOverrideCursor()

    def _do_rebuild_plots(self):
        prev_x_range = None
        if self._plot_widgets:
            try:
                prev_x_range = self._plot_widgets[0].getPlotItem().vb.viewRange()[0]
            except Exception:
                pass

        for pw in self._plot_widgets:
            self._plot_layout.removeWidget(pw)
            pw.deleteLater()
        self._plot_widgets.clear()
        self._plot_groups.clear()
        self._curves.clear()
        self._crosshair_lines.clear()
        self._cursor_dots.clear()

        while self._plot_layout.count():
            item = self._plot_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        groups = self._get_subplot_groups()
        if not groups or not self._logs:
            self._update_cursor_readout()
            self._refresh_stats_panel()
            return

        bg = THEME.c('plot_bg')
        fg = THEME.c('plot_fg')
        alpha = THEME.plot_grid_alpha()

        first_pw = None
        for gi, group in enumerate(groups):
            # Determine left and right units
            left_unit = None
            right_unit = None
            for param in group:
                unit = self._extract_unit(param)
                if left_unit is None:
                    left_unit = unit
                elif unit != left_unit and right_unit is None:
                    right_unit = unit

            pw = pg.PlotWidget(
                axisItems={'bottom': TimeAxisItem(orientation='bottom')})
            pw.setBackground(bg)
            pw.showGrid(x=True, y=True, alpha=alpha)
            normalized = self._is_subplot_normalized(group)
            smoothed = self._is_subplot_smoothed(group)
            pw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            pw.setFixedHeight(self._plot_height)

            pw.left_unit = left_unit
            pw.right_unit = right_unit
            pw.right_vb = None
            pw.right_axis = None

            # Visible card-style border around each subplot so the boundary
            # is unambiguous, and internal padding so axis tick labels never
            # collide with the border or the next subplot.
            border_color = THEME.c('border')
            pw.setStyleSheet(
                f"border: 1px solid {border_color}; border-radius: 4px;"
            )
            plot_item = pw.getPlotItem()
            # (left, top, right, bottom) inside the plot — extra left padding
            # so wide tick labels (e.g. 60000) plus the rotated axis title
            # have room without colliding with the border.
            plot_item.setContentsMargins(14, 8, 14, 8)
            # Reserve a minimum width for the y-axis so tick labels and title
            # don't fight for the same pixels when values are big or names
            # are long. Width auto-grows beyond this if needed.
            plot_item.getAxis('left').setWidth(64)
            pw.setLabel('left', left_unit if left_unit else '')

            if right_unit is not None:
                pw.right_vb = OverlayViewBox()
                plot_item.scene().addItem(pw.right_vb)
                plot_item.showAxis('right')
                ax = plot_item.getAxis('right')
                ax.linkToView(pw.right_vb)
                pw.right_vb.setXLink(plot_item.getViewBox())
                pw.right_axis = ax
                ax.setWidth(64)

                pen = pg.mkPen(fg)
                ax.setPen(pen)
                ax.setTextPen(pen)
                if hasattr(ax, 'labelStyle'):
                    style = dict(ax.labelStyle)
                    style['color'] = fg
                    pw.setLabel('right', right_unit, **style)
                else:
                    pw.setLabel('right', right_unit)

                def updateViews(dummy_arg=None, target_pi=plot_item, target_vb=pw.right_vb):
                    if target_vb is not None and target_pi is not None:
                        vb = target_pi.getViewBox()
                        if vb is not None:
                            target_vb.setGeometry(vb.sceneBoundingRect())
                            target_vb.linkedViewChanged(vb, target_vb.XAxis)

                plot_item.getViewBox().sigResized.connect(updateViews)
                updateViews()

            from .plot_panel import GRID_LAYOUTS
            rows, cols = GRID_LAYOUTS.get(self._layout_combo.currentText(), (2, 1))
            grid_row = gi // cols
            grid_col = gi % cols
            self._plot_layout.addWidget(pw, grid_row, grid_col)
            # _plot_widgets and _plot_groups MUST stay in lockstep: the
            # mouse SignalProxy created below fires at 60fps and indexes
            # both lists with the same `pi`. If we appended to _plot_groups
            # at the end of the iteration body, a mouse move during widget
            # setup (curve plotting, axis labels) would see _plot_widgets
            # ahead of _plot_groups and raise IndexError in _on_mouse_moved.
            self._plot_widgets.append(pw)
            self._plot_groups.append(list(group))

            # Performance: clip and downsample
            pw.setClipToView(True)
            pw.setDownsampling(auto=True, mode='peak')

            # Y-axis padding so curves don't touch the frame
            pw.getPlotItem().vb.setDefaultPadding(0.05)

            for axis_name in ('left', 'bottom'):
                ax = pw.getAxis(axis_name)
                pen = pg.mkPen(fg)
                ax.setPen(pen)
                ax.setTextPen(pen)

            if gi == len(groups) - 1:
                pw.setLabel('bottom', 'Elapsed time (mm:ss)')
            else:
                pw.setLabel('bottom', '')

            # Apply wall-clock mode if active
            time_axis = pw.getAxis('bottom')
            if isinstance(time_axis, TimeAxisItem) and self._wall_clock_mode:
                epoch = self._best_epoch_offset()
                time_axis.epoch_offset = epoch

            if first_pw is not None:
                pw.setXLink(first_pw)
            else:
                first_pw = pw

            legend = pw.addLegend(offset=(10, 10))
            legend.setLabelTextSize('7pt')
            legend_bg = THEME.c('legend_bg')
            if isinstance(legend_bg, tuple):
                legend.setBrush(pg.mkBrush(*legend_bg))
            else:
                legend.setBrush(pg.mkBrush(legend_bg))
            legend.setLabelTextColor(fg)

            multi = len(group) > 1
            log_list = list(self._logs.values())
            for param in group:
                for li, entry in enumerate(log_list):
                    if param not in entry.columns:
                        continue
                    x = entry.elapsed + entry.time_offset
                    y = entry.columns[param]
                    if smoothed:
                        y = self._moving_average(y, self._smoothing_window)
                    if normalized:
                        y = self._normalize_series(y)
                    mask = ~np.isnan(y)
                    # Multi-param: color = parameter, style = log.
                    # Single-param: color = log, style = solid.
                    curve_color, style = _curve_visuals(group, param, li, entry.color)
                    pen = pg.mkPen(color=curve_color, width=1.6, style=style)
                    # Legend entry always carries the parameter name (with
                    # unit when present) because the rotated y-axis label
                    # was removed. Format: "<param> · <log>" so the
                    # variable is the primary identifier and the log is
                    # the qualifier when multiple logs are loaded.
                    # Single-log + single-param: skip the redundant log
                    # suffix to keep the legend compact.
                    if multi or len(self._logs) > 1:
                        legend_name = f"{param} · {entry.name}"
                    else:
                        legend_name = param
                    # Annotate per-subplot transforms in the legend since
                    # they used to live in the (now-removed) axis title.
                    if normalized or smoothed:
                        suffix_parts = []
                        if normalized:
                            suffix_parts.append("norm")
                        if smoothed:
                            suffix_parts.append(f"smooth N={self._smoothing_window}")
                        legend_name = f"{legend_name}  ({', '.join(suffix_parts)})"

                    # Decouple left and right viewbox curves:
                    unit = self._extract_unit(param)
                    is_right = (right_unit is not None and unit != left_unit)
                    target_vb = pw.right_vb if is_right else plot_item.vb

                    curve = pg.PlotDataItem(x[mask], y[mask], pen=pen, name=legend_name)
                    target_vb.addItem(curve)
                    if legend is not None:
                        legend.addItem(curve, name=legend_name)

                    curve.setVisible(entry.visible)
                    curve.setClipToView(True)
                    self._curves.setdefault(entry.id, {})[param] = curve

            # Crosshair
            vline = pg.InfiniteLine(angle=90, movable=False,
                                    pen=pg.mkPen(THEME.c('crosshair'),
                                                 width=1, style=Qt.DashLine))
            hline = pg.InfiniteLine(angle=0, movable=False,
                                    pen=pg.mkPen(THEME.c('crosshair'),
                                                 width=1, style=Qt.DashLine))
            vline.setVisible(False)
            hline.setVisible(False)
            pw.addItem(vline, ignoreBounds=True)
            pw.addItem(hline, ignoreBounds=True)
            self._crosshair_lines[pw] = (vline, hline)

            # Mouse tracking — rate-limited at 60fps for smooth crosshair
            proxy = pg.SignalProxy(pw.scene().sigMouseMoved,
                                   rateLimit=60,
                                   slot=lambda evt, _pw=pw: self._on_mouse_moved(evt, _pw))
            pw.setProperty('_mouse_proxy', proxy)

            # Visible-range change → debounced stats refresh + (optional) auto-fit Y.
            pw.getPlotItem().vb.sigRangeChanged.connect(self._on_view_range_changed)

            # _plot_widgets and _plot_groups already appended in lockstep
            # at the top of the iteration (right after addWidget(pw, r, c)).
            # Previous code re-appended to _plot_widgets and re-added the
            # widget via addWidget(pw) without grid coords here, which
            # duplicated entries and placed the second instance at grid
            # (0,0) on top of others — left in the prior commit as a
            # comment to flag the change; now fully removed.

            # Per-subplot context menu
            pw.setContextMenuPolicy(Qt.CustomContextMenu)
            pw.customContextMenuRequested.connect(
                lambda pos, _pw=pw: self._on_subplot_context_menu(pos, _pw))

        # NOTE: no addStretch() here — QGridLayout has no such method
        # (that's QBoxLayout). Subplots fill the grid cells; extra room
        # is distributed by Qt's grid policy. Calling addStretch() used
        # to crash _do_rebuild_plots whenever the user re-arranged params.

        # Reset row stretches from prior layout cycles
        for r in range(self._plot_layout.rowCount()):
            self._plot_layout.setRowStretch(r, 0)

        # Add a stretch factor to the row after the last subplot row to push them to the top
        if self._plot_widgets:
            from .plot_panel import GRID_LAYOUTS
            rows, cols = GRID_LAYOUTS.get(self._layout_combo.currentText(), (2, 1))
            last_row = (len(groups) - 1) // cols
            self._plot_layout.setRowStretch(last_row + 1, 1)

        self._restore_v_cursors()
        self._restore_h_cursors()
        self._update_cursor_dots()

        # Restore X range if it was saved and we have new plots
        if prev_x_range is not None and self._plot_widgets:
            try:
                self._plot_widgets[0].setXRange(prev_x_range[0], prev_x_range[1], padding=0)
            except Exception:
                pass

        # Trigger an initial stats compute on the freshly rendered subplots.
        self._stats_timer.start()
        # (wait cursor released by _rebuild_plots wrapper)

    # ------------------------------------------------------------------
    # Wall-clock / elapsed time toggle
    # ------------------------------------------------------------------
    def _best_epoch_offset(self) -> float | None:
        """Return the earliest start_timestamp among all loaded logs."""
        ts = [e.start_timestamp for e in self._logs.values()
              if e.start_timestamp is not None]
        return min(ts) if ts else None

    def _on_wallclock_toggled(self, on: bool):
        self._wall_clock_mode = bool(on)
        epoch = self._best_epoch_offset() if on else None
        for pw in self._plot_widgets:
            time_axis = pw.getAxis('bottom')
            if isinstance(time_axis, TimeAxisItem):
                time_axis.epoch_offset = epoch
        if self._plot_widgets:
            last_pw = self._plot_widgets[-1]
            if on and epoch is not None:
                last_pw.setLabel('bottom', 'Wall clock (HH:MM:SS)')
            else:
                last_pw.setLabel('bottom', 'Elapsed time (mm:ss)')

    # ------------------------------------------------------------------
    # Per-subplot context menu
    # ------------------------------------------------------------------
    def _on_subplot_context_menu(self, pos, pw: pg.PlotWidget):
        menu = QMenu(self)
        act_csv = menu.addAction("Export visible range as CSV\u2026")
        act_csv.triggered.connect(lambda: self._export_subplot_csv(pw))
        act_img = menu.addAction("Copy plot as image")
        act_img.triggered.connect(lambda: self._copy_subplot_image(pw))
        menu.exec(pw.mapToGlobal(pos))

    def _export_subplot_csv(self, pw: pg.PlotWidget):
        """Export this subplot's visible curves to CSV."""
        pi = self._plot_widgets.index(pw) if pw in self._plot_widgets else -1
        if pi < 0:
            return
        group = self._plot_groups[pi]
        try:
            x_range = tuple(pw.getPlotItem().vb.viewRange()[0])
        except Exception:
            x_range = None
        rows = []
        for param in group:
            for entry in self._logs.values():
                if param not in entry.columns or not entry.visible:
                    continue
                rows.append({
                    "curve": f"{entry.name} \u00b7 {param}",
                    "log_name": entry.name,
                    "param": param,
                    "x": entry.elapsed + entry.time_offset,
                    "y": entry.columns[param],
                    "x_range": x_range,
                })
        if not rows:
            self._popup_information("Nothing to Export",
                                    "No visible curves on this subplot.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Subplot Data", get_analysis_dir(), "CSV Files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        from PySide6.QtWidgets import QProgressDialog
        progress_dlg = QProgressDialog(
            "Preparing export...", "Cancel", 0, 100, self
        )
        progress_dlg.setWindowTitle("Exporting CSV")
        progress_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setAutoClose(True)
        progress_dlg.setAutoReset(True)
        progress_dlg.setValue(0)
        progress_dlg.show()

        thread = CSVExportThread(path, rows, 1, self)
        thread.sigProgress.connect(progress_dlg.setValue)

        def on_error(err_msg):
            progress_dlg.close()
            self._popup_warning("Export Failed", err_msg)

        def on_finished(out_path, total_rows_written):
            progress_dlg.close()
            self._status.showMessage(
                f"Exported subplot to {os.path.basename(out_path)}", 5000)

        thread.sigError.connect(on_error)
        thread.sigFinished.connect(on_finished)
        progress_dlg.canceled.connect(thread.requestInterruption)

        self._export_thread = thread
        thread.finished.connect(lambda: setattr(self, "_export_thread", None))
        thread.start()

    def _copy_subplot_image(self, pw: pg.PlotWidget):
        """Render the subplot to a QImage and copy to clipboard."""
        try:
            from pyqtgraph.exporters import ImageExporter
            exporter = ImageExporter(pw.getPlotItem())
            img = exporter.export(toBytes=True)
            from PySide6.QtGui import QPixmap
            QApplication.clipboard().setPixmap(QPixmap.fromImage(img))
            self._status.showMessage("Plot image copied to clipboard.", 4000)
        except Exception as exc:
            self._popup_warning("Copy Failed", str(exc))

    # ------------------------------------------------------------------
    # Checked parameters helper
    # ------------------------------------------------------------------
    def _get_checked_params(self) -> list[str]:
        """Return a flat list of all currently checked parameter names."""
        tree = self._param_tree
        params = []
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                params.append(item.text(0))
        return params

    # ------------------------------------------------------------------
    # Statistics + view-range hooks
    # ------------------------------------------------------------------
    def _on_view_range_changed(self, *args):
        # Debounce — sigRangeChanged fires continuously while panning/zooming.
        self._stats_timer.start()
        # If auto-fit Y is on, recompute y-range for every subplot from the
        # currently visible x-range.
        if getattr(self, "_auto_fit_y", False):
            QTimer.singleShot(0, self._apply_auto_fit_y)

    def _visible_curve_rows(self) -> list[dict]:
        """Collect one entry per currently-rendered (log, param) curve.
        Each entry carries the raw arrays + the current x-range so the
        stats panel (or a CSV exporter) can slice consistently."""
        rows: list[dict] = []
        if not self._plot_widgets:
            return rows
        for pi, pw in enumerate(self._plot_widgets):
            if pi >= len(self._plot_groups):
                continue
            group = self._plot_groups[pi]
            multi = len(group) > 1
            try:
                x_range = tuple(pw.getPlotItem().vb.viewRange()[0])
            except Exception:
                x_range = None
            for param in group:
                for entry in self._logs.values():
                    if param not in entry.columns:
                        continue
                    if not entry.visible:
                        continue
                    label = f"{entry.name} · {param}" if multi else f"{entry.name} · {param}"
                    rows.append({
                        "curve": label,
                        "log_id": entry.id,
                        "log_name": entry.name,
                        "param": param,
                        "color": entry.color,
                        "x": entry.elapsed + entry.time_offset,
                        "y": entry.columns[param],
                        "x_range": x_range,
                    })
        return rows

    def _refresh_stats_panel(self):
        self._stats_panel.update_stats(self._visible_curve_rows())

    # ──────────────────────────────────────────────────────────────────
    # Crosshair / mouse tracking
    # ──────────────────────────────────────────────────────────────────
    def _on_mouse_moved(self, evt, pw: pg.PlotWidget):
        try:
            self._on_mouse_moved_inner(evt, pw)
        except Exception:
            # At 60 fps, one bad event must not kill the crosshair permanently.
            pass

    def _on_mouse_moved_inner(self, evt, pw: pg.PlotWidget):
        pos = evt[0]
        if not pw.sceneBoundingRect().contains(pos):
            if pw in self._crosshair_lines:
                self._crosshair_lines[pw][0].setVisible(False)
                self._crosshair_lines[pw][1].setVisible(False)
            return

        mouse_point = pw.getPlotItem().vb.mapSceneToView(pos)
        t = mouse_point.x()
        v = mouse_point.y()

        # Track mouse position for H-cursor placement
        self._last_mouse_pw = pw
        self._last_mouse_pos = mouse_point

        if pw in self._crosshair_lines:
            vl, hl = self._crosshair_lines[pw]
            vl.setPos(t)
            hl.setPos(v)
            vl.setVisible(True)
            hl.setVisible(True)

        # Build tooltip
        pi = self._plot_widgets.index(pw) if pw in self._plot_widgets else -1
        # Defensive bounds-check on _plot_groups too. Normally the two
        # lists are appended atomically inside _do_rebuild_plots, but a
        # rate-limited mouse event can race with a teardown/rebuild
        # sequence (e.g. layout change while the user is hovering) where
        # _plot_widgets has already been cleared/repopulated but
        # _plot_groups is mid-clear. Bailing here is harmless — the next
        # event tick after rebuild completes shows the correct tooltip.
        if pi < 0 or pi >= len(self._plot_groups):
            return
        group = self._plot_groups[pi]
        multi = len(group) > 1
        parts = [f"t={t:.3f}s"]
        for param in group:
            for entry in self._logs.values():
                if not entry.visible or param not in entry.columns:
                    continue
                x = entry.elapsed + entry.time_offset
                if len(x) == 0:
                    continue
                idx = np.searchsorted(x, t)
                idx = min(idx, len(x) - 1)
                yv = entry.columns[param][idx]
                if not np.isnan(yv):
                    label = f"{entry.name} · {param}" if multi else entry.name
                    parts.append(f"{label}: {yv:.2f}")

        self._status.showMessage("  |  ".join(parts))

    # ──────────────────────────────────────────────────────────────────
    # Vertical cursors (global or single-plot)
    # ──────────────────────────────────────────────────────────────────
    def _resolve_vertical_cursor_anchor(self) -> tuple[Optional[pg.PlotWidget], float]:
        """Find the plot under the mouse and its X anchor position."""
        anchor_pw = None
        for pw in self._plot_widgets:
            if pw.underMouse():
                anchor_pw = pw
                break
        if anchor_pw is None and self._last_mouse_pw in self._plot_widgets:
            anchor_pw = self._last_mouse_pw
        if anchor_pw is None:
            anchor_pw = self._plot_widgets[0] if self._plot_widgets else None
        if anchor_pw is None:
            return None, 0.0

        if self._last_mouse_pos is not None and self._last_mouse_pw is anchor_pw:
            return anchor_pw, self._last_mouse_pos.x()

        vb = anchor_pw.getPlotItem().vb
        x_range = vb.viewRange()[0]
        return anchor_pw, (x_range[0] + x_range[1]) / 2.0

    def _plot_widget_for_param(self, plot_param: str) -> Optional[pg.PlotWidget]:
        """Return the current plot widget that contains the given parameter
        (may be a multi-param subplot)."""
        for idx, group in enumerate(self._plot_groups):
            if plot_param in group and idx < len(self._plot_widgets):
                return self._plot_widgets[idx]
        return None

    def _add_vertical_cursor(self, scope: str = 'all', time_value: Optional[float] = None,
                             plot_param: Optional[str] = None,
                             color: Optional[str] = None,
                             label_num: Optional[int] = None,
                             cursor_id: Optional[str] = None):
        if not self._plot_widgets:
            return

        anchor_pw, default_t = self._resolve_vertical_cursor_anchor()
        if anchor_pw is None:
            return
        t = default_t if time_value is None else time_value

        if label_num is None:
            self._v_cursor_counter += 1
            label_num = self._v_cursor_counter
        else:
            self._v_cursor_counter = max(self._v_cursor_counter, label_num)

        cid = cursor_id or uuid.uuid4().hex[:8]
        cursor_color = color or CURSOR_COLORS[(len(self._v_cursors)) % len(CURSOR_COLORS)]
        if scope == 'plot' and plot_param is None and anchor_pw in self._plot_widgets:
            group = self._plot_groups[self._plot_widgets.index(anchor_pw)]
            plot_param = group[0] if group else None

        if scope == 'plot':
            target_pw = self._plot_widget_for_param(plot_param) if plot_param else anchor_pw
            if target_pw is None:
                return
            target_plots = [target_pw]
        else:
            target_plots = list(self._plot_widgets)

        lines: dict[pg.PlotWidget, pg.InfiniteLine] = {}
        for pw in target_plots:
            line = pg.InfiniteLine(
                pos=t, angle=90, movable=True,
                pen=pg.mkPen(cursor_color, width=2),
                label=f'C{label_num}: {t:.2f}s',
                labelOpts={'position': 0.95, 'color': cursor_color,
                           'fill': THEME.c('cursor_label_bg'),
                           'movable': True})
            pw.addItem(line, ignoreBounds=True)
            line.sigPositionChanged.connect(
                lambda l, _cid=cid: self._on_v_cursor_moved(_cid, l))
            line.sigClicked.connect(
                lambda *a, _cid=cid: self._select_v_cursor(_cid))
            lines[pw] = line

        cursor_data = {
            'id': cid,
            'label': label_num,
            'scope': scope,
            'plot_param': plot_param,
            'lines': lines,
            'time': t,
            'color': cursor_color,
        }
        self._v_cursors.append(cursor_data)
        self._select_v_cursor(cid)
        self._update_cursor_dots()
        self._update_cursor_readout()

    def _add_plot_vertical_cursor(self):
        self._add_vertical_cursor(scope='plot')

    def _restore_v_cursors(self):
        """Re-add existing vertical cursor lines to newly rebuilt plots."""
        for cdata in self._v_cursors:
            cid = cdata['id']
            new_lines: dict[pg.PlotWidget, pg.InfiniteLine] = {}
            if cdata.get('scope') == 'plot':
                target_pw = self._plot_widget_for_param(cdata.get('plot_param'))
                target_plots = [target_pw] if target_pw is not None else []
            else:
                target_plots = list(self._plot_widgets)

            for pw in target_plots:
                line = pg.InfiniteLine(
                    pos=cdata['time'], angle=90, movable=True,
                    pen=pg.mkPen(cdata['color'], width=2),
                    label=f'C{cdata["label"]}: {cdata["time"]:.2f}s',
                    labelOpts={'position': 0.95, 'color': cdata['color'],
                               'fill': THEME.c('cursor_label_bg'),
                               'movable': True})
                pw.addItem(line, ignoreBounds=True)
                line.sigPositionChanged.connect(
                    lambda l, _cid=cid: self._on_v_cursor_moved(_cid, l))
                line.sigClicked.connect(
                    lambda *a, _cid=cid: self._select_v_cursor(_cid))
                new_lines[pw] = line
            cdata['lines'] = new_lines
        # Re-apply selected highlight
        if self._selected_v_cursor:
            self._select_v_cursor(self._selected_v_cursor)

    def _restore_h_cursors(self):
        """Re-add existing horizontal cursor lines to newly rebuilt plots."""
        for hc in self._h_cursors:
            hc['line'] = None
            hc['plot_widget'] = None

            pi = hc.get('plot_index', -1)
            if 0 <= pi < len(self._plot_widgets):
                pw = self._plot_widgets[pi]
                val = hc['value']
                color = hc['color']
                label_num = hc['label']
                cid = hc['id']
                line = pg.InfiniteLine(
                    pos=val, angle=0, movable=True,
                    pen=pg.mkPen(color, width=2, style=Qt.DashDotLine),
                    label=f'H{label_num}: {val:.2f}',
                    labelOpts={'position': 0.05, 'color': color,
                               'fill': THEME.c('cursor_label_bg'),
                               'movable': True})
                pw.addItem(line, ignoreBounds=True)

                line.sigPositionChanged.connect(
                    lambda l, _cid=cid: self._on_h_cursor_moved(_cid, l))
                line.sigClicked.connect(
                    lambda *a, _cid=cid: self._select_h_cursor(_cid))

                hc['line'] = line
                hc['plot_widget'] = pw

        # Re-apply selected highlight
        if self._selected_h_cursor:
            self._select_h_cursor(self._selected_h_cursor)

    def _on_v_cursor_moved(self, cursor_id: str, moved_line: pg.InfiniteLine):
        cdata = self._find_cursor_by_id(cursor_id)
        if cdata is None:
            return
        t = moved_line.value()
        cdata['time'] = t
        for _pw, line in cdata['lines'].items():
            if line is not moved_line:
                line.blockSignals(True)
                line.setValue(t)
                line.blockSignals(False)
            line.label.setText(f'C{cdata["label"]}: {t:.2f}s')
        self._select_v_cursor(cursor_id)
        self._update_cursor_dots_for_id(cursor_id)
        self._update_cursor_readout()

    def _find_cursor_by_id(self, cursor_id: str):
        """Return cursor data dict by ID, or None."""
        for cdata in self._v_cursors:
            if cdata.get('id') == cursor_id:
                return cdata
        return None

    def _select_v_cursor(self, cursor_id: str):
        """Mark cursor as selected (red pen), deselect others."""
        prev_id = self._selected_v_cursor
        self._selected_v_cursor = cursor_id
        # Restore previous cursor color
        if prev_id and prev_id != cursor_id:
            prev = self._find_cursor_by_id(prev_id)
            if prev:
                pen = pg.mkPen(prev['color'], width=2)
                for line in prev['lines'].values():
                    line.setPen(pen)
        # Highlight new selected cursor
        cur = self._find_cursor_by_id(cursor_id)
        if cur:
            sel_pen = pg.mkPen(SELECTED_CURSOR_COLOR, width=3)
            for line in cur['lines'].values():
                line.setPen(sel_pen)

    def _delete_v_cursor(self, cursor_id_or_index):
        """Delete a vertical cursor by ID string or list index (int)."""
        # Support being called with an index (from keyPressEvent)
        if isinstance(cursor_id_or_index, int):
            idx = cursor_id_or_index
            if idx < 0 or idx >= len(self._v_cursors):
                return
            cid = self._v_cursors[idx]['id']
        else:
            cid = cursor_id_or_index
        cdata = self._find_cursor_by_id(cid)
        if cdata is None:
            return
        self._v_cursors.remove(cdata)
        for pw, line in cdata['lines'].items():
            try:
                pw.removeItem(line)
            except Exception:
                pass
        # Remove tracking dots
        if cid in self._cursor_dots:
            for dot in self._cursor_dots.pop(cid):
                try:
                    target_vb = dot.get('vb', dot['pw'].getPlotItem().vb)
                    target_vb.removeItem(dot['item'])
                except Exception:
                    pass
        # Reset selection
        if self._selected_v_cursor == cid:
            self._selected_v_cursor = ''
        self._update_cursor_readout()

    def _update_cursor_readout(self):
        visible_logs = [e for e in self._logs.values() if e.visible]
        params = self._get_checked_params()
        # Enrich each V-cursor with the active params of the subplot it's
        # placed on (for plot-scoped cursors) or all checked params (for global ones).
        v_cursor_views: list[dict] = []
        for vc in self._v_cursors:
            if vc.get('scope') == 'plot':
                vc_params = []
                for pw in vc.get('lines', {}).keys():
                    pw_deleted = False
                    if hasattr(pw, 'parent'):
                        try:
                            pw.parent()
                        except RuntimeError:
                            pw_deleted = True
                    if not pw_deleted and pw in self._plot_widgets:
                        pi = self._plot_widgets.index(pw)
                        if 0 <= pi < len(self._plot_groups):
                            group = self._plot_groups[pi]
                            for p in group:
                                if p in params and p not in vc_params:
                                    vc_params.append(p)
            else:
                vc_params = params
            v_cursor_views.append({
                **vc,
                'params': vc_params,
            })

        # Enrich each H-cursor with the param list of the subplot it's
        # anchored on so the readout panel can render it with the same
        # "C1  t  [param] / ● log / param  value" structure as V-cursors.
        # The h_cursor dict itself carries only the plot_widget reference;
        # the param mapping lives on the AnalysisSuiteWindow.
        h_cursor_views: list[dict] = []
        for idx, hc in enumerate(self._h_cursors, start=1):
            pw = hc.get('plot_widget')
            group: list[str] = []
            pw_deleted = False
            if pw is not None:
                if hasattr(pw, 'parent'):
                    try:
                        pw.parent()
                    except RuntimeError:
                        pw_deleted = True
            if not pw_deleted and pw is not None and pw in self._plot_widgets:
                pi = self._plot_widgets.index(pw)
                if 0 <= pi < len(self._plot_groups):
                    group = list(self._plot_groups[pi])
            h_cursor_views.append({
                **hc,
                'label': hc.get('label', idx),
                'plot_group': group,
                'plot_widget_id': id(pw) if not pw_deleted else 0,
            })
        self._cursor_readout.update_readout(
            v_cursor_views, visible_logs, params,
            h_cursors=h_cursor_views,
        )

    def _update_cursor_dots(self):
        """Rebuild tracking dots for all cursors on all plots."""
        for _cid, dots in self._cursor_dots.items():
            for dot in dots:
                try:
                    target_vb = dot.get('vb', dot['pw'].getPlotItem().vb)
                    target_vb.removeItem(dot['item'])
                except Exception:
                    pass
        self._cursor_dots.clear()
        for cdata in self._v_cursors:
            self._update_cursor_dots_for_id(cdata['id'])

    def _update_cursor_dots_for_id(self, cursor_id: str):
        """Place small tracking dots where cursor intersects each curve."""
        cdata = self._find_cursor_by_id(cursor_id)
        if cdata is None:
            return
        # Remove old dots for this cursor
        if cursor_id in self._cursor_dots:
            for dot in self._cursor_dots[cursor_id]:
                try:
                    target_vb = dot.get('vb', dot['pw'].getPlotItem().vb)
                    target_vb.removeItem(dot['item'])
                except Exception:
                    pass
        dots = []
        t = cdata['time']
        log_list = list(self._logs.values())
        for pw in cdata['lines'].keys():
            if pw not in self._plot_widgets:
                continue
            pi = self._plot_widgets.index(pw)
            group = self._plot_groups[pi]

            # Determine left and right units
            left_unit = getattr(pw, 'left_unit', None)
            right_unit = getattr(pw, 'right_unit', None)

            for param in group:
                for li, entry in enumerate(log_list):
                    if not entry.visible or param not in entry.columns:
                        continue
                    x = entry.elapsed + entry.time_offset
                    if len(x) == 0:
                        continue
                    yv = float(np.interp(t, x, entry.columns[param]))
                    if np.isnan(yv):
                        continue
                    # Match the dot color to the actual curve color so the
                    # dot stays visually attached to its trace in multi-
                    # param subplots.
                    dot_color, _style = _curve_visuals(group, param, li, entry.color)
                    dot_item = pg.ScatterPlotItem(
                        [t], [yv], size=8,
                        pen=pg.mkPen(THEME.c('plot_bg'), width=1),
                        brush=pg.mkBrush(dot_color))

                    unit = self._extract_unit(param)
                    is_right = (hasattr(pw, 'right_vb') and pw.right_vb is not None and right_unit is not None and unit != left_unit)
                    target_vb = pw.right_vb if is_right else pw.getPlotItem().vb

                    target_vb.addItem(dot_item)
                    dots.append({'pw': pw, 'vb': target_vb, 'item': dot_item})
        self._cursor_dots[cursor_id] = dots

    # ──────────────────────────────────────────────────────────────────
    # Horizontal cursors (placed at mouse position)
    # ──────────────────────────────────────────────────────────────────
    def _add_horizontal_cursor_at_mouse(self):
        """Add h-cursor on the plot currently under the mouse, or last hovered."""
        # Check which plot the mouse is physically over right now
        pw = None
        for p in self._plot_widgets:
            if p.underMouse():
                pw = p
                break
        # Fall back to last tracked plot
        if pw is None and self._last_mouse_pw in self._plot_widgets:
            pw = self._last_mouse_pw
        if pw is None:
            if self._plot_widgets:
                pw = self._plot_widgets[0]
            else:
                return
        if self._last_mouse_pos is not None and self._last_mouse_pw is pw:
            val = self._last_mouse_pos.y()
        else:
            y_range = pw.getPlotItem().vb.viewRange()[1]
            val = (y_range[0] + y_range[1]) / 2.0

        label_num = len(self._h_cursors) + 1
        color = CURSOR_COLORS[(len(self._h_cursors) + 2) % len(CURSOR_COLORS)]
        cid = uuid.uuid4().hex[:8]
        line = pg.InfiniteLine(
            pos=val, angle=0, movable=True,
            pen=pg.mkPen(color, width=2, style=Qt.DashDotLine),
            label=f'H{label_num}: {val:.2f}',
            labelOpts={'position': 0.05, 'color': color,
                       'fill': THEME.c('cursor_label_bg'),
                       'movable': True})
        pw.addItem(line, ignoreBounds=True)

        pi = self._plot_widgets.index(pw) if pw in self._plot_widgets else -1

        hc = {
            'id': cid,
            'line': line,
            'plot_widget': pw,
            'plot_index': pi,
            'value': val,
            'color': color,
            'label': label_num,
        }
        self._h_cursors.append(hc)

        # On drag: keep the label fresh, keep the cached `value` in sync
        # with the line position, and refresh the readout so the bottom
        # panel always reflects the displayed Y.
        line.sigPositionChanged.connect(
            lambda l, _cid=cid: self._on_h_cursor_moved(_cid, l))
        line.sigClicked.connect(
            lambda *a, _cid=cid: self._select_h_cursor(_cid))

        self._select_h_cursor(cid)
        self._update_cursor_readout()

    def _find_h_cursor_by_id(self, cursor_id: str) -> Optional[dict]:
        for hc in self._h_cursors:
            if hc.get('id') == cursor_id:
                return hc
        return None

    def _on_h_cursor_moved(self, cursor_id: str, line: pg.InfiniteLine) -> None:
        """Sync the H-cursor's cached value + label + readout after a drag."""
        hc = self._find_h_cursor_by_id(cursor_id)
        if hc is None:
            return
        v = float(line.value())
        label_num = hc.get('label')
        label_txt = f'H{label_num}: {v:.2f}' if label_num else f'{v:.2f}'
        line.label.setText(label_txt)
        hc['value'] = v
        self._select_h_cursor(cursor_id)
        self._update_cursor_readout()

    def _select_h_cursor(self, cursor_id: str):
        """Mark h-cursor as selected (red pen), deselect others."""
        prev_id = self._selected_h_cursor
        self._selected_h_cursor = cursor_id
        # Restore previous cursor color
        if prev_id and prev_id != cursor_id:
            prev = self._find_h_cursor_by_id(prev_id)
            if prev and prev.get('line'):
                prev['line'].setPen(pg.mkPen(prev['color'], width=2, style=Qt.DashDotLine))
        # Highlight new selected cursor
        cur = self._find_h_cursor_by_id(cursor_id)
        if cur and cur.get('line'):
            cur['line'].setPen(
                pg.mkPen(SELECTED_CURSOR_COLOR, width=3, style=Qt.DashDotLine))

    def _delete_h_cursor(self, cursor_id: str):
        hc = self._find_h_cursor_by_id(cursor_id)
        if hc is None:
            return
        self._h_cursors.remove(hc)
        pw = hc.get('plot_widget')
        line = hc.get('line')
        pw_deleted = False
        if pw is not None:
            if hasattr(pw, 'parent'):
                try:
                    pw.parent()
                except RuntimeError:
                    pw_deleted = True
        if not pw_deleted and pw is not None and line is not None:
            try:
                pw.removeItem(line)
            except Exception:
                pass
        if self._selected_h_cursor == cursor_id:
            self._selected_h_cursor = ''
        self._update_cursor_readout()

    def _clear_all_cursors(self):
        # Vertical
        for cdata in self._v_cursors:
            for pw, line in cdata['lines'].items():
                try:
                    pw_deleted = False
                    if hasattr(pw, 'parent'):
                        try:
                            pw.parent()
                        except RuntimeError:
                            pw_deleted = True
                    if not pw_deleted and line is not None:
                        pw.removeItem(line)
                except Exception:
                    pass
        self._v_cursors.clear()
        self._selected_v_cursor = ''

        # Cursor dots
        for _cid, dots in self._cursor_dots.items():
            for dot in dots:
                try:
                    pw = dot['pw']
                    pw_deleted = False
                    if hasattr(pw, 'parent'):
                        try:
                            pw.parent()
                        except RuntimeError:
                            pw_deleted = True
                    item = dot['item']
                    if not pw_deleted and item is not None:
                        target_vb = dot.get('vb', pw.getPlotItem().vb)
                        target_vb.removeItem(item)
                except Exception:
                    pass
        self._cursor_dots.clear()

        # Horizontal
        for hc in self._h_cursors:
            try:
                pw = hc.get('plot_widget')
                pw_deleted = False
                if pw is not None:
                    if hasattr(pw, 'parent'):
                        try:
                            pw.parent()
                        except RuntimeError:
                            pw_deleted = True
                line = hc.get('line')
                if not pw_deleted and pw is not None and line is not None:
                    pw.removeItem(line)
            except Exception:
                pass
        self._h_cursors.clear()
        self._selected_h_cursor = ''

        self._update_cursor_readout()

    def _reset_zoom(self):
        for pw in self._plot_widgets:
            pw.autoRange()
            if hasattr(pw, 'right_vb') and pw.right_vb is not None:
                pw.right_vb.autoRange()

    def _set_plot_export_theme(self, pw: pg.PlotWidget, dark: bool = False):
        """Temporarily set plot to white bg + black axes for export."""
        pw.setBackground('w')
        fg = pg.mkPen('#000000')
        for ax_name in ('left', 'bottom', 'top', 'right'):
            ax = pw.getAxis(ax_name)
            ax.setPen(fg)
            ax.setTextPen(fg)

    def _restore_plot_theme(self, pw: pg.PlotWidget):
        """Restore plot to current theme colors."""
        pw.setBackground(THEME.c('plot_bg'))
        fg = pg.mkPen(THEME.c('plot_fg'))
        for ax_name in ('left', 'bottom', 'top', 'right'):
            ax = pw.getAxis(ax_name)
            ax.setPen(fg)
            ax.setTextPen(fg)

    # ──────────────────────────────────────────────────────────────────
    # Session save / load
    # ──────────────────────────────────────────────────────────────────
    def _save_session(self):
        folder = get_analysis_dir()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Analysis Session", folder,
            "Analysis Session (*.json)")
        if not path:
            return
        if not path.endswith('.json'):
            path += '.json'

        # Flatten currently checked params for the legacy 'parameters' key so
        # older app versions can still partially read this session.
        groups = self._get_subplot_groups()
        flat_checked: list[str] = []
        for g in groups:
            flat_checked.extend(g)

        data = {
            'version': SESSION_VERSION,
            'plot_height': self._plot_height,
            'logs': [],
            'parameters': flat_checked,
            # New in v4: full subplot layout (each subplot's param list) and
            # the user's persisted layout including unchecked params.
            'subplots': groups,
            'subplot_layout': self._subplot_layout,
            'cursors': {
                'vertical': [],
                'horizontal': [],
            }
        }

        for entry in self._logs.values():
            data['logs'].append({
                'path': entry.path,
                'color': entry.color,
                'visible': entry.visible,
                'time_offset': entry.time_offset,
            })

        for cdata in self._v_cursors:
            data['cursors']['vertical'].append({
                'time': cdata['time'],
                'color': cdata['color'],
                'label': cdata.get('label'),
                'scope': cdata.get('scope', 'all'),
                'plot_param': cdata.get('plot_param'),
            })

        for hi, hc in enumerate(self._h_cursors, start=1):
            pi = hc.get('plot_index', -1)
            pw = hc.get('plot_widget')
            pw_deleted = False
            if pw is not None:
                if hasattr(pw, 'parent'):
                    try:
                        pw.parent()
                    except RuntimeError:
                        pw_deleted = True
            if not pw_deleted and pw is not None and pw in self._plot_widgets:
                pi = self._plot_widgets.index(pw)

            val = hc['value']
            line = hc.get('line')
            if line is not None:
                try:
                    val = line.value()
                except (RuntimeError, AttributeError):
                    pass

            data['cursors']['horizontal'].append({
                'plot_index': pi,
                'value': val,
                'color': hc['color'],
                'label': hc.get('label', hi),
            })

        if self._plot_widgets:
            x_range = self._plot_widgets[0].getPlotItem().vb.viewRange()[0]
            data['view_range'] = {'x': x_range}

        self._status.showMessage("Saving session...", 3000)
        self._save_thread = SessionSaveThread(path, data, self)
        self._save_thread.sigFinished.connect(
            lambda out_path: self._status.showMessage(f"Session saved to {os.path.basename(out_path)}", 5000)
        )
        self._save_thread.sigError.connect(
            lambda err: self._popup_warning("Save Error", err)
        )
        self._save_thread.finished.connect(lambda: setattr(self, "_save_thread", None))
        self._save_thread.start()

    def _load_session(self):
        folder = get_analysis_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Analysis Session", folder,
            "Analysis Session (*.json)")
        if not path:
            return

        self._status.showMessage("Loading session...", 3000)
        self._load_thread = SessionLoadThread(path, self)
        self._load_thread.sigFinished.connect(self._on_session_data_loaded)
        self._load_thread.sigError.connect(
            lambda err: self._popup_warning("Load Error", err)
        )
        self._load_thread.finished.connect(lambda: setattr(self, "_load_thread", None))
        self._load_thread.start()

    def _on_session_data_loaded(self, data: dict):
        ver = data.get('version', 0)
        if ver not in (1, 2, 3, 4):
            self._popup_warning("Version Mismatch", "Session file version not supported.")
            return

        # Clear current state
        self._clear_all_cursors()
        log_ids = list(self._logs.keys())
        for lid in log_ids:
            self._remove_log(lid)

        # Restore plot height
        ph = data.get('plot_height', DEFAULT_PLOT_HEIGHT)
        self._plot_height = max(MIN_PLOT_HEIGHT, min(MAX_PLOT_HEIGHT, ph))
        # _height_slider removed in grid-layout refactor; skip silently.
        if hasattr(self, "_height_slider"):
            self._height_slider.setValue(self._plot_height)

        session_params = set(data.get('parameters', []))
        # v4+ stores the layout; older versions only stored flat 'parameters'.
        session_subplot_layout = data.get('subplot_layout')
        if session_subplot_layout is None:
            session_subplots = data.get('subplots')
            if session_subplots is not None:
                session_subplot_layout = session_subplots
            else:
                # v1-v3 fallback: each checked param gets its own subplot.
                session_subplot_layout = [[p] for p in data.get('parameters', [])]

        pending_logs = data.get('logs', [])
        self._pending_session = {
            'params': session_params,
            'subplot_layout': session_subplot_layout,
            'cursors': data.get('cursors', {}),
            'view_range': data.get('view_range'),
            'remaining': len(pending_logs),
        }

        for log_info in pending_logs:
            log_path = log_info['path']
            if not os.path.isfile(log_path):
                self._status.showMessage(f"File not found: {log_path}", 5000)
                self._pending_session['remaining'] -= 1
                continue
            log_id = uuid.uuid4().hex[:8]
            color = log_info.get('color', self._next_color())
            thread = LogLoaderThread(log_path, log_id, color, self)
            thread.sigFinished.connect(
                lambda lid, p, e, info=log_info: self._on_session_log_loaded(lid, p, e, info))
            thread.error.connect(self._on_load_error)
            thread.finished.connect(lambda t=thread: self._cleanup_thread(t))
            self._loader_threads.append(thread)
            thread.start()

    def _on_session_log_loaded(self, log_id, path, entry, log_info):
        entry.color = log_info.get('color', entry.color)
        entry.visible = log_info.get('visible', True)
        entry.time_offset = log_info.get('time_offset', 0.0)

        self._logs[log_id] = entry
        self._add_log_to_sidebar(entry)

        # Update checkbox and offset spinbox from restored UI
        ui = self._log_entries_ui.get(log_id)
        if ui:
            if not entry.visible:
                ui['checkbox'].setChecked(False)
            ui['spin'].setValue(entry.time_offset)

        self._pending_session['remaining'] -= 1
        if self._pending_session['remaining'] <= 0:
            self._finish_session_restore()

    def _finish_session_restore(self):
        session = self._pending_session

        # Restore the persisted subplot layout BEFORE rebuilding, so the tree
        # comes back with the same grouping the user saved.
        self._subplot_layout = [list(g) for g in session.get('subplot_layout', [])]
        self._rebuild_param_list()

        # Apply checked state from the flat 'parameters' list.
        self._param_tree.blockSignals(True)
        for i in range(self._param_tree.topLevelItemCount()):
            top = self._param_tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                child.setCheckState(
                    0,
                    Qt.Checked if child.text(0) in session['params']
                    else Qt.Unchecked,
                )
        self._param_tree.blockSignals(False)

        self._rebuild_plots()

        # Restore cursors
        cursors = session.get('cursors', {})
        for vc in cursors.get('vertical', []):
            self._add_vertical_cursor(
                scope=vc.get('scope', 'all'),
                time_value=vc.get('time', 0),
                plot_param=vc.get('plot_param'),
                color=vc.get('color'),
                label_num=vc.get('label'),
            )

        for hc_data in cursors.get('horizontal', []):
            pi = hc_data.get('plot_index', 0)
            if 0 <= pi < len(self._plot_widgets):
                pw = self._plot_widgets[pi]
                val = hc_data.get('value', 0)
                color = hc_data.get('color', '#e63946')
                label_num = hc_data.get('label', len(self._h_cursors) + 1)
                cid = uuid.uuid4().hex[:8]
                line = pg.InfiniteLine(
                    pos=val, angle=0, movable=True,
                    pen=pg.mkPen(color, width=2, style=Qt.DashDotLine),
                    label=f'H{label_num}: {val:.2f}',
                    labelOpts={'position': 0.05, 'color': color,
                               'fill': THEME.c('cursor_label_bg'),
                               'movable': True})
                pw.addItem(line, ignoreBounds=True)

                line.sigPositionChanged.connect(
                    lambda l, _cid=cid: self._on_h_cursor_moved(_cid, l))
                line.sigClicked.connect(
                    lambda *a, _cid=cid: self._select_h_cursor(_cid))

                self._h_cursors.append({
                    'id': cid,
                    'line': line,
                    'plot_widget': pw,
                    'plot_index': pi,
                    'value': val,
                    'color': color,
                    'label': label_num,
                })

        # Restore view range
        vr = session.get('view_range')
        if vr and self._plot_widgets:
            x = vr.get('x')
            if x and len(x) == 2:
                self._plot_widgets[0].setXRange(x[0], x[1], padding=0)

        self._update_cursor_dots()
        self._update_cursor_readout()
        self._pending_session = None
        self._status.showMessage("Session restored.", 5000)

    # ──────────────────────────────────────────────────────────────────
    # Utility actions
    # ──────────────────────────────────────────────────────────────────
    def _open_datalogs_folder(self):
        d = get_datalogs_dir()
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
        except Exception as exc:
            self._popup_warning("Open Folder", f"Could not open:\n{d}\n\n{exc}")

    def _open_analysis_folder(self):
        d = get_analysis_dir()
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
        except Exception as exc:
            self._popup_warning("Open Folder", f"Could not open:\n{d}\n\n{exc}")

    def _open_xy_plotter(self):
        if self._xy_window is not None and self._xy_window.isVisible():
            self._xy_window.raise_()
            self._xy_window.activateWindow()
            return
        # parent=None so the window can freely go behind other windows
        self._xy_window = XYPlotWindow(self._logs)
        self._xy_window.show()

    # ──────────────────────────────────────────────────────────────────
    # Export
    # ──────────────────────────────────────────────────────────────────
    def _export_image(self):
        if not self._plot_widgets:
            self._popup_information("Export", "No plots to export.")
            return
        path, filt = QFileDialog.getSaveFileName(
            self, "Export Plots as Image", get_analysis_dir(),
            "PNG Image (*.png);;SVG Vector (*.svg)")
        if not path:
            return
        self._do_export(path, filt)

    def _export_pdf(self):
        if not self._plot_widgets:
            self._popup_information("Export", "No plots to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plots as PDF", get_analysis_dir(),
            "PDF Document (*.pdf)")
        if not path:
            return
        if not path.lower().endswith('.pdf'):
            path += '.pdf'
        self._do_export(path, "PDF")

    def _do_export(self, path: str, filt: str):
        try:
            from pyqtgraph.exporters import ImageExporter

            if filt and "SVG" in filt:
                from pyqtgraph.exporters import SVGExporter
                for i, pw in enumerate(self._plot_widgets):
                    suffix = "_".join(self._plot_groups[i]) if i < len(self._plot_groups) else str(i)
                    # Strip any path separators a parameter name might contain.
                    suffix = re.sub(r'[\\/:*?"<>|]', '_', suffix)
                    p = path if len(self._plot_widgets) == 1 else \
                        path.replace('.svg', f'_{suffix}.svg')
                    exporter = SVGExporter(pw.getPlotItem())
                    exporter.export(p)
                self._status.showMessage(f"Exported SVG to {os.path.dirname(path)}", 5000)
                return

            # Grab plot images on the UI thread since rendering must touch the GUI
            plot_images = []
            if filt and "PDF" in filt or path.lower().endswith('.pdf'):
                mode = "PDF"
                export_width = 1600
                for pw in self._plot_widgets:
                    self._set_plot_export_theme(pw, dark=False)
                    exporter = ImageExporter(pw.getPlotItem())
                    exporter.parameters()['width'] = export_width
                    exporter.parameters()['background'] = pg.mkColor('w')
                    img = exporter.export(toBytes=True)
                    self._restore_plot_theme(pw)
                    plot_images.append(img)
            else:
                mode = "PNG"
                for pw in self._plot_widgets:
                    exporter = ImageExporter(pw.getPlotItem())
                    img = exporter.export(toBytes=True)
                    plot_images.append(img)

            # Start background thread to stitch, format, and save the images
            self._status.showMessage("Exporting...", 3000)
            self._export_thread = PlotImageExportThread(
                path, mode, plot_images, THEME.c('plot_bg'), self
            )
            self._export_thread.sigFinished.connect(
                lambda out_path: self._status.showMessage(
                    f"Exported {mode} to {os.path.basename(out_path)}", 5000
                )
            )
            self._export_thread.sigError.connect(
                lambda err: self._popup_warning("Export Error", err)
            )
            self._export_thread.finished.connect(lambda: setattr(self, "_export_thread", None))
            self._export_thread.start()

        except Exception as exc:
            self._popup_warning("Export Error", str(exc))

    # ──────────────────────────────────────────────────────────────────
    # Cleanup & persistence
    # ──────────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        # Stop debounce timer FIRST so it can't fire during teardown.
        self._stats_timer.stop()
        # Persist UI state
        try:
            qs = self._qsettings
            qs.setValue("analysis/plot_height", self._plot_height)
            if self._plot_widgets:
                x_range = self._plot_widgets[0].getPlotItem().vb.viewRange()[0]
                qs.setValue("analysis/x_range", x_range)
            cursor_times = [c['time'] for c in self._v_cursors]
            qs.setValue("analysis/cursor_positions", cursor_times)
        except Exception:
            pass
        for t in self._loader_threads:
            try:
                t.sigFinished.disconnect()
                t.error.disconnect()
                t.finished.disconnect()
            except Exception:
                pass
            t.quit()
            t.wait(500)
        self._loader_threads.clear()
        super().closeEvent(event)
