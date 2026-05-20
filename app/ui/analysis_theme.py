"""Theme palette + app constants for the Analysis Suite.

Extracted from analysis_suite.py so the helper widgets (cursor readout,
stats panel, X-Y plotter, time-axis item) can import shared colours and
the THEME singleton without forming an import cycle with the main window
class.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal


# ─── App identity (used as QSettings org/app name) ──────────────────────
APP_NAME = "Bytehound"
APP_ORG = "Bytehound"


def get_datalogs_dir() -> str:
    path = Path.home() / "Documents" / APP_NAME / "Logs"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def get_analysis_dir() -> str:
    path = Path.home() / "Documents" / APP_NAME / "Analysis"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


# ─── Plot palette ───────────────────────────────────────────────────────
# Theme-aware color provider so plots/cursors follow the app's dark/light
# setting. Mirrors _apply_plot_theme() in main_window.py — same Slate
# (#1E293B) for dark plot bg and #FFFFFF for light, so the Analysis Suite
# plots match the Live Plot canvas exactly.
_DARK_PLOT_COLORS = {
    'plot_bg': '#1E293B',
    'plot_fg': '#CBD5E1',
    'crosshair': '#94A3B8',
    'cursor_label_bg': '#0F172A',
    'border': '#334155',
    'legend_bg': (0, 0, 0, 100),
}
_LIGHT_PLOT_COLORS = {
    'plot_bg': '#FFFFFF',
    'plot_fg': '#475569',
    'crosshair': '#64748B',
    'cursor_label_bg': '#F3F4F6',
    'border': '#E5E7EB',
    'legend_bg': (255, 255, 255, 160),
}


class _AppTheme(QObject):
    theme_changed = Signal(str)

    def theme(self) -> str:
        return str(QSettings(APP_ORG, APP_NAME).value("ui/theme", "dark"))

    def c(self, key: str) -> str:
        palette = _LIGHT_PLOT_COLORS if self.theme() == "light" else _DARK_PLOT_COLORS
        return palette.get(key, '#FFFFFF')

    def plot_grid_alpha(self) -> float:
        return 0.15


THEME = _AppTheme()


# ─── Per-log / per-cursor colour cycles ─────────────────────────────────
LOG_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#17becf', '#bcbd22',
    '#ff9896', '#98df8a', '#c5b0d5', '#393b79',
]

CURSOR_COLORS = ['#e63946', '#457b9d', '#2a9d8f', '#f4a261', '#6a4c93']
SELECTED_CURSOR_COLOR = '#ff0000'


def _parse_unit(param_name: str) -> str | None:
    """Extract unit string from a column header.

    Recognises both parenthesised and bracketed conventions:
        ``Voltage [V]``  → ``V``
        ``Speed (Kmph)`` → ``Kmph``
        ``Temperature``  → None
    """
    m = re.search(r'[\[\(]([^\]\)]+)[\]\)]\s*$', param_name)
    return m.group(1).strip() if m else None
