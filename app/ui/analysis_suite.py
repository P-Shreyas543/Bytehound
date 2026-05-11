"""Analysis Suite — Multi-log comparison tool with overlay plots.

Launched from the Data menu as a non-modal QMainWindow.  All Excel loading
runs in a QThread so the live test is never blocked.  Plots use OpenGL
acceleration via pyqtgraph for lag-free pan/zoom even with many data points.
"""
import csv
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from openpyxl import load_workbook
from PySide6.QtCore import QThread, Qt, Signal, QPointF, QObject
from PySide6.QtGui import (
    QAction, QColor, QFont, QKeySequence, QPainter, QPen,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpinBox, QSplitter,
    QStatusBar, QToolBar, QVBoxLayout, QWidget,
)

# ═══════════════════════════════════════════════════════════════════════
# Stubs to replace missing dependencies
# ═══════════════════════════════════════════════════════════════════════
APP_NAME = "Bytehound"

def get_datalogs_dir() -> str:
    path = Path.home() / "Documents" / APP_NAME / "Logs"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)

def get_analysis_dir() -> str:
    path = Path.home() / "Documents" / APP_NAME / "Analysis"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)

class _DummyTheme(QObject):
    theme_changed = Signal(str)
    def c(self, key: str) -> str:
        colors = {
            'plot_bg': '#1e1e1e',
            'plot_fg': '#ffffff',
            'crosshair': '#aaaaaa',
            'cursor_label_bg': '#333333'
        }
        return colors.get(key, '#ffffff')
    def plot_grid_alpha(self) -> float:
        return 0.3

THEME = _DummyTheme()

# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════
LOG_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#17becf', '#bcbd22',
    '#ff9896', '#98df8a', '#c5b0d5', '#393b79',
]

CURSOR_COLORS = ['#e63946', '#457b9d', '#2a9d8f', '#f4a261', '#6a4c93']
SELECTED_CURSOR_COLOR = '#ff0000'

DEFAULT_PARAMS = [
    "Vehicle Speed (Kmph)", "Dyno Act Torque (Nm)",
    "Vehicle Power (W)", "Roller Speed (RPM)",
]

SESSION_VERSION = 3
MIN_PLOT_HEIGHT = 80
MAX_PLOT_HEIGHT = 600
DEFAULT_PLOT_HEIGHT = 200


# ═══════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class LogEntry:
    """One loaded test-log file."""
    id: str = ""
    path: str = ""
    name: str = ""
    color: str = "#1f77b4"
    visible: bool = True
    time_offset: float = 0.0
    elapsed: np.ndarray = field(default_factory=lambda: np.zeros(0))
    columns: dict[str, np.ndarray] = field(default_factory=dict)

    def available_params(self) -> list[str]:
        return [name for name in self.columns.keys() if not _is_time_like_param(name)]


def _is_time_like_param(name: str) -> bool:
    """Return True for columns that represent time axes rather than data."""
    norm = re.sub(r'\s+', ' ', (name or '').strip().lower())
    if norm in {
        '', 'time', 'timestamp', 'elapsed', 'elapsed (s)', 'time (s)',
        'elapsed time', 'elapsed time (s)',
    }:
        return True
    return norm.startswith('timestamp ') or norm.startswith('elapsed ')


def _test_name_from_path(path: str) -> str:
    """Extract a human-readable test name from the log filename."""
    base = os.path.splitext(os.path.basename(path))[0]
    # Strip DynoLog_ prefix and _YYYYMMDD_HHMMSS suffix
    base = re.sub(r'^DynoLog_', '', base)
    base = re.sub(r'_\d{8}_\d{6}$', '', base)
    return base or os.path.basename(path)


# ═══════════════════════════════════════════════════════════════════════
# Background loader thread
# ═══════════════════════════════════════════════════════════════════════
class LogLoaderThread(QThread):
    """Loads one .xlsx or _decoded.csv log file in a background thread."""
    log_loaded = Signal(str, str, object)   # (log_id, path, LogEntry or None)
    error = Signal(str, str)                # (path, error_message)

    def __init__(self, path: str, log_id: str, color: str, parent=None):
        super().__init__(parent)
        self._path = path
        self._log_id = log_id
        self._color = color

    def run(self):
        try:
            ext = os.path.splitext(self._path)[1].lower()
            if ext == ".csv":
                self._load_csv()
            else:
                self._load_xlsx()
        except Exception as exc:
            self.error.emit(self._path, str(exc))

    def _load_csv(self):
        """Parse a _decoded.csv file produced by DecodedLogger."""
        with open(self._path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            rows = list(reader)

        if not fieldnames:
            self.error.emit(self._path, "CSV header row is missing.")
            return
        if not rows:
            self.error.emit(self._path, "No data rows found in CSV.")
            return

        data_columns = [
            name for name in fieldnames
            if name and name not in {"timestamp", "elapsed_ms"}
        ]
        if not data_columns:
            self.error.emit(self._path, "No data columns found in CSV.")
            return

        import datetime as dt
        first_ts = None
        col_data: dict[str, list[tuple[float, float]]] = {name: [] for name in data_columns}

        for row in rows:
            elapsed_s: float | None = None
            elapsed_raw = row.get("elapsed_ms", "")
            if elapsed_raw is not None and str(elapsed_raw).strip() != "":
                try:
                    elapsed_s = float(elapsed_raw) / 1000.0
                except ValueError:
                    elapsed_s = None

            if elapsed_s is None:
                ts_str = row.get("timestamp", "")
                try:
                    ts = dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    try:
                        ts = dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        ts = None
                if first_ts is None and ts is not None:
                    first_ts = ts
                elapsed_s = (ts - first_ts).total_seconds() if (ts and first_ts) else 0.0

            for label in data_columns:
                cell = row.get(label, "")
                if cell is None or str(cell).strip() == "":
                    continue
                try:
                    value = float(cell)
                except (ValueError, TypeError):
                    continue
                col_data[label].append((elapsed_s, value))

        col_data = {label: pairs for label, pairs in col_data.items() if pairs}
        if not col_data:
            self.error.emit(self._path, "No numeric columns found in CSV.")
            return

        # Build unified time axis (union of all timestamps, sorted)
        all_times = sorted({t for times in col_data.values() for t, _ in times})
        n = len(all_times)
        time_idx = {t: i for i, t in enumerate(all_times)}
        elapsed_arr = np.array(all_times)

        columns: dict[str, np.ndarray] = {}
        for label, pairs in col_data.items():
            arr = np.full(n, np.nan)
            for t, v in pairs:
                arr[time_idx[t]] = v
            columns[label] = arr

        entry = LogEntry(
            id=self._log_id,
            path=self._path,
            name=_test_name_from_path(self._path),
            color=self._color,
            elapsed=elapsed_arr,
            columns=columns,
        )
        self.log_loaded.emit(self._log_id, self._path, entry)

    def _load_xlsx(self):
        """Parse a .xlsx file (Dyno or exported Excel log)."""
        from openpyxl import load_workbook
        wb = load_workbook(self._path, read_only=True, data_only=True)
        # Prefer 'Record' sheet (new format), fall back to active
        if 'Record' in wb.sheetnames:
            ws = wb['Record']
        else:
            ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if len(rows) < 2:
            self.error.emit(self._path, "No data rows found.")
            return

        headers = [str(c) if c else "" for c in rows[0]]
        data_rows = rows[1:]

        # Find elapsed-time column
        elapsed_idx = -1
        for i, h in enumerate(headers):
            if h == "Elapsed (s)":
                elapsed_idx = i
                break

        n = len(data_rows)
        elapsed = np.zeros(n)
        columns: dict[str, np.ndarray] = {}

        # Identify numeric data columns (skip axis/time-like fields)
        col_map: dict[int, str] = {}
        for i, h in enumerate(headers):
            if not _is_time_like_param(h):
                col_map[i] = h
                columns[h] = np.full(n, np.nan)

        for r, row in enumerate(data_rows):
            if elapsed_idx >= 0 and elapsed_idx < len(row):
                try:
                    elapsed[r] = float(row[elapsed_idx])
                except (ValueError, TypeError):
                    elapsed[r] = elapsed[r - 1] if r > 0 else 0.0
            for ci, param in col_map.items():
                if ci < len(row) and row[ci] is not None:
                    try:
                        columns[param][r] = float(row[ci])
                    except (ValueError, TypeError):
                        pass

        entry = LogEntry(
            id=self._log_id,
            path=self._path,
            name=_test_name_from_path(self._path),
            color=self._color,
            elapsed=elapsed,
            columns=columns,
        )
        self.log_loaded.emit(self._log_id, self._path, entry)



# ═══════════════════════════════════════════════════════════════════════
# Cursor readout widget
# ═══════════════════════════════════════════════════════════════════════
class CursorReadoutPanel(QGroupBox):
    """Displays interpolated values at vertical cursor positions.

    Each parameter value is on its own line for readability.
    """

    def __init__(self, parent=None):
        super().__init__("Cursor Readout", parent)
        self.setMinimumWidth(200)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(1)
        self._scroll.setWidget(self._inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.addWidget(self._scroll)

        self._delta_label = QLabel("")
        self._delta_label.setFont(QFont("PT Sans", 9, QFont.Bold))
        self._layout.addWidget(self._delta_label)
        self._info_label = QLabel("Add cursors with V / Shift+V / H keys.")
        self._info_label.setFont(QFont("PT Sans", 8))
        self._info_label.setWordWrap(True)
        self._layout.addWidget(self._info_label)
        self._layout.addStretch()

    def update_readout(self, cursors: list[dict],
                       logs: list['LogEntry'],
                       active_params: list[str]):
        vbar = self._scroll.verticalScrollBar()
        old_scroll = vbar.value()

        # Clear dynamic labels (keep delta + info + stretch)
        while self._layout.count() > 3:
            item = self._layout.takeAt(2)
            w = item.widget() if item else None
            if w:
                w.deleteLater()

        if not cursors:
            self._delta_label.setText("")
            self._info_label.setText("Add cursors with V / Shift+V / H keys.")
            vbar.setValue(min(old_scroll, vbar.maximum()))
            return

        self._info_label.setText("")
        if len(cursors) >= 2:
            dt = abs(cursors[1]['time'] - cursors[0]['time'])
            self._delta_label.setText(f"\u0394t = {dt:.3f} s")
        else:
            self._delta_label.setText(f"t = {cursors[0]['time']:.3f} s")

        for cursor in cursors:
            t = cursor['time']
            label_num = cursor.get('label', 0)
            scope = cursor.get('scope', 'all')
            plot_param = cursor.get('plot_param')
            hdr_txt = f"C{label_num}  t = {t:.3f} s"
            if scope == 'plot' and plot_param:
                hdr_txt += f"  [{plot_param}]"
            hdr = QLabel(hdr_txt)
            hdr.setFont(QFont("PT Sans", 8, QFont.Bold))
            self._layout.insertWidget(self._layout.count() - 1, hdr)

            if scope == 'plot' and plot_param:
                params_for_cursor = [plot_param]
            else:
                params_for_cursor = active_params

            for log in logs:
                if not log.visible or len(log.elapsed) == 0:
                    continue
                x = log.elapsed + log.time_offset
                name_lbl = QLabel(f"  {log.name}:")
                name_lbl.setFont(QFont("PT Sans", 8, QFont.Bold))
                name_lbl.setStyleSheet(f"color: {log.color};")
                self._layout.insertWidget(self._layout.count() - 1, name_lbl)
                for param in params_for_cursor:
                    if param not in log.columns:
                        continue
                    idx = int(np.clip(np.searchsorted(x, t), 0, len(x) - 1))
                    v = log.columns[param][idx]
                    short = param.split('(')[0].strip()
                    unit = ""
                    m = re.search(r'\(([^)]+)\)', param)
                    if m:
                        unit = m.group(1)
                    if not np.isnan(v):
                        val_txt = f"    {short}: {v:.2f} {unit}"
                    else:
                        val_txt = f"    {short}: \u2014"
                    lbl = QLabel(val_txt)
                    lbl.setFont(QFont("PT Sans", 8))
                    self._layout.insertWidget(self._layout.count() - 1, lbl)

        vbar.setValue(min(old_scroll, vbar.maximum()))


# ═══════════════════════════════════════════════════════════════════════
# X-Y Scatter Plot Window
# ═══════════════════════════════════════════════════════════════════════
# Symbol name → pyqtgraph symbol string
_XY_SYMBOLS = [
    ('Circle (outline)', 'o'),
    ('Circle (filled)', 'o'),
    ('Square', 's'),
    ('Triangle', 't'),
    ('Diamond', 'd'),
    ('Cross', '+'),
]


class XYPlotWindow(QDialog):
    """Scatter / X-Y plot window for cross-parameter analysis."""

    def __init__(self, logs: dict[str, LogEntry], parent=None):
        super().__init__(parent)
        # Qt.Window: independent z-order (not an owned always-on-top window)
        self.setWindowFlag(Qt.Window)
        self.setWindowTitle(f"X-Y Plotter — {APP_NAME}")
        self.resize(900, 700)
        self.setMinimumSize(600, 400)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._logs = logs
        self._curves: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # ── Row 1: axis selectors ─────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("X-Axis:"))
        self._x_combo = QComboBox()
        self._x_combo.setMinimumWidth(160)
        ctrl.addWidget(self._x_combo)
        ctrl.addWidget(QLabel("Y-Axis:"))
        self._y_combo = QComboBox()
        self._y_combo.setMinimumWidth(160)
        ctrl.addWidget(self._y_combo)
        ctrl.addSpacing(12)

        # ── Symbol style ─────────────────────────────────────────
        ctrl.addWidget(QLabel("Symbol:"))
        self._sym_combo = QComboBox()
        for name, _ in _XY_SYMBOLS:
            self._sym_combo.addItem(name)
        self._sym_combo.setCurrentIndex(1)  # filled circle default
        ctrl.addWidget(self._sym_combo)
        ctrl.addSpacing(8)

        # ── Symbol size ──────────────────────────────────────────
        ctrl.addWidget(QLabel("Size:"))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(2, 30)
        self._size_spin.setValue(6)
        self._size_spin.setFixedWidth(55)
        ctrl.addWidget(self._size_spin)
        ctrl.addSpacing(12)

        btn_plot = QPushButton("Plot")
        btn_plot.clicked.connect(self._do_plot)
        ctrl.addWidget(btn_plot)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_plot)
        ctrl.addWidget(btn_clear)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # ── Populate combos ───────────────────────────────────────
        all_params: list[str] = []
        seen = set()
        for entry in self._logs.values():
            for p in entry.available_params():
                if p not in seen:
                    seen.add(p)
                    all_params.append(p)
        self._x_combo.addItems(all_params)
        self._y_combo.addItems(all_params)
        if len(all_params) >= 2:
            self._x_combo.setCurrentIndex(0)
            self._y_combo.setCurrentIndex(1)

        # ── Plot widget ───────────────────────────────────────────
        self._plot = pg.PlotWidget()
        bg = THEME.c('plot_bg')
        fg = THEME.c('plot_fg')
        self._plot.setBackground(bg)
        self._plot.showGrid(x=True, y=True, alpha=THEME.plot_grid_alpha())
        for ax_name in ('left', 'bottom'):
            ax = self._plot.getAxis(ax_name)
            pen = pg.mkPen(fg)
            ax.setPen(pen)
            ax.setTextPen(pen)
        self._legend = self._plot.addLegend(offset=(10, 10))
        layout.addWidget(self._plot)

    def _do_plot(self):
        x_param = self._x_combo.currentText()
        y_param = self._y_combo.currentText()
        if not x_param or not y_param:
            return
        self._plot.setLabel('bottom', x_param)
        self._plot.setLabel('left', y_param)

        sym_idx = self._sym_combo.currentIndex()
        sym_str = _XY_SYMBOLS[sym_idx][1]
        size = self._size_spin.value()
        # Outline vs filled: outline uses mkPen with color, filled uses no pen
        filled = (self._sym_combo.currentText().lower().find('filled') >= 0
                  or self._sym_combo.currentIndex() == 1)

        for entry in self._logs.values():
            if not entry.visible:
                continue
            if x_param not in entry.columns or y_param not in entry.columns:
                continue
            x = entry.columns[x_param]
            y = entry.columns[y_param]
            mask = ~(np.isnan(x) | np.isnan(y))
            pen = pg.mkPen(None) if filled else pg.mkPen(entry.color, width=1)
            brush = pg.mkBrush(entry.color) if filled else pg.mkBrush(None)
            scatter = pg.ScatterPlotItem(
                x=x[mask], y=y[mask],
                pen=pen, brush=brush,
                symbol=sym_str, size=size,
                name=entry.name)
            self._plot.addItem(scatter)
            self._curves.append(scatter)

    def _clear_plot(self):
        for c in self._curves:
            self._plot.removeItem(c)
        self._curves.clear()


# ═══════════════════════════════════════════════════════════════════════
# Main analysis window
# ═══════════════════════════════════════════════════════════════════════
class AnalysisSuiteWindow(QMainWindow):
    """Multi-log comparison analysis tool."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Analysis Suite — {APP_NAME}")
        self.resize(1500, 900)
        self.setMinimumSize(900, 600)

        self._logs: dict[str, LogEntry] = {}
        self._color_index = 0
        self._loader_threads: list[LogLoaderThread] = []

        # Plot management
        self._plot_widgets: list[pg.PlotWidget] = []
        self._plot_params: list[str] = []
        self._curves: dict[str, dict[str, pg.PlotDataItem]] = {}
        self._v_cursors: list[dict] = []
        self._h_cursors: list[dict] = []
        self._crosshair_lines: dict[pg.PlotWidget, tuple] = {}
        self._selected_v_cursor: str = ''   # cursor ID string, '' = none
        self._selected_h_cursor: int = -1
        self._cursor_dots: dict[str, list] = {}   # cursor_id → [{'pw', 'item'}]
        self._v_cursor_counter: int = 0          # ever-increasing label counter
        self._xy_window = None                   # keep reference to non-modal XY window
        self._plot_height = DEFAULT_PLOT_HEIGHT
        self._last_mouse_pw: Optional[pg.PlotWidget] = None
        self._last_mouse_pos: Optional[QPointF] = None

        # Log sidebar UI elements
        self._log_entries_ui: dict[str, dict] = {}  # log_id → {checkbox, spin, container, ...}

        self._build_ui()
        self._build_menus()
        self._apply_theme()
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
        QMessageBox.information(self, title, message)

    def _popup_warning(self, title: str, message: str) -> None:
        self._log_popup("WARN", title, message)
        QMessageBox.warning(self, title, message)

    # ──────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(4, 4, 4, 4)

        # ── Left sidebar ─────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setMaximumWidth(320)
        sidebar.setMinimumWidth(240)
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

        # Plot height slider
        height_row = QHBoxLayout()
        height_row.addWidget(QLabel("Plot Height:"))
        self._height_slider = QSlider(Qt.Horizontal)
        self._height_slider.setRange(MIN_PLOT_HEIGHT, MAX_PLOT_HEIGHT)
        self._height_slider.setValue(DEFAULT_PLOT_HEIGHT)
        self._height_slider.valueChanged.connect(self._on_plot_height_changed)
        height_row.addWidget(self._height_slider)
        self._height_label = QLabel(f"{DEFAULT_PLOT_HEIGHT}px")
        self._height_label.setMinimumWidth(40)
        height_row.addWidget(self._height_label)
        side_layout.addLayout(height_row)

        # Parameter selector group — pushed to bottom
        param_group = QGroupBox("Parameters (Subplots)")
        param_layout = QVBoxLayout(param_group)
        param_layout.setContentsMargins(4, 12, 4, 4)

        p_btn_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(lambda: self._set_all_params(True))
        p_btn_row.addWidget(btn_all)
        btn_none = QPushButton("Deselect All")
        btn_none.clicked.connect(lambda: self._set_all_params(False))
        p_btn_row.addWidget(btn_none)
        param_layout.addLayout(p_btn_row)

        self._param_list = QListWidget()
        self._param_list.setFont(QFont("PT Sans", 9))
        self._param_list.itemChanged.connect(self._on_param_changed)
        param_layout.addWidget(self._param_list)
        side_layout.addWidget(param_group, 2)

        root_layout.addWidget(sidebar)

        # ── Middle: plot area ────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._plot_container = QWidget()
        self._plot_layout = QVBoxLayout(self._plot_container)
        self._plot_layout.setContentsMargins(0, 0, 0, 0)
        self._plot_layout.setSpacing(2)
        self._plot_layout.addStretch()
        self._scroll.setWidget(self._plot_container)
        root_layout.addWidget(self._scroll, stretch=1)

        # ── Right: cursor readout ────────────────────────────────────
        self._cursor_readout = CursorReadoutPanel()
        self._cursor_readout.setMaximumWidth(280)
        self._cursor_readout.setMinimumWidth(200)
        root_layout.addWidget(self._cursor_readout)

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
        file_menu.addSeparator()
        file_menu.addAction("Save Session", self._save_session,
                            QKeySequence.Save)
        file_menu.addAction("Load Session...", self._load_session,
                            QKeySequence.Open)
        file_menu.addSeparator()
        file_menu.addAction("Export Plots as Image...", self._export_image)
        file_menu.addAction("Export Plots as PDF...", self._export_pdf)
        file_menu.addSeparator()
        file_menu.addAction("Open Data Logs Folder", self._open_datalogs_folder)
        file_menu.addAction("Open Analysis Folder", self._open_analysis_folder)
        file_menu.addSeparator()
        file_menu.addAction("Close", self.close, QKeySequence("Ctrl+W"))

        # ── Tools ────────────────────────────────────────────────────
        tools_menu = mb.addMenu("Tools")
        tools_menu.addAction("Add Common Vertical Cursor At Mouse",
                             self._add_vertical_cursor, QKeySequence("V"))
        tools_menu.addAction("Add Plot Vertical Cursor At Mouse",
                     self._add_plot_vertical_cursor, QKeySequence("Shift+V"))
        tools_menu.addAction("Add Horizontal Cursor at Mouse",
                             self._add_horizontal_cursor_at_mouse, QKeySequence("H"))
        tools_menu.addSeparator()
        tools_menu.addAction("Clear All Cursors", self._clear_all_cursors)
        tools_menu.addAction("Reset Zoom", self._reset_zoom)

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
            if self._selected_h_cursor >= 0:
                self._delete_h_cursor(self._selected_h_cursor)
                return
        super().keyPressEvent(event)

    # ──────────────────────────────────────────────────────────────────
    # Theme
    # ──────────────────────────────────────────────────────────────────
    def _apply_theme(self, _mode: str = ""):
        bg = THEME.c('plot_bg')
        fg = THEME.c('plot_fg')
        alpha = THEME.plot_grid_alpha()

        for pw in self._plot_widgets:
            pw.setBackground(bg)
            for axis_name in ('left', 'bottom'):
                ax = pw.getAxis(axis_name)
                pen = pg.mkPen(fg)
                ax.setPen(pen)
                ax.setTextPen(pen)
            pw.showGrid(x=True, y=True, alpha=alpha)

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
            thread.log_loaded.connect(self._on_log_loaded)
            thread.error.connect(self._on_load_error)
            thread.finished.connect(lambda t=thread: self._cleanup_thread(t))
            self._loader_threads.append(thread)
            thread.start()

        n = len(self._loader_threads)
        if n:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._status.showMessage(f"Loading {n} file(s)... please wait")

    def _cleanup_thread(self, t):
        if t in self._loader_threads:
            self._loader_threads.remove(t)
        if not self._loader_threads:
            QApplication.restoreOverrideCursor()

    def _on_log_loaded(self, log_id: str, path: str, entry: LogEntry):
        self._logs[log_id] = entry
        self._add_log_to_sidebar(entry)
        self._rebuild_param_list()
        self._rebuild_plots()
        self._status.showMessage(
            f"Loaded: {entry.name}  ({len(entry.elapsed)} rows)", 5000)

    def _on_load_error(self, path: str, msg: str):
        self._status.showMessage(f"Error loading {os.path.basename(path)}: {msg}", 8000)
        QApplication.restoreOverrideCursor()  # restore on error too
        self._popup_warning("Load Error", f"Could not load:\n{path}\n\n{msg}")

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
        self._logs.pop(log_id, None)
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
    # Plot height
    # ──────────────────────────────────────────────────────────────────
    def _on_plot_height_changed(self, value: int):
        self._plot_height = value
        self._height_label.setText(f"{value}px")
        for pw in self._plot_widgets:
            pw.setMinimumHeight(value)
            pw.setMaximumHeight(value)

    # ──────────────────────────────────────────────────────────────────
    # Parameter selector
    # ──────────────────────────────────────────────────────────────────
    def _rebuild_param_list(self):
        self._param_list.blockSignals(True)
        # Gather currently checked params before clearing
        prev_checked = set()
        for i in range(self._param_list.count()):
            it = self._param_list.item(i)
            if it and it.checkState() == Qt.Checked:
                prev_checked.add(it.text())

        self._param_list.clear()

        # Union of all parameter names across loaded logs
        all_params: list[str] = []
        seen = set()
        for entry in self._logs.values():
            for p in entry.available_params():
                if p not in seen:
                    seen.add(p)
                    all_params.append(p)

        for p in all_params:
            item = QListWidgetItem(p)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if prev_checked:
                item.setCheckState(Qt.Checked if p in prev_checked else Qt.Unchecked)
            else:
                # First load — check default params
                item.setCheckState(Qt.Checked if p in DEFAULT_PARAMS else Qt.Unchecked)
            self._param_list.addItem(item)

        self._param_list.blockSignals(False)

    def _get_checked_params(self) -> list[str]:
        params = []
        for i in range(self._param_list.count()):
            it = self._param_list.item(i)
            if it and it.checkState() == Qt.Checked:
                params.append(it.text())
        return params

    def _set_all_params(self, checked: bool):
        self._param_list.blockSignals(True)
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self._param_list.count()):
            it = self._param_list.item(i)
            if it:
                it.setCheckState(state)
        self._param_list.blockSignals(False)
        self._rebuild_plots()

    def _on_param_changed(self, item: QListWidgetItem):
        self._rebuild_plots()

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
        for pw in self._plot_widgets:
            self._plot_layout.removeWidget(pw)
            pw.deleteLater()
        self._plot_widgets.clear()
        self._plot_params.clear()
        self._curves.clear()
        self._crosshair_lines.clear()
        self._cursor_dots.clear()

        while self._plot_layout.count():
            item = self._plot_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        checked = self._get_checked_params()
        if not checked or not self._logs:
            self._plot_layout.addStretch()
            return

        bg = THEME.c('plot_bg')
        fg = THEME.c('plot_fg')
        alpha = THEME.plot_grid_alpha()

        first_pw = None
        for pi, param in enumerate(checked):
            pw = pg.PlotWidget()
            pw.setBackground(bg)
            pw.showGrid(x=True, y=True, alpha=alpha)
            pw.setLabel('left', param)
            pw.setMinimumHeight(self._plot_height)
            pw.setMaximumHeight(self._plot_height)
            pw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # Performance: clip and downsample
            pw.setClipToView(True)
            pw.setDownsampling(auto=True, mode='peak')

            for axis_name in ('left', 'bottom'):
                ax = pw.getAxis(axis_name)
                pen = pg.mkPen(fg)
                ax.setPen(pen)
                ax.setTextPen(pen)

            if pi == len(checked) - 1:
                pw.setLabel('bottom', 'Elapsed Time (s)')
            else:
                pw.setLabel('bottom', '')

            if first_pw is not None:
                pw.setXLink(first_pw)
            else:
                first_pw = pw

            legend = pw.addLegend(offset=(10, 10))
            legend.setLabelTextSize('8pt')

            for entry in self._logs.values():
                if param not in entry.columns:
                    continue
                x = entry.elapsed + entry.time_offset
                y = entry.columns[param]
                mask = ~np.isnan(y)
                pen = pg.mkPen(color=entry.color, width=2)
                curve = pw.plot(x[mask], y[mask], pen=pen, name=entry.name)
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

            self._plot_widgets.append(pw)
            self._plot_params.append(param)
            self._plot_layout.addWidget(pw)

        self._plot_layout.addStretch()
        self._restore_v_cursors()
        self._update_cursor_dots()
        # (wait cursor released by _rebuild_plots wrapper)

    # ──────────────────────────────────────────────────────────────────
    # Crosshair / mouse tracking
    # ──────────────────────────────────────────────────────────────────
    def _on_mouse_moved(self, evt, pw: pg.PlotWidget):
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
        if pi < 0:
            return
        param = self._plot_params[pi]
        parts = [f"t={t:.3f}s"]
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
                parts.append(f"{entry.name}: {yv:.2f}")

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
        """Return the current plot widget showing the given parameter."""
        for idx, param in enumerate(self._plot_params):
            if param == plot_param and idx < len(self._plot_widgets):
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
            plot_param = self._plot_params[self._plot_widgets.index(anchor_pw)]

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

    def _on_v_cursor_moved(self, cursor_id: str, moved_line: pg.InfiniteLine):
        cdata = self._find_cursor_by_id(cursor_id)
        if cdata is None:
            return
        t = moved_line.value()
        cdata['time'] = t
        for pw, line in cdata['lines'].items():
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
            pw.removeItem(line)
        # Remove tracking dots
        if cid in self._cursor_dots:
            for dot in self._cursor_dots.pop(cid):
                dot['pw'].removeItem(dot['item'])
        # Reset selection
        if self._selected_v_cursor == cid:
            self._selected_v_cursor = ''
        self._update_cursor_readout()

    def _update_cursor_readout(self):
        visible_logs = [e for e in self._logs.values() if e.visible]
        params = self._get_checked_params()
        self._cursor_readout.update_readout(self._v_cursors, visible_logs, params)

    def _update_cursor_dots(self):
        """Rebuild tracking dots for all cursors on all plots."""
        for cid, dots in self._cursor_dots.items():
            for dot in dots:
                dot['pw'].removeItem(dot['item'])
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
                dot['pw'].removeItem(dot['item'])
        dots = []
        t = cdata['time']
        for pw in cdata['lines'].keys():
            if pw not in self._plot_widgets:
                continue
            pi = self._plot_widgets.index(pw)
            param = self._plot_params[pi]
            for entry in self._logs.values():
                if not entry.visible or param not in entry.columns:
                    continue
                x = entry.elapsed + entry.time_offset
                if len(x) == 0:
                    continue
                idx = np.searchsorted(x, t)
                idx = min(idx, len(x) - 1)
                yv = entry.columns[param][idx]
                if np.isnan(yv):
                    continue
                dot_item = pg.ScatterPlotItem(
                    [t], [yv], size=8, pen=pg.mkPen('w', width=1),
                    brush=pg.mkBrush(entry.color))
                pw.addItem(dot_item, ignoreBounds=True)
                dots.append({'pw': pw, 'item': dot_item})
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

        ci = len(self._h_cursors)
        color = CURSOR_COLORS[(ci + 2) % len(CURSOR_COLORS)]
        line = pg.InfiniteLine(
            pos=val, angle=0, movable=True,
            pen=pg.mkPen(color, width=2, style=Qt.DashDotLine),
            label=f'{val:.2f}',
            labelOpts={'position': 0.05, 'color': color,
                       'fill': THEME.c('cursor_label_bg'),
                       'movable': True})
        pw.addItem(line, ignoreBounds=True)
        line.sigPositionChanged.connect(
            lambda l: l.label.setText(f'{l.value():.2f}'))
        line.sigClicked.connect(
            lambda *a, _ci=ci: self._on_h_cursor_selected(_ci))
        self._h_cursors.append({
            'line': line, 'plot_widget': pw,
            'value': val, 'color': color,
        })

    def _on_h_cursor_selected(self, cursor_index: int):
        """Mark h-cursor as selected (red pen), deselect others."""
        prev = self._selected_h_cursor
        self._selected_h_cursor = cursor_index
        if 0 <= prev < len(self._h_cursors) and prev != cursor_index:
            hc = self._h_cursors[prev]
            hc['line'].setPen(pg.mkPen(hc['color'], width=2, style=Qt.DashDotLine))
        if 0 <= cursor_index < len(self._h_cursors):
            self._h_cursors[cursor_index]['line'].setPen(
                pg.mkPen(SELECTED_CURSOR_COLOR, width=3, style=Qt.DashDotLine))

    def _delete_h_cursor(self, cursor_index: int):
        if cursor_index < 0 or cursor_index >= len(self._h_cursors):
            return
        hc = self._h_cursors.pop(cursor_index)
        hc['plot_widget'].removeItem(hc['line'])
        if self._selected_h_cursor == cursor_index:
            self._selected_h_cursor = -1
        elif self._selected_h_cursor > cursor_index:
            self._selected_h_cursor -= 1

    def _clear_all_cursors(self):
        # Vertical
        for cdata in self._v_cursors:
            for pw, line in cdata['lines'].items():
                pw.removeItem(line)
        self._v_cursors.clear()
        self._selected_v_cursor = ''

        # Cursor dots
        for cid, dots in self._cursor_dots.items():
            for dot in dots:
                dot['pw'].removeItem(dot['item'])
        self._cursor_dots.clear()

        # Horizontal
        for hc in self._h_cursors:
            hc['plot_widget'].removeItem(hc['line'])
        self._h_cursors.clear()
        self._selected_h_cursor = -1

        self._update_cursor_readout()

    def _reset_zoom(self):
        for pw in self._plot_widgets:
            pw.autoRange()

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

        data = {
            'version': SESSION_VERSION,
            'plot_height': self._plot_height,
            'logs': [],
            'parameters': self._get_checked_params(),
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

        for hc in self._h_cursors:
            pi = -1
            for i, pw in enumerate(self._plot_widgets):
                if pw is hc['plot_widget']:
                    pi = i
                    break
            data['cursors']['horizontal'].append({
                'plot_index': pi,
                'value': hc['line'].value(),
                'color': hc['color'],
            })

        if self._plot_widgets:
            x_range = self._plot_widgets[0].getPlotItem().vb.viewRange()[0]
            data['view_range'] = {'x': x_range}

        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            self._status.showMessage(f"Session saved to {os.path.basename(path)}", 5000)
        except Exception as exc:
            self._popup_warning("Save Error", str(exc))

    def _load_session(self):
        folder = get_analysis_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Analysis Session", folder,
            "Analysis Session (*.json)")
        if not path:
            return

        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception as exc:
            self._popup_warning("Load Error", str(exc))
            return

        ver = data.get('version', 0)
        if ver not in (1, 2, 3):
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
        self._height_slider.setValue(self._plot_height)

        session_params = set(data.get('parameters', []))

        pending_logs = data.get('logs', [])
        self._pending_session = {
            'params': session_params,
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
            thread.log_loaded.connect(
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

        self._rebuild_param_list()
        self._param_list.blockSignals(True)
        for i in range(self._param_list.count()):
            it = self._param_list.item(i)
            if it:
                it.setCheckState(
                    Qt.Checked if it.text() in session['params']
                    else Qt.Unchecked)
        self._param_list.blockSignals(False)

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
                line = pg.InfiniteLine(
                    pos=val, angle=0, movable=True,
                    pen=pg.mkPen(color, width=2, style=Qt.DashDotLine),
                    label=f'{val:.2f}',
                    labelOpts={'position': 0.05, 'color': color,
                               'fill': THEME.c('cursor_label_bg'),
                               'movable': True})
                pw.addItem(line, ignoreBounds=True)
                line.sigPositionChanged.connect(
                    lambda l: l.label.setText(f'{l.value():.2f}'))
                self._h_cursors.append({
                    'line': line, 'plot_widget': pw,
                    'value': val, 'color': color,
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
        os.startfile(get_datalogs_dir())

    def _open_analysis_folder(self):
        os.startfile(get_analysis_dir())

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
            from PySide6.QtGui import QImage, QPixmap
            from PySide6.QtCore import QMarginsF
            from pyqtgraph.exporters import ImageExporter

            if filt and "SVG" in filt:
                from pyqtgraph.exporters import SVGExporter
                for i, pw in enumerate(self._plot_widgets):
                    p = path if len(self._plot_widgets) == 1 else \
                        path.replace('.svg', f'_{self._plot_params[i]}.svg')
                    exporter = SVGExporter(pw.getPlotItem())
                    exporter.export(p)
                self._status.showMessage(f"Exported SVG to {os.path.dirname(path)}", 5000)
                return

            if filt and "PDF" in filt or path.lower().endswith('.pdf'):
                from PySide6.QtGui import QPageSize, QPageLayout
                from PySide6.QtPrintSupport import QPrinter
                # Render each plot to image with forced white background + black axes
                plot_images = []
                export_width = 1600
                for pw in self._plot_widgets:
                    self._set_plot_export_theme(pw, dark=False)
                    exporter = ImageExporter(pw.getPlotItem())
                    exporter.parameters()['width'] = export_width
                    exporter.parameters()['background'] = pg.mkColor('w')
                    img = exporter.export(toBytes=True)
                    self._restore_plot_theme(pw)
                    plot_images.append(img)

                # Stitch vertically onto one canvas with white bg
                total_h = sum(img.height() for img in plot_images) + 8 * max(len(plot_images) - 1, 0)
                canvas = QImage(export_width, total_h, QImage.Format_ARGB32)
                canvas.fill(QColor('#ffffff'))
                painter_c = QPainter(canvas)
                y = 0
                for img in plot_images:
                    painter_c.drawImage(0, y, img)
                    y += img.height() + 8
                painter_c.end()

                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(path)
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
                self._status.showMessage(f"Exported PDF to {os.path.basename(path)}", 5000)
                return

            # Default: PNG composite using ImageExporter (avoids blank OpenGL grabs)
            images = []
            total_height = 0
            width = 0
            for pw in self._plot_widgets:
                exporter = ImageExporter(pw.getPlotItem())
                img = exporter.export(toBytes=True)
                images.append(img)
                total_height += img.height() + 10
                width = max(width, img.width())

            composite = QImage(width, total_height, QImage.Format_ARGB32)
            composite.fill(QColor(THEME.c('plot_bg')))
            painter = QPainter(composite)
            y_offset = 0
            for img in images:
                painter.drawImage(0, y_offset, img)
                y_offset += img.height() + 10
            painter.end()
            composite.save(path)
            self._status.showMessage(f"Exported PNG to {os.path.basename(path)}", 5000)

        except Exception as exc:
            self._popup_warning("Export Error", str(exc))

    # ──────────────────────────────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        for t in self._loader_threads:
            t.quit()
            t.wait(500)
        self._loader_threads.clear()
        super().closeEvent(event)
