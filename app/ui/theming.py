"""Theme / styling logic extracted from main_window.py.

QSS string constants, the build_card_qss builder, the plot-palette
tuples, and ThemingMixin (which holds the theme-application methods).
"""

from __future__ import annotations

import logging
from typing import Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPen

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover
    pg = None

try:
    import qdarktheme
except ImportError:  # pragma: no cover
    qdarktheme = None

from .widgets import _apply_windows_dark_titlebar, _icon


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

/* 9. Theme-aware secondary text. Using explicit hex codes instead of
      palette(...) avoids Qt's QSS palette-resolution cache (Qt resolves
      palette(...) once at setStyleSheet time and never re-resolves on
      app palette changes, so theme toggles left these labels stuck). */
QLabel#hintLabel       { color: #94A3B8; }   /* Slate-400 — dim on dark slate */
QLabel#auxReadout      { color: #CBD5E1; }   /* Slate-300 — aux readouts */
QLabel#hoverReadout    { color: #F8FAFC; }   /* Slate-50  — primary on dark */

/* 10. Tabbed dock bars — match the dock title surface so the tabs
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

/* 8. Theme-aware secondary text. Mirror of the dark-override block:
      explicit colours so theme toggles produce a visible swap, instead
      of relying on palette(...) which Qt's QSS engine caches. */
QLabel#hintLabel       { color: #6B7280; }   /* Gray-500 — dim on white */
QLabel#auxReadout      { color: #4B5563; }   /* Gray-600 — aux readouts */
QLabel#hoverReadout    { color: #1F2937; }   /* Gray-800 — primary text */

/* 9. Tabbed dock bars (Bitfields | Enums | TX Commands | … and the
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


def resolve_theme(theme: str) -> str:
    """Map any theme name to a concrete ``"dark"`` or ``"light"``.

    The user-facing theme selection includes ``"auto"`` (System), which
    qdarktheme handles natively for its own palette but every QSS override
    and per-paint branch in this codebase used to fall through the
    ``theme == "dark"`` check and silently render as light. Result: on a
    dark-OS machine, picking System gave a dark qdarktheme palette with
    our LIGHT overrides on top — visually broken.

    The resolution path here:
      1. ``"dark"`` / ``"light"`` pass through unchanged.
      2. Anything else (``"auto"``, legacy values, typos) is resolved by
         inspecting the QApplication palette that qdarktheme just installed
         — palette window lightness < 128 means dark.
      3. If no QApplication is alive yet (very early boot), fall back to
         dark — the historical default.
    """
    if theme == "dark":
        return "dark"
    if theme == "light":
        return "light"
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPalette
        app = QApplication.instance()
        if app is not None:
            window = app.palette().color(QPalette.ColorRole.Window)
            return "dark" if window.lightness() < 128 else "light"
    except Exception:
        pass
    return "dark"


def build_card_qss(theme: str) -> str:
    """Assemble the app's shared card/dock/table/tab QSS for a given theme.

    Exposed so secondary top-level windows (e.g. Analysis Suite) can apply the
    same styling — qdarktheme's palette is applied app-wide, but these QSS
    rules are not, and must be installed on each top-level window.

    Accepts ``"auto"`` and resolves to the actual OS theme via
    :func:`resolve_theme` so callers don't have to.
    """
    effective = resolve_theme(theme)
    qss = _QSS_BASE
    if effective == "dark":
        qss += "\n" + _QSS_DARK_OVERRIDES
    else:
        qss += "\n" + _QSS_LIGHT_OVERRIDES
    return qss


class ThemingMixin:
    """MainWindow mixin holding theme/styling methods."""

    def _refresh_palette_dependent_widgets(self) -> None:
        """Re-resolve cached palette() references after an app-wide theme swap.

        Qt resolves ``palette(role)`` in a widget's stylesheet exactly once
        when ``setStyleSheet`` is called, then caches the concrete colour.
        Changing ``QApplication.palette()`` (as qdarktheme does on theme
        switch) does NOT invalidate that cache, so labels styled with e.g.
        ``color: palette(mid)`` stay on the previous theme's colour.

        Walking descendants once per switch is cheap — a few hundred widgets
        at worst — and the cost is paid only on user action, not per packet.
        Includes top-level dialogs/popups too so transient windows opened
        after a theme change pick up the new palette.
        """
        from PySide6.QtWidgets import QApplication, QWidget
        seen: set[int] = set()

        def repolish(w: QWidget) -> None:
            wid = id(w)
            if wid in seen:
                return
            seen.add(wid)
            qss = w.styleSheet()
            if qss and "palette(" in qss:
                # Three-step invalidation. Qt sometimes short-circuits
                # ``setStyleSheet(same_string)`` as a no-op, leaving the
                # cached resolved palette() colours untouched. Clearing
                # first, then unpolish/polish, then re-applying the
                # original string guarantees the QSS engine re-runs
                # palette() resolution against the live app palette.
                w.setStyleSheet("")
                w.style().unpolish(w)
                w.style().polish(w)
                w.setStyleSheet(qss)
                w.update()
            for child in w.findChildren(QWidget):
                repolish(child)

        repolish(self)
        # Cover dialogs/popups Qt has spawned that aren't descendants of self.
        app = QApplication.instance()
        if app is not None:
            for tlw in app.topLevelWidgets():
                if isinstance(tlw, QWidget):
                    repolish(tlw)

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

    def _apply_theme(self, theme: str) -> None:
        if qdarktheme is None:
            return
        try:
            qdarktheme.setup_theme(theme, corner_shape="rounded")
        except Exception as exc:
            self._popup_warning("Theme", f"Failed to apply theme: {exc}")
            return
        # Persist the USER'S selection (may be "auto"/System) so the choice
        # is sticky across restarts. sync() flushes immediately so a crash
        # before normal shutdown doesn't lose the setting.
        # _rebuild_action_icons -> _populate_view_menu reads the saved value
        # to decide its icon tint; without writing BEFORE that, the View
        # submenu stays on the previous theme's tint until the NEXT change.
        self._settings.setValue("ui/theme", theme)
        self._settings.sync()
        # Resolve "auto" -> "dark"/"light" once. Every downstream painter
        # branches on a binary; passing "auto" through to them would land
        # in the light path even on a dark OS.
        effective = resolve_theme(theme)
        # Re-apply our card + dark-override QSS on top of the fresh qdarktheme base.
        self._apply_card_qss(effective)
        # Rebuild qtawesome icons with the correct tint for the new theme.
        self._rebuild_action_icons(effective)
        # Repaint the pyqtgraph canvas — it is not a QWidget child so it does
        # not pick up the QPalette change automatically.
        self._apply_plot_theme(effective)
        # Stylesheets that reference `palette(...)` are resolved once when
        # setStyleSheet is called and the resolved colour is cached, so a
        # plain QApplication palette swap leaves those widgets stuck on the
        # previous theme's colours. Walk the descendant tree and re-set the
        # stylesheet on every widget that has palette() references; setting
        # the same string back forces Qt to re-resolve against the new app
        # palette. Catches the editor "🔒 Only signals marked RW..." info
        # label, hover readout, session clock, Hz rate, and any future
        # widget that uses palette(...) without us having to track it.
        self._refresh_palette_dependent_widgets()
        # Forward theme change to the Analysis Suite if it's open — it's a
        # separate top-level window so QSS doesn't cascade into it.
        analysis = getattr(self, "_analysis_window", None)
        if analysis is not None and hasattr(analysis, "apply_theme"):
            try:
                analysis.apply_theme(theme)
            except Exception:
                logging.getLogger("bytehound.ui").warning(
                    "Analysis Suite apply_theme failed", exc_info=True
                )
        from PySide6.QtWidgets import QApplication
        # Schedule title-bar update via singleShot so the native HWND is stable.
        dark = (effective == "dark")
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
        effective = resolve_theme(theme)
        if effective == "dark":
            bg = "#1E293B"          # match QDockWidget body — same Slate
            axis = "#CBD5E1"        # high-contrast on dark
            self._plot_palette = _PLOT_PALETTE_DARK
        else:
            bg = "#FFFFFF"
            axis = "#475569"        # readable on light
            self._plot_palette = _PLOT_PALETTE_LIGHT
        self._gl_widget.setBackground(pg.mkColor(bg))
        crosshair_pen = self._plot_crosshair_pen(effective)
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
                self._style_plot_legend(panel.legend, effective)
            if getattr(panel, "vline", None) is not None:
                panel.vline.setPen(crosshair_pen)
            if getattr(panel, "hline", None) is not None:
                panel.hline.setPen(crosshair_pen)
        if hasattr(self, "_panel_strip_layout") and self._panel_strip_layout is not None:
            self._rebuild_panel_strips()
        self._redraw_plot()

    def _current_plot_palette(self) -> Tuple[str, ...]:
        return getattr(self, "_plot_palette", _PLOT_PALETTE_DARK)

    def _plot_crosshair_pen(self, theme: str):
        if pg is None:
            return QPen()
        effective = resolve_theme(theme)
        color = "#94A3B8" if effective == "dark" else "#64748B"
        return pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)

    def _style_plot_legend(self, legend, theme: str) -> None:
        if pg is None or legend is None:
            return
        if resolve_theme(theme) == "dark":
            bg = QColor(15, 23, 42, 160)
            border = "#475569"
        else:
            bg = QColor(255, 255, 255, 180)
            border = "#CBD5E1"
        legend.setBrush(pg.mkBrush(bg))
        legend.setPen(pg.mkPen(border, width=1))

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
        color = "#F8FAFC" if resolve_theme(theme) == "dark" else "#1F2937"

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

