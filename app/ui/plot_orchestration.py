"""Live-plot orchestration methods extracted from MainWindow as a mixin.

Holds the methods that drive the live plot: grid build/rebuild, per-panel
state (auto-Y, saved Y range, signal assignment), redraw fast-path,
time-axis mode toggle, crosshair / mouse interactions, and indicator
refresh. Designed to be mixed into MainWindow.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple

import numpy as np

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QPushButton, QToolButton, QWidget, QWidgetAction, QColorDialog,
)


# Order matters: indexes are persisted to QSettings and used by the panel-strip
# QComboBox. Tuples are (mode-key, dropdown-label, tooltip).
_Y_SCALE_MODES: list[tuple[str, str, str]] = [
    ("fit",    "Y: Fit",    "Tight auto-fit (5% padding). Axis rescales every 0.5 s."),
    ("loose",  "Y: Loose",  "Auto-fit with 25% headroom — gentler than Fit; small noise stays inside the padding."),
    ("expand", "Y: Expand", "Axis only grows, never shrinks. Best for noisy signals — eliminates the 'breathing' you get with Fit."),
    ("manual", "Y: Manual", "Lock the y-range. Opens a dialog to type min/max; you can also mouse-pan/zoom or right-click → Set Y Range… later."),
]
_Y_SCALE_KEYS = [m[0] for m in _Y_SCALE_MODES]

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover
    pg = None

from .plot_panel import (
    PlotPanel,
    _PLOT_INITIAL_WINDOW_S,
    _TimeAxisItem,
    _configure_live_curve,
    _format_elapsed_time,
)
from .analysis_widgets import OverlayViewBox



class PlotOrchestrationMixin:
    """MainWindow mixin holding the live-plot orchestration methods."""

    def _visible_window_t_min(self) -> Optional[float]:
        """Lower bound (in elapsed seconds) of the currently-shown X window.

        Returns ``None`` when the user has selected "All session", which
        means callers should look at the full series.
        """
        window = getattr(self, "_plot_window_seconds", None)
        if not window:
            return None
        current_t = (datetime.now() - self._session_started).total_seconds()
        return max(0.0, current_t - float(window))

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

    def _on_plot_window_changed(self, idx: int) -> None:
        """User picked a new sliding-window length from the segmented control.

        Persists the choice and triggers an immediate redraw so the new
        window takes effect without waiting for the next packet.
        """
        options = getattr(self, "_plot_window_options", None)
        if not options or idx < 0 or idx >= len(options):
            return
        # Options entries are (short_label, full_label, seconds_or_None);
        # only the seconds value matters for the window.
        seconds = options[idx][-1]
        self._plot_window_seconds = seconds
        # 0 sentinel in QSettings → "All session" (None internally).
        self._settings.setValue("plot/window_seconds", int(seconds) if seconds else 0)
        # Resuming Live makes the window change visible immediately; if the
        # user was in Explore, they presumably want to inspect history, so
        # we leave that state alone and just redraw.
        if hasattr(self, "_hover_cache"):
            self._hover_cache.clear()
        self._redraw_plot()

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

    def _on_plot_state_btn_clicked(self) -> None:
        """Tri-state transition driven by the plot state button.

        State machine:
            Live    --click-->  Paused      (user explicitly freezes)
            Paused  --click-->  Live        (resume streaming)
            Explore --click-->  Live        (return to following data)

        Pan/zoom on the plot still flips Live -> Explore implicitly via
        the viewbox X-range handler; that path doesn't go through here.
        """
        if self._plot_live:
            self._set_plot_live(False, source="button")
            self._log_activity("[ACTION] Plot Paused")
        else:
            self._set_plot_live(True, source="button")
            self._log_activity("[ACTION] Plot resumed Live")
            self._redraw_plot()

    def _on_plot_y_range_changed(self, panel_idx: int, y_range) -> None:
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        if panel.y_scale_mode != "manual":
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
        """Periodically refit Y for panels in fit/loose/expand mode.

        Replaces pyqtgraph's continuous auto-range (which fires on every
        setData call) with a 2 Hz recompute. Skips when the computed range
        matches the current view so the axis only repaints when bounds
        actually changed.
        """
        if pg is None or not self._plot_panels:
            return
        if not self._plot_live:
            return  # paused — leave the user's view alone
        for panel in self._plot_panels:
            if panel.y_scale_mode == "manual":
                continue
            self._fit_panel_y_now(panel)

    def _fit_panel_y_now(self, panel) -> None:
        if pg is None:
            return
        mode = panel.y_scale_mode
        if mode == "manual":
            return
        vb = panel.plot_item.getViewBox()
        if vb is None:
            return
        # Only consider samples in the currently visible time window so
        # zooming out of a long-running session doesn't squash the y-axis
        # against historical outliers the user can no longer see.
        t_min = self._visible_window_t_min()
        left_min, left_max = None, None
        right_min, right_max = None, None

        for key in panel.assigned_keys:
            buf = self._plot_history.get(key)
            if buf is None or len(buf) == 0:
                continue
            _, ys = buf.arrays_since(t_min) if t_min is not None else buf.arrays()
            if ys.size == 0:
                continue
            local_min = float(np.nanmin(ys))
            local_max = float(np.nanmax(ys))

            unit = self._signal_unit_map.get(key, "").strip() if hasattr(self, "_signal_unit_map") else ""
            if panel.left_unit is None or unit == panel.left_unit:
                if left_min is None or local_min < left_min:
                    left_min = local_min
                if left_max is None or local_max > left_max:
                    left_max = local_max
            elif panel.right_unit is not None:
                if right_min is None or local_min < right_min:
                    right_min = local_min
                if right_max is None or local_max > right_max:
                    right_max = local_max

        def _apply_range(target_vb, y_min, y_max):
            if y_min is None or y_max is None:
                return
            if y_min == y_max:
                pad = max(abs(y_min) * 0.05, 1.0)
                y_min -= pad
                y_max += pad

            cur_range = target_vb.viewRange()[1]
            if mode == "expand" and cur_range and len(cur_range) == 2:
                cur_y_min, cur_y_max = float(cur_range[0]), float(cur_range[1])
                new_y_min = min(cur_y_min, y_min)
                new_y_max = max(cur_y_max, y_max)
                if new_y_min == cur_y_min and new_y_max == cur_y_max:
                    return
                y_min, y_max = new_y_min, new_y_max
                padding = 0.0
            else:
                padding = 0.25 if mode == "loose" else 0.05
                if cur_range and len(cur_range) == 2:
                    span = max(y_max - y_min, 1e-9)
                    expected_min = y_min - span * padding
                    expected_max = y_max + span * padding
                    if (abs(cur_range[0] - expected_min) / span < 0.01
                            and abs(cur_range[1] - expected_max) / span < 0.01):
                        return
            target_vb.setYRange(y_min, y_max, padding=padding)

        _apply_range(vb, left_min, left_max)
        if panel.right_vb is not None:
            _apply_range(panel.right_vb, right_min, right_max)

    def _persist_plot_y_range(self, panel_idx: int) -> None:
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        if panel.y_scale_mode != "manual":
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
        if panel.y_scale_mode == "manual":
            y_range = self._read_saved_y_range(panel_idx)
            if y_range is not None:
                vb.setYRange(y_range[0], y_range[1], padding=0)
        else:
            vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
            self._fit_panel_y_now(panel)
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

        # Clear variable-strip widgets and reset prior column/row stretches so
        # a previous 1×8 layout doesn't leave 8 stretched columns hanging
        # around after a switch to 4×2.
        if hasattr(self, "_panel_strip_layout") and self._panel_strip_layout is not None:
            while self._panel_strip_layout.count():
                item = self._panel_strip_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for c in range(self._panel_strip_layout.columnCount()):
                self._panel_strip_layout.setColumnStretch(c, 0)
            for r in range(self._panel_strip_layout.rowCount()):
                self._panel_strip_layout.setRowStretch(r, 0)

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
        from .theming import resolve_theme
        first_vb = None
        theme = resolve_theme(str(self._settings.value("ui/theme", "dark")))
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
                vb.menu.addAction(
                    "Set Y Range…",
                    lambda i=idx: self._prompt_panel_y_range(i),
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
            # Restore per-panel Y-scale mode. Falls back to the legacy
            # `auto_y` boolean key so users upgrading from the old checkbox
            # don't get reset to defaults.
            saved_mode = self._settings.value(f"plot/panel/{idx}/y_scale_mode", None)
            if saved_mode is None:
                legacy = self._settings.value(f"plot/panel/{idx}/auto_y", True)
                if isinstance(legacy, str):
                    legacy_on = legacy.lower() in ("true", "1", "yes")
                else:
                    legacy_on = bool(legacy)
                saved_mode = "fit" if legacy_on else "manual"
            mode = str(saved_mode).lower()
            if mode not in _Y_SCALE_KEYS:
                mode = "fit"
            panel.y_scale_mode = mode
            # Throttled auto-Y: we run our own 2 Hz fit (see _throttled_y_autofit)
            # so pyqtgraph's per-update auto-range stays off regardless of preference.
            vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
            if panel.y_scale_mode == "manual":
                y_range = self._read_saved_y_range(idx)
                if y_range is not None:
                    vb.setYRange(y_range[0], y_range[1], padding=0)
            self._plot_panels.append(panel)

            # Redraw existing curves for this panel
            for key in panel.assigned_keys:
                fid_str = f"0x{key[0]:04X}" if isinstance(key[0], int) else str(key[0])
                label = f"{fid_str} {key[1]}"
                color_idx = sum(len(p.assigned_keys) for p in self._plot_panels[:-1]) + len(panel.curves)
                palette = self._current_plot_palette()
                color = palette[color_idx % len(palette)]
                curve = pi.plot(name=label, pen=pg.mkPen(color, width=1.8))
                _configure_live_curve(curve)
                panel.curves[key] = curve

            # Build variable-strip widget for this panel, placed in the same
            # grid cell (row_idx, col_idx) as the plot so each strip sits
            # above its panel instead of jamming all N strips into one
            # horizontal row (which forced the dock to ~N*200px wide).
            if hasattr(self, "_panel_strip_layout") and self._panel_strip_layout is not None:
                strip = self._make_panel_strip(idx)
                self._panel_strip_layout.addWidget(strip, row_idx, col_idx)

        # Remember the grid dims so _rebuild_panel_strips (called after
        # add/remove-signal) places strips at the same (row, col) coords.
        self._plot_grid_rows = rows
        self._plot_grid_cols = cols
        if hasattr(self, "_panel_strip_layout") and self._panel_strip_layout is not None:
            for c in range(cols):
                self._panel_strip_layout.setColumnStretch(c, 1)

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
        """Build the per-panel control strip.

        Layout: ``P{n}: [Signals ▾ (count)] [+ Add] [Auto Y]``. The
        assigned signals live behind the Signals dropdown so a panel
        with 14 cell voltages doesn't blow out the strip width and
        squash the plot underneath. Each menu row carries a colour
        swatch, the signal name, and a remove (✕) button.
        """
        strip = QWidget()
        strip.setObjectName(f"panelStrip_{panel_idx}")
        strip.setMaximumHeight(36)
        hl = QHBoxLayout(strip)
        hl.setContentsMargins(2, 2, 2, 2)
        hl.setSpacing(4)
        lbl = QLabel(f"P{panel_idx + 1}:")
        lbl.setStyleSheet("font-weight:bold; font-size:9pt;")
        hl.addWidget(lbl)

        panel = self._plot_panels[panel_idx] if panel_idx < len(self._plot_panels) else None
        sig_count = len(panel.assigned_keys) if panel else 0
        signals_btn = QToolButton()
        signals_btn.setText(self._panel_signals_button_label(sig_count))
        signals_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        signals_btn.setFixedHeight(24)
        signals_btn.setStyleSheet(
            "QToolButton { font-size:9pt; padding: 0 8px; }"
            "QToolButton::menu-indicator { subcontrol-position: right center; }"
        )
        signals_btn.setToolTip(
            "Signals assigned to this panel. Click a row's ✕ to remove."
        )
        signals_btn.setMenu(self._build_panel_signals_menu(panel_idx, signals_btn))
        signals_btn.setEnabled(sig_count > 0)
        hl.addWidget(signals_btn)

        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(24)
        add_btn.setStyleSheet("font-size:9pt; padding: 0 6px;")
        add_btn.clicked.connect(lambda _, i=panel_idx: self._on_panel_add_signal(i))
        hl.addWidget(add_btn)
        # Per-panel Y-scale mode. Fit/Loose/Expand/Manual — see _Y_SCALE_MODES.
        # Expand mode is the noise-killer: axis only grows, so jittery signals
        # don't make it breathe on every redraw.
        y_scale_cb = QComboBox()
        y_scale_cb.setFixedHeight(24)
        y_scale_cb.setStyleSheet("QComboBox { font-size: 9pt; padding: 0 4px; }")
        current_mode = panel.y_scale_mode if panel else "fit"
        for mode_key, label, tip in _Y_SCALE_MODES:
            y_scale_cb.addItem(label, mode_key)
            y_scale_cb.setItemData(y_scale_cb.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        try:
            y_scale_cb.setCurrentIndex(_Y_SCALE_KEYS.index(current_mode))
        except ValueError:
            y_scale_cb.setCurrentIndex(0)
        y_scale_cb.setToolTip(
            "Y-axis scale mode. Use Expand if Fit is too twitchy on noisy signals."
        )
        y_scale_cb.currentIndexChanged.connect(
            lambda new_idx, i=panel_idx: self._on_panel_y_scale_changed(i, new_idx))
        hl.addWidget(y_scale_cb)
        hl.addStretch(1)
        return strip

    @staticmethod
    def _panel_signals_button_label(count: int) -> str:
        if count == 0:
            return "Signals (none)"
        if count == 1:
            return "Signals (1)"
        return f"Signals ({count})"

    def _build_panel_signals_menu(self, panel_idx: int, parent: QWidget) -> QMenu:
        """Build the dropdown menu listing this panel's assigned signals.

        Each row is a custom widget with [colour dot] [name] [✕]. The
        menu is rebuilt fresh whenever the strip is rebuilt (after add
        or remove), so there's no separate refresh path.
        """
        menu = QMenu(parent)
        menu.setStyleSheet(
            "QMenu { padding: 4px; }"
            "QWidget { background: transparent; }"
        )
        if panel_idx >= len(self._plot_panels):
            return menu
        panel = self._plot_panels[panel_idx]
        if not panel.assigned_keys:
            empty_action = menu.addAction("(no signals on this panel)")
            empty_action.setEnabled(False)
            return menu

        color_offset = sum(
            len(self._plot_panels[i].assigned_keys) for i in range(panel_idx)
        )
        palette = self._current_plot_palette()
        for local_idx, key in enumerate(panel.assigned_keys):
            custom_color = self._settings.value(f"plot/colors/{key[1]}")
            if custom_color:
                color = str(custom_color)
            else:
                color = palette[(color_offset + local_idx) % len(palette)]
            row = self._build_panel_signal_menu_row(panel_idx, key, color, menu)
            action = QWidgetAction(menu)
            action.setDefaultWidget(row)
            menu.addAction(action)
        return menu

    def _build_panel_signal_menu_row(
        self, panel_idx: int, key: Tuple[int, str], color: str, menu: QMenu,
    ) -> QWidget:
        row = QWidget(menu)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(6, 2, 6, 2)
        rl.setSpacing(8)

        def select_color():
            initial_color = QColor(color)
            chosen_color = QColorDialog.getColor(initial_color, self, f"Select Color for {key[1]}")
            if chosen_color.isValid():
                chosen_hex = chosen_color.name()
                self._settings.setValue(f"plot/colors/{key[1]}", chosen_hex)
                menu.close()
                self._rebuild_panel_strips()
                self._redraw_plot()

        dot = QToolButton(row)
        dot.setText("●")
        dot.setAutoRaise(True)
        dot.setStyleSheet(f"QToolButton {{ color:{color}; font-size:10pt; border:none; padding:0; background:transparent; }}")
        dot.setCursor(Qt.CursorShape.PointingHandCursor)
        dot.setToolTip("Click to change color")
        dot.clicked.connect(select_color)
        rl.addWidget(dot)

        fid_str = f"0x{key[0]:04X}" if isinstance(key[0], int) else str(key[0])
        name = QLabel(f"{fid_str} · {key[1]}", row)
        name.setStyleSheet("font-size:9pt; color: palette(text);")
        name.setMinimumWidth(180)
        name.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        name.customContextMenuRequested.connect(lambda pos: select_color())
        name.setToolTip("Right-click to change color")
        rl.addWidget(name, 1)

        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(lambda pos: select_color())

        remove = QToolButton(row)
        remove.setText("✕")
        remove.setAutoRaise(True)
        remove.setToolTip("Remove this signal from the panel")
        remove.setStyleSheet(
            "QToolButton { font-size:9pt; padding: 0 6px; color:#b04a4a; }"
            "QToolButton:hover { color:#ff5555; }"
        )

        def _remove():
            menu.close()
            self._remove_signal_from_panel(panel_idx, key)

        remove.clicked.connect(_remove)
        rl.addWidget(remove)
        return row

    def _on_panel_y_scale_changed(self, panel_idx: int, new_idx: int) -> None:
        if panel_idx >= len(self._plot_panels) or pg is None:
            return
        if new_idx < 0 or new_idx >= len(_Y_SCALE_KEYS):
            return
        mode = _Y_SCALE_KEYS[new_idx]
        panel = self._plot_panels[panel_idx]
        panel.y_scale_mode = mode
        vb = panel.plot_item.getViewBox()
        # Don't enable pyqtgraph's continuous auto-Y — the 2 Hz throttled
        # fitter handles it.
        vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        if mode == "manual":
            # Freeze the current view as the starting lock, then prompt the
            # user to type exact bounds. Cancel keeps the frozen view.
            y_range = vb.viewRange()[1]
            if y_range and len(y_range) == 2:
                self._settings.setValue(
                    f"plot/panel/{panel_idx}/y_range",
                    [float(y_range[0]), float(y_range[1])],
                )
            self._settings.setValue(f"plot/panel/{panel_idx}/y_scale_mode", mode)
            self._prompt_panel_y_range(panel_idx)
            return
        # Switching back into an auto mode: refit immediately so the user
        # sees the change without waiting for the next throttled tick.
        self._fit_panel_y_now(panel)
        self._settings.setValue(f"plot/panel/{panel_idx}/y_scale_mode", mode)

    def _prompt_panel_y_range(self, panel_idx: int) -> None:
        """Pop the Y-range dialog for *panel_idx* and apply on accept.

        Also flips the panel into Manual mode — typing a range only makes
        sense if the axis won't immediately rescale away from it. Reachable
        from the Y-scale dropdown's Manual option and the ViewBox right-
        click menu.
        """
        if pg is None or panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        vb = panel.plot_item.getViewBox()
        if vb is None:
            return
        cur = vb.viewRange()[1]
        cur_min = float(cur[0]) if cur and len(cur) == 2 else 0.0
        cur_max = float(cur[1]) if cur and len(cur) == 2 else 1.0

        from .dialogs import YRangeDialog
        dlg = YRangeDialog(self, f"Panel {panel_idx + 1}", cur_min, cur_max)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        y_min, y_max = dlg.get_range()
        # Force Manual mode so the throttled fitter doesn't immediately
        # overwrite the user's chosen range on the next 2 Hz tick.
        panel.y_scale_mode = "manual"
        self._settings.setValue(f"plot/panel/{panel_idx}/y_scale_mode", "manual")
        self._settings.setValue(
            f"plot/panel/{panel_idx}/y_range", [y_min, y_max],
        )
        vb.setYRange(y_min, y_max, padding=0)
        # Sync the strip combobox in case the user reached this dialog via
        # the right-click menu while the dropdown still said Fit/Loose/Expand.
        self._rebuild_panel_strips()

    def _rebuild_panel_strips(self) -> None:
        """Rebuild all variable-chip strips after assignments change.

        Strips are placed in the same (row, col) cells as the plot panels —
        the grid dims are cached on _plot_grid_rows / _plot_grid_cols by
        _rebuild_plot_grid. Falls back to a single column when called
        before the first grid build.
        """
        if not hasattr(self, "_panel_strip_layout") or self._panel_strip_layout is None:
            return
        while self._panel_strip_layout.count():
            item = self._panel_strip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cols = getattr(self, "_plot_grid_cols", 1) or 1
        for idx in range(len(self._plot_panels)):
            row_idx, col_idx = divmod(idx, cols)
            strip = self._make_panel_strip(idx)
            self._panel_strip_layout.addWidget(strip, row_idx, col_idx)
        for c in range(cols):
            self._panel_strip_layout.setColumnStretch(c, 1)

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
            fid_str = f"0x{key[0]:04X}" if isinstance(key[0], int) else str(key[0])
            self._log_activity(
                f"[ACTION] Added signal {fid_str} {key[1]} to panel {panel_idx + 1}"
            )

    def _remove_signal_from_panel(self, panel_idx: int, key: Tuple[int, str]) -> None:
        if panel_idx >= len(self._plot_panels):
            return
        panel = self._plot_panels[panel_idx]
        if key in panel.assigned_keys:
            panel.assigned_keys.remove(key)
            if key in panel.curves:
                curve = panel.curves.pop(key)
                try:
                    curve.clear()
                except Exception:
                    pass
                try:
                    panel.plot_item.removeItem(curve)
                except Exception:
                    pass
                # Removing from the plot does NOT remove the legend row in
                # pyqtgraph — leave this out and the legend keeps a phantom
                # entry, then re-adding the same signal stacks a second row
                # for the same name. Drop both the curve and the legend row.
                if panel.right_vb is not None:
                    try:
                        panel.right_vb.removeItem(curve)
                    except Exception:
                        pass
                if panel.legend is not None:
                    try:
                        panel.legend.removeItem(curve)
                    except Exception:
                        pass
            self._sync_plot_keys()
            self._persist_panel_assignments()
            self._rebuild_panel_strips()
            self._redraw_plot()
            fid_str = f"0x{key[0]:04X}" if isinstance(key[0], int) else str(key[0])
            self._log_activity(
                f"[ACTION] Removed signal {fid_str} {key[1]} from panel {panel_idx + 1}"
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

    def _on_plot_range_changed(self, vb, x_range) -> None:
        """Called when any ViewBox X-range changes.

        Guard suppresses changes triggered by our own setXRange calls;
        any other change means the user panned/zoomed → switch to Explore.
        """
        if self._plot_range_changing or not getattr(self, "_initial_show_done", True):
            return
        self._plot_range_changing = True
        try:
            if self._plot_panels:
                first_vb = self._plot_panels[0].plot_item.getViewBox()
                if first_vb is not None and first_vb is not vb:
                    first_vb.setXRange(*x_range, padding=0)
        finally:
            self._plot_range_changing = False
        if self._plot_live:
            # User pan/zoom is functionally the same as Pausing.
            self._set_plot_live(False, source="pan")
            self._log_activity("[ACTION] Plot switched to Explore mode (user pan/zoom)")

    def _set_plot_live(self, live: bool, *, source: str = "") -> None:
        """Single source of truth for ``_plot_live`` + the tri-state button.

        Every code path that wants to flip the plot between Live and
        Explore/Pause goes through here so internal state and UI cannot
        drift. ``source`` is "pan" when the change was triggered by a
        user pan/zoom (renders as Explore); any other source for a
        non-live transition renders as Paused.

        When transitioning to Live, re-fit Y axes that were disturbed by
        pan/zoom during the previous freeze. X-axis range is left to
        _redraw_plot so the data-aware window logic stays centralised.
        """
        was_live = self._plot_live
        self._plot_live = live
        if live and not was_live and pg is not None and self._plot_panels:
            self._plot_range_changing = True
            try:
                for panel in self._plot_panels:
                    vb = panel.plot_item.getViewBox()
                    if vb is not None and panel.y_scale_mode != "manual":
                        self._fit_panel_y_now(panel)
            finally:
                self._plot_range_changing = False
        if not hasattr(self, "_plot_state_btn"):
            return
        if live:
            label, bg, bg_hover, tip = (
                "⏵ Live",
                "#16A34A",
                "#22C55E",
                "Streaming — click to pause (Space).",
            )
        elif source == "pan":
            label, bg, bg_hover, tip = (
                "🔍 Explore",
                "#2563EB",
                "#3B82F6",
                "View frozen — you panned/zoomed. Click to resume Live (Space).",
            )
        else:
            label, bg, bg_hover, tip = (
                "⏸ Paused",
                "#D97706",
                "#F59E0B",
                "Paused — click to resume Live (Space).",
            )
        self._plot_state_btn.setText(label)
        self._plot_state_btn.setToolTip(tip)
        self._plot_state_btn.setStyleSheet(
            f"QPushButton {{ background:{bg}; color:#fff; border:none;"
            f"               padding:4px 12px; border-radius:4px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{bg_hover}; }}"
        )

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
                    # In Live mode with a finite window, only the visible
                    # slice is needed — saves a full-series copy when the
                    # buffer has hours of data.
                    if self._plot_live:
                        window_t_min = self._visible_window_t_min()
                    else:
                        window_t_min = None
                    if window_t_min is not None:
                        xs_view, ys_view = buf.arrays_since(window_t_min)
                    else:
                        xs_view, ys_view = buf.arrays()
                    # Copy so chunk seal-and-swap can't mutate storage behind
                    # the cached arrays — arrays_since() of a single chunk
                    # returns a view, and the cache is cleared every flush.
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
        # Sliding-window lower bound (None = show entire session).
        # Only honoured in Live mode — Explore means the user has panned
        # to inspect historical data and needs the full series to be
        # visible regardless of the current Window dropdown setting.
        window_t_min = self._visible_window_t_min() if self._plot_live else None

        color_offset = 0
        # Track the oldest sample we want to *show*. For finite windows this
        # is just window_t_min; for "All session" it is the first sample we
        # have. We never look past samples that were dropped by the safety
        # cap (TimeSeriesBuffer keeps first_x() current).
        oldest_x: Optional[float] = None

        for panel in self._plot_panels:
            pi = panel.plot_item
            if hasattr(pi, "isVisible") and not pi.isVisible():
                color_offset += len(panel.assigned_keys)
                continue
            active_keys = set(panel.assigned_keys)

            # Determine left and right units
            left_unit = None
            right_unit = None
            for key in panel.assigned_keys:
                unit = self._signal_unit_map.get(key, "").strip() if hasattr(self, "_signal_unit_map") else ""
                if left_unit is None:
                    left_unit = unit
                elif unit != left_unit and right_unit is None:
                    right_unit = unit

            panel.left_unit = left_unit
            panel.right_unit = right_unit

            pi.setLabel('left', text=left_unit if left_unit else "")

            if right_unit is not None:
                if panel.right_vb is None:
                    panel.right_vb = OverlayViewBox()
                    pi.scene().addItem(panel.right_vb)
                    pi.showAxis('right')
                    ax = pi.getAxis('right')
                    ax.linkToView(panel.right_vb)
                    panel.right_vb.setXLink(pi.getViewBox())
                    panel.right_vb.sigXRangeChanged.connect(self._on_plot_range_changed)
                    panel.right_axis = ax

                    from .theming import resolve_theme
                    theme = resolve_theme(str(self._settings.value("ui/theme", "dark")))
                    fg = "#CBD5E1" if theme == "dark" else "#475569"
                    pen = pg.mkPen(fg)
                    ax.setPen(pen)
                    ax.setTextPen(pen)

                    def updateViews(dummy_arg=None, target_pi=pi, target_vb=panel.right_vb):
                        if target_vb is not None and target_pi is not None:
                            vb = target_pi.getViewBox()
                            if vb is not None:
                                target_vb.setGeometry(vb.sceneBoundingRect())
                                target_vb.linkedViewChanged(vb, target_vb.XAxis)

                    pi.getViewBox().sigResized.connect(updateViews)
                    updateViews()

                panel.right_axis.setLabel(text=right_unit)
                panel.right_axis.show()

                # Sync geometry of the overlayed right ViewBox with the main ViewBox on every redraw
                # to prevent layout mismatch when axis labels change size.
                vb = pi.getViewBox()
                if vb is not None and panel.right_vb is not None:
                    panel.right_vb.setGeometry(vb.sceneBoundingRect())
                    panel.right_vb.linkedViewChanged(vb, panel.right_vb.XAxis)
            elif panel.right_axis is not None:
                panel.right_axis.hide()

            # Remove curves for keys no longer assigned
            for key in list(panel.curves):
                if key not in active_keys:
                    curve = panel.curves.pop(key)
                    try:
                        curve.clear()
                    except Exception:
                        pass
                    try:
                        pi.removeItem(curve)
                    except Exception:
                        pass
                    if panel.right_vb is not None:
                        try:
                            panel.right_vb.removeItem(curve)
                        except Exception:
                            pass
                    # Legend rows aren't auto-removed with the curve — clear
                    # the entry here too so any future path that drops a key
                    # without going through _remove_signal_from_panel still
                    # leaves a clean legend behind.
                    if panel.legend is not None:
                        try:
                            panel.legend.removeItem(curve)
                        except Exception:
                            pass

            for local_idx, key in enumerate(panel.assigned_keys):
                buf = self._plot_history.get(key)
                xs_len = len(buf) if buf is not None else 0
                if buf is not None and xs_len:
                    first_x = buf.first_x()
                    if first_x is not None and (oldest_x is None or first_x < oldest_x):
                        oldest_x = first_x

                custom_color = self._settings.value(f"plot/colors/{key[1]}")
                if custom_color:
                    color = str(custom_color)
                else:
                    color = palette[(color_offset + local_idx) % len(palette)]
                fid_str = f"0x{key[0]:04X}" if isinstance(key[0], int) else str(key[0])
                label = f"{fid_str} {key[1]}"

                unit = self._signal_unit_map.get(key, "").strip() if hasattr(self, "_signal_unit_map") else ""
                is_right = (right_unit is not None and unit != left_unit)
                target_vb = panel.right_vb if is_right else pi.getViewBox()

                curve = panel.curves.get(key)

                if curve is not None:
                    try:
                        old_vb = curve.getViewBox()
                        if old_vb != target_vb:
                            if old_vb is not None:
                                try:
                                    curve.clear()
                                except Exception:
                                    pass
                                try:
                                    if hasattr(old_vb, "removeItem"):
                                        old_vb.removeItem(curve)
                                except Exception:
                                    pass
                            try:
                                pi.getViewBox().removeItem(curve)
                            except Exception:
                                pass
                            if panel.right_vb is not None:
                                try:
                                    panel.right_vb.removeItem(curve)
                                except Exception:
                                    pass
                            if panel.legend is not None:
                                try:
                                    panel.legend.removeItem(curve)
                                except Exception:
                                    pass
                            curve = None
                    except Exception:
                        curve = None

                if curve is None:
                    curve = pg.PlotDataItem(name=label, pen=pg.mkPen(color, width=1.8))
                    _configure_live_curve(curve)
                    panel.curves[key] = curve
                    curve._bh_color = color  # type: ignore[attr-defined]
                    try:
                        target_vb.addItem(curve)
                    except Exception:
                        pass
                    if pi.legend is not None:
                        try:
                            pi.legend.addItem(curve, name=label)
                        except Exception:
                            pass
                else:
                    if getattr(curve, "_bh_color", None) != color:
                        try:
                            curve.setPen(pg.mkPen(color, width=1.8))
                        except Exception:
                            pass
                        curve._bh_color = color  # type: ignore[attr-defined]

                # Skip setData when this curve hasn't changed since the last
                # redraw. Signature mixes length, right-most timestamp, and
                # the window lower bound — so widening the window after a
                # long quiet period still re-renders the older samples.
                last_x = buf.last_x() if (buf is not None and xs_len) else None
                signature = (xs_len, last_x, window_t_min)
                if getattr(curve, "_bh_last_sig", None) == signature:
                    continue

                if buf is None or xs_len == 0:
                    try:
                        curve.clear()
                    except Exception:
                        pass
                    curve._bh_last_sig = signature  # type: ignore[attr-defined]
                    continue
                elif window_t_min is not None:
                    # Feed only samples inside the visible window; whole
                    # chunks below the window are skipped by arrays_since().
                    x_values, y_values = buf.arrays_since(window_t_min)
                else:
                    x_values, y_values = buf.arrays()

                try:
                    curve.setData(
                        x_values, y_values,
                        autoDownsample=True,
                        clipToView=True,
                    )
                    curve._bh_last_sig = signature  # type: ignore[attr-defined]
                except Exception:
                    # If Pyqtgraph throws an exception (e.g. mid-layout caching bug),
                    # catch it so we don't break the loop, and don't cache the signature
                    # so we retry next frame.
                    pass

            color_offset += len(panel.assigned_keys)

        # Live mode X range. Three cases:
        #   - No data yet: anchor [0, INITIAL_WINDOW] so the axis reads 0 at
        #     the left while waiting for the first packet.
        #   - Finite window: anchor [current_t - window, current_t * 1.02]
        #     so the newest sample sits near the right edge and the axis
        #     scrolls as time advances.
        #   - All session: anchor [oldest_x, current_t * 1.05] so the curve
        #     fills the panel from the first sample we still have.
        # The re-entrancy guard stops sigXRangeChanged from flipping us to Explore.
        if self._plot_live and self._plot_panels:
            self._plot_range_changing = True
            try:
                first_pi = self._plot_panels[0].plot_item
                if oldest_x is None and window_t_min is None:
                    x_min = 0.0
                    x_max = _PLOT_INITIAL_WINDOW_S
                elif window_t_min is not None:
                    # Pin to the sliding window even when the first packet
                    # hasn't arrived — keeps the axis reading sensibly.
                    span = max(float(self._plot_window_seconds or 0), _PLOT_INITIAL_WINDOW_S)
                    x_min = max(0.0, current_t - span)
                    x_max = max(current_t, x_min + _PLOT_INITIAL_WINDOW_S)
                    # Small right padding so the newest point isn't flush
                    # against the edge.
                    x_max = x_min + (x_max - x_min) * 1.02
                else:
                    x_min = oldest_x or 0.0
                    span = max(current_t - x_min, _PLOT_INITIAL_WINDOW_S)
                    x_max = x_min + span * 1.05
                first_pi.setXRange(x_min, x_max, padding=0)
            finally:
                self._plot_range_changing = False

    def _on_plot_settings(self) -> None:
        self._log_activity("[ACTION] Open Plot Settings dialog")
        from .dialogs import PlotSettingsDialog
        from PySide6.QtWidgets import QDialog
        dlg = PlotSettingsDialog(self._settings, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cap_val, window_s = dlg.get_values()

        # Apply cap to existing plot buffers
        self._plot_history_max_samples = cap_val if cap_val > 0 else None
        for buf in self._plot_history.values():
            buf.set_max_samples(self._plot_history_max_samples)

        # Apply display window
        self._plot_window_seconds = window_s if window_s > 0 else None

        # Force a redraw to update display window immediately
        self._redraw_plot()

        self._set_status(
            f"Plot settings updated: memory cap {cap_val or 'Unlimited'}, display window {window_s or 'All'}"
        )
        self._log_activity(
            f"[INFO] Plot settings updated: max_samples={cap_val}, window_s={window_s}"
        )

