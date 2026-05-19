"""Live-plot orchestration methods extracted from MainWindow as a mixin.

Holds the methods that drive the live plot: grid build/rebuild, per-panel
state (auto-Y, saved Y range, signal assignment), redraw fast-path,
time-axis mode toggle, crosshair / mouse interactions, and indicator
refresh. Designed to be mixed into MainWindow.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
    QPushButton, QWidget,
)

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover
    pg = None

from .plot_panel import (
    PlotPanel,
    _EMPTY_F64,
    _PLOT_INITIAL_WINDOW_S,
    _TimeAxisItem,
    _configure_live_curve,
    _format_elapsed_time,
)
from .widgets import _contrast_text_color


class PlotOrchestrationMixin:
    """MainWindow mixin holding the live-plot orchestration methods."""

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

