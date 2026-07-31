"""Reusable UI widgets and helpers carved out of main_window.py.

Houses small, MainWindow-independent UI components:
* :class:`_CheckableGroupCombo`   — multi-select group filter button.
* :class:`_StatusBadgeDelegate`   — pill-style Status column delegate.
* :class:`TitleBarThemeFilter`    — application-wide native title-bar themer.
* :func:`_apply_windows_dark_titlebar` — the underlying DWM toggle.
* :func:`_icon`                   — qtawesome wrapper that degrades gracefully.
* :func:`_pad_dock_content`       — applies internal margins to a QDockWidget.
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QSettings, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

try:
    import qtawesome as qta  # type: ignore
except ImportError:  # pragma: no cover - icons degrade to empty if missing
    qta = None

from ..decoder.types import FrameConfig


# Primary toolbar button colour palette. Three semantic states; all buttons
# show white (#FFFFFF) text/icons on top.
_BTN_GREEN  = "#16A34A"   # idle / safe-to-activate  (Connect, Start Auto-Fetch)
_BTN_YELLOW = "#D97706"   # ready but not running     (Start Logging — inactive)
_BTN_PINK   = "#DB2777"   # currently active / danger (Disconnect, Stop Fetch/Log)


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


def _apply_windows_accent_titlebar(widget, color) -> None:
    """Apply custom title bar caption and border colors to match the theme accent.

    Only effective on Windows 11+.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())

        # Windows COLORREF is 0x00BBGGRR
        bgr_color = (color.blue() << 16) | (color.green() << 8) | color.red()
        value = ctypes.c_int(bgr_color)

        # DWMWA_CAPTION_COLOR = 35
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            35,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )

        # DWMWA_BORDER_COLOR = 34
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            34,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )

        # Set text color to white/black for contrast
        # DWMWA_TEXT_COLOR = 36
        luminance = (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255.0
        text_color_val = 0x00FFFFFF if luminance < 0.5 else 0x00000000
        text_value = ctypes.c_int(text_color_val)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            36,
            ctypes.byref(text_value),
            ctypes.sizeof(text_value),
        )
    except Exception:
        pass


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
        self.setObjectName("checkableGroupCombo")
        self.setMinimumWidth(160)
        self.setText("All groups  ▾")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Popup container ──────────────────────────────────────
        self._popup = QFrame(self.window(), Qt.WindowType.Popup)
        self._popup.setObjectName("checkableGroupPopup")
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
            self.setText("All groups  ▾")
        elif len(checked) == 1:
            self.setText(f"{checked[0]}  ▾")
        else:
            self.setText(f"{len(checked)} groups  ▾")


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
        # Lazy import: widgets.py is imported during theming.py module init,
        # so a top-level import would be a cycle.
        from .theming import resolve_theme
        theme = "dark"
        if self._settings is not None:
            theme = str(self._settings.value("ui/theme", "dark"))
        if resolve_theme(theme) == "light":
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
                    from .theming import resolve_theme
                    from PySide6.QtGui import QPalette
                    from PySide6.QtWidgets import QApplication

                    theme = str(self._settings.value("ui/theme", "dark"))
                    is_dark = (resolve_theme(theme) == "dark")
                    _apply_windows_dark_titlebar(obj, dark=is_dark)

                    accent = QApplication.palette().color(QPalette.ColorRole.Highlight)
                    _apply_windows_accent_titlebar(obj, accent)
            except Exception:
                pass
        return False


class FrameFormatWidget(QWidget):
    """A graphical, byte-aligned widget that displays a protocol's on-wire frame format."""

    def __init__(self, config: FrameConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._protocol = config.protocol
        self._grid_widget = None
        self._tx_grid_widget = None
        self._init_ui()

    def _init_ui(self) -> None:
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QTabWidget, QScrollArea
        from PySide6.QtCore import Qt

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(6)

        # Dropdown selection layout for RX
        self._rx_container = QWidget()
        rx_layout = QVBoxLayout(self._rx_container)
        rx_layout.setContentsMargins(0, 0, 0, 0)
        rx_layout.setSpacing(6)

        selector_layout = QHBoxLayout()
        selector_layout.setContentsMargins(0, 0, 0, 0)

        lbl_text = "Select Register:" if self._protocol.parser_type == "modbus_rtu" else "Select Frame Structure:"
        self._select_lbl = QLabel(lbl_text)
        self._select_lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
        selector_layout.addWidget(self._select_lbl)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(220)

        default_item = "All Registers (General)" if self._protocol.parser_type == "modbus_rtu" else "All Frames (General Template)"
        self._combo.addItem(default_item, userData=None)

        # Add all loaded frames to the dropdown
        for frame_id in sorted(self._config.frames.keys()):
            frame = self._config.frames[frame_id]
            desc = f"0x{frame_id:04X}"
            if frame.frame_name:
                desc += f" - {frame.frame_name}"
            self._combo.addItem(desc, userData=frame_id)

        self._combo.currentIndexChanged.connect(self._on_frame_selection_changed)
        selector_layout.addWidget(self._combo)
        selector_layout.addStretch()

        rx_layout.addLayout(selector_layout)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setStyleSheet("background: transparent; border: none;")
        rx_layout.addWidget(self._scroll_area)

        # Check if TX commands exist
        if self._config.tx_commands:
            self._tab_widget = QTabWidget(self)
            self._tab_widget.addTab(self._rx_container, "RX Frames / Registers")

            self._tx_container = QWidget()
            tx_layout = QVBoxLayout(self._tx_container)
            tx_layout.setContentsMargins(4, 4, 4, 4)
            tx_layout.setSpacing(6)

            tx_selector_layout = QHBoxLayout()
            tx_selector_layout.setContentsMargins(0, 0, 0, 0)

            tx_lbl_text = "Select TX Command:"
            self._tx_select_lbl = QLabel(tx_lbl_text)
            self._tx_select_lbl.setStyleSheet("font-weight: bold; font-size: 11px;")
            tx_selector_layout.addWidget(self._tx_select_lbl)

            self._tx_combo = QComboBox()
            self._tx_combo.setMinimumWidth(220)

            default_tx_item = "All Commands (General Template)"
            self._tx_combo.addItem(default_tx_item, userData=None)

            # Add all TX commands to the dropdown
            for cmd_name in sorted(self._config.tx_commands.keys()):
                cmd = self._config.tx_commands[cmd_name]
                desc = cmd_name
                if cmd.description:
                    desc += f" ({cmd.description})"
                self._tx_combo.addItem(desc, userData=cmd_name)

            self._tx_combo.currentIndexChanged.connect(self._on_tx_selection_changed)
            tx_selector_layout.addWidget(self._tx_combo)
            tx_selector_layout.addStretch()

            tx_layout.addLayout(tx_selector_layout)

            self._tx_scroll_area = QScrollArea()
            self._tx_scroll_area.setWidgetResizable(True)
            self._tx_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._tx_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._tx_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            self._tx_scroll_area.setStyleSheet("background: transparent; border: none;")
            tx_layout.addWidget(self._tx_scroll_area)

            self._tab_widget.addTab(self._tx_container, "TX Commands")
            self._main_layout.addWidget(self._tab_widget)

            # Initial rebuild of TX grid
            self._rebuild_tx_grid(None)
        else:
            self._main_layout.addWidget(self._rx_container)

        # Build initial RX grid
        self._rebuild_grid(None)

    def _on_frame_selection_changed(self, index: int) -> None:
        frame_id = self._combo.itemData(index)
        self._rebuild_grid(frame_id)

    def _on_tx_selection_changed(self, index: int) -> None:
        cmd_name = self._tx_combo.itemData(index)
        self._rebuild_tx_grid(cmd_name)

    def _hex_to_bytes(self, value: str) -> bytes:
        cleaned = (value or "").replace(" ", "").replace("0x", "").replace("0X", "")
        if not cleaned:
            return b""
        try:
            return bytes.fromhex(cleaned)
        except ValueError:
            return b""

    def _build_byte_grid(self, fields: list[tuple[str, int, str, str]]) -> QWidget:
        from PySide6.QtWidgets import QGridLayout, QLabel
        from PySide6.QtCore import Qt

        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        layout = QGridLayout(grid_widget)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 4, 0, 4)

        colors = {
            "Amber": ("#F59E0B", "#D97706", "#B45309"),
            "Emerald": ("#10B981", "#059669", "#047857"),
            "Indigo": ("#6366F1", "#4F46E5", "#4338CA"),
            "Teal": ("#06B6D4", "#0891B2", "#0E7490"),
            "Pink": ("#EC4899", "#DB2777", "#9D174D"),
            "Grey": ("#6B7280", "#4B5563", "#374151"),
            "Muted": ("#64748B", "#475569", "#334155"),
        }

        total_bytes = sum(size for _, size, _, _ in fields)
        for i in range(total_bytes):
            lbl = QLabel(f"Byte {i}")
            lbl.setStyleSheet("font-size: 9px; font-weight: bold; margin-bottom: 2px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl, 0, i)

        col_idx = 0
        for label_text, size, color_name, tooltip in fields:
            display_text = label_text
            if len(display_text) > 12 and size <= 2:
                display_text = display_text[:9] + "..."

            lbl = QLabel(display_text)
            lbl.setToolTip(tooltip)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)

            start_c, end_c, border_c = colors[color_name]
            style = f"""
                QLabel {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {start_c}, stop:1 {end_c});
                    color: #FFFFFF;
                    border: 1px solid {border_c};
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 11px;
                    padding: 8px 2px;
                }}
                QLabel:hover {{
                    border-color: #FFFFFF;
                }}
            """
            lbl.setStyleSheet(style)
            layout.addWidget(lbl, 1, col_idx, 1, size)
            col_idx += size

        grid_widget.setMinimumWidth(total_bytes * 45)
        grid_widget.setMaximumHeight(85)
        return grid_widget

    def _rebuild_grid(self, frame_id: Optional[int]) -> None:
        if self._grid_widget:
            self._grid_widget.deleteLater()
            self._grid_widget = None

        # Define fields: (Label, Size in bytes, Color key, Tooltip description)
        if self._protocol.parser_type == "modbus_rtu":
            if frame_id is not None:
                # Modbus Register specific frame layout
                signals = self._config.signals_by_frame.get(frame_id, [])
                if signals:
                    sig_names = ", ".join(s.signal_name for s in signals)
                    data_desc = f"Mapped signals: {sig_names}"
                    data_label = signals[0].signal_name if len(signals) == 1 else "Reg Data"
                else:
                    data_desc = "No variables configured at this address"
                    data_label = "Reg Data"

                fields = [
                    ("Node Addr", 1, "Amber", f"Node/Slave Address (0x{self._protocol.modbus_node_address:02X})"),
                    ("Func Code", 1, "Emerald", "Function Code (e.g. 0x03 Read, 0x06 Write)"),
                    ("Reg Addr", 2, "Indigo", f"Register Start Address: 0x{frame_id:04X} ({frame_id})"),
                    (data_label, 2, "Teal", f"Register Data/Value (2 bytes, Big-endian)\n{data_desc}"),
                    ("CRC-16", 2, "Pink", "CRC-16 Checksum (2 bytes, Little-endian)"),
                ]
            else:
                fields = [
                    ("Node Addr", 1, "Amber", f"Node/Slave Address (0x{self._protocol.modbus_node_address:02X})"),
                    ("Func Code", 1, "Emerald", "Function Code (e.g. 0x03 Read, 0x06 Write)"),
                    ("Reg Addr", 2, "Indigo", "Register Start Address (2 bytes, Big-endian)"),
                    ("Reg Value", 2, "Teal", "Register Data/Value (2-byte response/request, Big-endian)"),
                    ("CRC-16", 2, "Pink", "CRC-16 Checksum (2 bytes, Little-endian)"),
                ]
        else:
            fields = []
            if self._protocol.header:
                fields.append((
                    "Header",
                    len(self._protocol.header),
                    "Amber",
                    f"Frame Header Hex: 0x{self._protocol.header.hex().upper()}"
                ))
            if self._protocol.frame_id_size > 0:
                fid_val_desc = f" (Value: 0x{frame_id:04X})" if frame_id is not None else ""
                fields.append((
                    "Frame ID",
                    self._protocol.frame_id_size,
                    "Emerald",
                    f"Frame Identifier ({self._protocol.frame_id_size} bytes, {self._protocol.frame_id_byte_order}-endian){fid_val_desc}"
                ))
            if self._protocol.length_size > 0:
                len_bo = self._protocol.length_byte_order or self._protocol.frame_id_byte_order
                fields.append((
                    "Length",
                    self._protocol.length_size,
                    "Indigo",
                    f"Payload Length ({self._protocol.length_size} bytes, {len_bo}-endian, meaning: {self._protocol.length_meaning})"
                ))

            if frame_id is not None:
                # Add specific signals for selected Frame ID
                signals = self._config.signals_by_frame.get(frame_id, [])
                sorted_signals = sorted(signals, key=lambda s: s.start_byte)

                frame_def = self._config.frames.get(frame_id)
                expected_payload_len = frame_def.payload_length if frame_def else None

                current_byte = 0
                for sig in sorted_signals:
                    if sig.start_byte > current_byte:
                        gap_size = sig.start_byte - current_byte
                        fields.append((
                            "Unused",
                            gap_size,
                            "Muted",
                            f"Unused payload byte(s) ({gap_size} bytes)"
                        ))

                    fields.append((
                        sig.signal_name,
                        sig.byte_length,
                        "Teal",
                        f"Signal: {sig.signal_name}\nData Type: {sig.data_type}\nByte offset: {sig.start_byte}\nSize: {sig.byte_length} bytes\nScale: {sig.scale}\nOffset: {sig.offset}\nUnit: {sig.unit or '-'}"
                    ))
                    current_byte = sig.end_byte

                if expected_payload_len is not None and expected_payload_len > current_byte:
                    gap_size = expected_payload_len - current_byte
                    tx_cmd = next((c for c in self._config.tx_commands.values() if c.frame_id == frame_id), None)
                    if tx_cmd and tx_cmd.fields:
                        tf_names = ", ".join(f.field_name for f in tx_cmd.fields)
                        desc = f"Unused for RX telemetry decoding ({gap_size} bytes).\nOutbound TX fields ({tf_names}) are configured in the 'TX Commands' tab."
                        label = "TX Frame" if current_byte == 0 else "Unused"
                    else:
                        desc = f"Unused trailing payload byte(s) ({gap_size} bytes)"
                        label = "Unused"
                    fields.append((
                        label,
                        gap_size,
                        "Muted",
                        desc
                    ))
                elif not sorted_signals:
                    fields.append((
                        "Data",
                        8,
                        "Teal",
                        "Payload Data (no signals configured)"
                    ))
            else:
                fixed_size = len(self._protocol.header) + self._protocol.frame_id_size + self._protocol.length_size + self._protocol.crc_size + len(self._protocol.footer)
                if self._protocol.tx_pad_length is not None:
                    payload_size = max(0, self._protocol.tx_pad_length - fixed_size)
                    data_label = f"Data ({payload_size}-Byte)"
                else:
                    payload_size = 8
                    data_label = "Data (8-Byte)"

                fields.append((
                    data_label,
                    payload_size,
                    "Teal",
                    "Payload Data (configured signals)"
                ))

            if self._protocol.crc_size > 0:
                fields.append((
                    f"CRC-{self._protocol.crc_size*8}",
                    self._protocol.crc_size,
                    "Pink",
                    f"CRC Checksum ({self._protocol.crc_size} bytes, type: {self._protocol.crc_type}, {self._protocol.crc_byte_order}-endian)"
                ))
            if self._protocol.footer:
                fields.append((
                    "Footer",
                    len(self._protocol.footer),
                    "Grey",
                    f"Frame Footer Hex: 0x{self._protocol.footer.hex().upper()}"
                ))

        self._grid_widget = self._build_byte_grid(fields)
        self._scroll_area.setWidget(self._grid_widget)

    def _compute_tx_field_blocks(self, cmd_fields: list) -> list[tuple[str, int, str, str]]:
        from ..decoder.types import FMT_SIZES
        blocks: list[tuple[str, int, str, str]] = []
        bool_group: list = []

        def flush_bools():
            nonlocal bool_group
            if not bool_group:
                return
            num_bools = len(bool_group)
            num_bytes = (num_bools + 7) // 8
            names = [f.field_name for f in bool_group]
            label = names[0] if num_bools == 1 else f"Flags ({num_bools} bits)"
            if len(", ".join(names)) <= 25:
                label = ", ".join(names)

            details = "\n".join([f"• Bit {i}: {f.field_name}" for i, f in enumerate(bool_group)])
            tooltip = f"Bit-packed Boolean Flags ({num_bools} bits in {num_bytes} byte(s)):\n{details}"
            blocks.append((label, num_bytes, "Teal", tooltip))
            bool_group = []

        for f in cmd_fields:
            if getattr(f, "is_boolean", False):
                bool_group.append(f)
                if len(bool_group) == 8:
                    flush_bools()
            else:
                flush_bools()
                size = FMT_SIZES.get(f.fmt, 1)
                tooltip = f"Field: {f.field_name}\nType: {f.fmt}\nUnit: {f.unit or '-'}\nByte Order: {f.byte_order}\nScale: {f.factor}\nOffset: {f.offset}"
                blocks.append((f.field_name, size, "Teal", tooltip))
        flush_bools()
        return blocks

    def _compute_tx_fields_size(self, cmd_fields: list) -> int:
        return sum(b[1] for b in self._compute_tx_field_blocks(cmd_fields))

    def _rebuild_tx_grid(self, command_name: Optional[str]) -> None:
        if not hasattr(self, "_tx_scroll_area"):
            return

        if self._tx_grid_widget:
            self._tx_grid_widget.deleteLater()
            self._tx_grid_widget = None

        if self._protocol.parser_type == "modbus_rtu":
            if command_name is not None:
                command = self._config.tx_commands.get(command_name)
                if command is not None:
                    static_bytes = self._hex_to_bytes(command.payload_hex)
                    fields_size = self._compute_tx_fields_size(command.fields)
                    total_payload_size = len(static_bytes) + fields_size

                    if total_payload_size == 0:
                        fields = [
                            ("Node Addr", 1, "Amber", f"Node/Slave Address (0x{self._protocol.modbus_node_address:02X})"),
                            ("Func Code", 1, "Emerald", "Function Code: 0x03 (Read Holding Registers)"),
                            ("Reg Addr", 2, "Indigo", f"Register Start Address: 0x{command.frame_id:04X} ({command.frame_id})"),
                            ("Quantity", 2, "Teal", "Quantity of registers to read (2 bytes, default 1)"),
                            ("CRC-16", 2, "Pink", "CRC-16 Checksum (2 bytes, Little-endian)"),
                        ]
                    elif total_payload_size == 2:
                        val_desc = "Register Write Value (2 bytes)"
                        val_label = "Value"
                        if command.fields:
                            f = command.fields[0]
                            val_label = f.field_name
                            val_desc = f"Field: {f.field_name}\nType: {f.fmt}\nUnit: {f.unit or '-'}"
                        elif static_bytes:
                            val_desc = f"Static value hex: 0x{static_bytes.hex().upper()}"
                            val_label = f"Value (0x{static_bytes.hex().upper()})"

                        fields = [
                            ("Node Addr", 1, "Amber", f"Node/Slave Address (0x{self._protocol.modbus_node_address:02X})"),
                            ("Func Code", 1, "Emerald", "Function Code: 0x06 (Write Single Register)"),
                            ("Reg Addr", 2, "Indigo", f"Register Start Address: 0x{command.frame_id:04X} ({command.frame_id})"),
                            (val_label, 2, "Teal", f"Register Data/Value (2-byte response/request, Big-endian)\n{val_desc}"),
                            ("CRC-16", 2, "Pink", "CRC-16 Checksum (2 bytes, Little-endian)"),
                        ]
                    else:
                        qty = total_payload_size // 2
                        fields = [
                            ("Node Addr", 1, "Amber", f"Node/Slave Address (0x{self._protocol.modbus_node_address:02X})"),
                            ("Func Code", 1, "Emerald", "Function Code: 0x10 (Write Multiple Registers)"),
                            ("Reg Addr", 2, "Indigo", f"Register Start Address: 0x{command.frame_id:04X} ({command.frame_id})"),
                            ("Quantity", 2, "Teal", f"Quantity of registers (2 bytes, value: {qty})"),
                            ("Byte Count", 1, "Teal", f"Byte count (1 byte, value: {total_payload_size})"),
                        ]
                        if static_bytes:
                            fields.append((
                                "Static Payload",
                                len(static_bytes),
                                "Teal",
                                f"Static payload bytes: 0x{static_bytes.hex().upper()}"
                            ))
                        fields.extend(self._compute_tx_field_blocks(command.fields))
                        fields.append(
                            ("CRC-16", 2, "Pink", "CRC-16 Checksum (2 bytes, Little-endian)")
                        )
                else:
                    command_name = None

            if command_name is None:
                fields = [
                    ("Node Addr", 1, "Amber", f"Node/Slave Address (0x{self._protocol.modbus_node_address:02X})"),
                    ("Func Code", 1, "Emerald", "Function Code (e.g. 0x03 Read, 0x06/0x10 Write)"),
                    ("Reg Addr", 2, "Indigo", "Register Start Address (2 bytes, Big-endian)"),
                    ("Reg Value", 2, "Teal", "Register Data/Value (2-byte response/request, Big-endian)"),
                    ("CRC-16", 2, "Pink", "CRC-16 Checksum (2 bytes, Little-endian)"),
                ]
        else:
            fields = []
            if self._protocol.header:
                fields.append((
                    "Header",
                    len(self._protocol.header),
                    "Amber",
                    f"Frame Header Hex: 0x{self._protocol.header.hex().upper()}"
                ))
            if self._protocol.frame_id_size > 0:
                fid_val_desc = ""
                if command_name is not None:
                    command = self._config.tx_commands.get(command_name)
                    if command is not None:
                        fid_val_desc = f" (Value: 0x{command.frame_id:04X})"
                fields.append((
                    "Frame ID",
                    self._protocol.frame_id_size,
                    "Emerald",
                    f"Frame Identifier ({self._protocol.frame_id_size} bytes, {self._protocol.frame_id_byte_order}-endian){fid_val_desc}"
                ))
            if self._protocol.length_size > 0:
                len_bo = self._protocol.length_byte_order or self._protocol.frame_id_byte_order
                fields.append((
                    "Length",
                    self._protocol.length_size,
                    "Indigo",
                    f"Payload Length ({self._protocol.length_size} bytes, {len_bo}-endian, meaning: {self._protocol.length_meaning})"
                ))

            if command_name is not None:
                command = self._config.tx_commands.get(command_name)
                if command is not None:
                    static_bytes = self._hex_to_bytes(command.payload_hex)
                    if static_bytes:
                        fields.append((
                            "Static Payload",
                            len(static_bytes),
                            "Teal",
                            f"Static payload bytes: 0x{static_bytes.hex().upper()}"
                        ))

                    fields.extend(self._compute_tx_field_blocks(command.fields))

                    if self._protocol.tx_pad_length is not None:
                        fixed_size = len(self._protocol.header) + self._protocol.frame_id_size + self._protocol.length_size + self._protocol.crc_size + len(self._protocol.footer)
                        payload_size = len(static_bytes) + self._compute_tx_fields_size(command.fields)
                        padding_size = self._protocol.tx_pad_length - fixed_size - payload_size
                        if padding_size > 0:
                            fields.append((
                                "Padding",
                                padding_size,
                                "Muted",
                                f"Zero padding to reach fixed tx_pad_length={self._protocol.tx_pad_length}"
                            ))
                else:
                    command_name = None

            if command_name is None:
                fixed_size = len(self._protocol.header) + self._protocol.frame_id_size + self._protocol.length_size + self._protocol.crc_size + len(self._protocol.footer)
                if self._protocol.tx_pad_length is not None:
                    payload_size = max(0, self._protocol.tx_pad_length - fixed_size)
                    data_label = f"Data ({payload_size}-Byte)"
                else:
                    payload_size = 8
                    data_label = "Data (8-Byte)"

                fields.append((
                    data_label,
                    payload_size,
                    "Teal",
                    "Payload Data (configured fields)"
                ))

            if self._protocol.crc_size > 0:
                fields.append((
                    f"CRC-{self._protocol.crc_size*8}",
                    self._protocol.crc_size,
                    "Pink",
                    f"CRC Checksum ({self._protocol.crc_size} bytes, type: {self._protocol.crc_type}, {self._protocol.crc_byte_order}-endian)"
                ))
            if self._protocol.footer:
                fields.append((
                    "Footer",
                    len(self._protocol.footer),
                    "Grey",
                    f"Frame Footer Hex: 0x{self._protocol.footer.hex().upper()}"
                ))

        self._tx_grid_widget = self._build_byte_grid(fields)
        self._tx_scroll_area.setWidget(self._tx_grid_widget)


