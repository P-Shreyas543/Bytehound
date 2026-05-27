"""UI-builder methods extracted from MainWindow as a mixin.

These methods construct the main window's widget tree, actions, menus,
toolbar and tabs. They run once during ``MainWindow.__init__`` and are
purely constructive — every attribute they assign (``self._led_label``,
``self._table``, ``self._console``, ``self._tx_command_combo``…) is read
by the rest of MainWindow / its other mixins, so the mixin only makes
sense as part of MainWindow's MRO.

Module-level helpers (``_icon``, palette constants, etc.) are imported
late from ``main_window`` to break the import cycle — ``main_window`` defines
those helpers above its mixin imports, so by the time this module is
loaded they exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QFont, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover - optional dep
    pg = None

try:
    import qdarktheme
except ImportError:  # pragma: no cover
    qdarktheme = None

from .plot_panel import GRID_LAYOUTS
from .telemetry_model import TelemetryTableModel, COLUMNS as _MODEL_COLUMNS
from .widgets import (
    _BTN_GREEN,
    _BTN_PINK,
    _BTN_YELLOW,
    _CheckableGroupCombo,
    _StatusBadgeDelegate,
    _icon,
    _pad_dock_content,
)


class WarningBadge(QLabel):
    """Subclass of QLabel that dismisses/hides itself when clicked."""
    def mousePressEvent(self, event) -> None:
        self.setVisible(False)
        super().mousePressEvent(event)


class UIBuildersMixin:
    """MainWindow mixin holding _build_ui and tab/menu/toolbar builders."""

    def _build_ui(self) -> None:
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_main_layout()

        self._led_label = QLabel("⬤")
        self._led_label.setStyleSheet("color: #ef5350;")
        self._led_label.setToolTip("Disconnected")
        self._status_label = QLabel("")
        
        self._warning_badge = WarningBadge("⚠️ Queue Saturated")
        self._warning_badge.setStyleSheet(
            "background-color: #F59E0B; color: #000000; font-weight: bold; padding: 2px 6px; border-radius: 4px; font-size: 8pt;"
        )
        self._warning_badge.setToolTip("TX Queue or Raw Log Queue is saturated. Commands/logs are being dropped. Click to dismiss.")
        self._warning_badge.setCursor(Qt.PointingHandCursor)
        self._warning_badge.setVisible(False)

        self._counts_label = QLabel("")
        self._counts_label.setFont(QFont("Consolas", 9))
        self._counts_label.setStyleSheet("padding: 0 8px; letter-spacing: 0.5px;")
        bar = QStatusBar(self)
        bar.addWidget(self._led_label)
        bar.addWidget(self._status_label, 1)
        bar.addPermanentWidget(self._warning_badge)
        bar.addPermanentWidget(self._counts_label)
        self.setStatusBar(bar)

        # Subtle "card" styling for compact panels + dock + primary action.
        # Pick the right QSS set based on the saved theme preference.
        _saved_theme = str(self._settings.value("ui/theme", "dark"))
        self._apply_card_qss(_saved_theme)

    def _build_actions(self) -> None:

        # All action icons follow the active theme tint. Primary actions
        # (Connect / Poll / Log) live in BOTH the toolbar (on a coloured
        # button background) AND the Device menu (on the regular menu
        # background), so a fixed white tint that looked great on the
        # toolbar made the same icons invisible in the Device menu under
        # light theme. The theme-tinted icon is readable in both contexts:
        #   dark menu bg + white icon  -> good
        #   light menu bg + dark icon  -> good
        #   green/yellow/pink button + white-or-dark icon -> still readable
        #     because the button colours are saturated (high contrast both ways).
        from .theming import resolve_theme
        _saved_theme = str(self._settings.value("ui/theme", "dark"))
        _ic = "#F8FAFC" if resolve_theme(_saved_theme) == "dark" else "#1F2937"

        # Keyboard shortcuts are passed to setShortcut() so Qt automatically
        # renders them in the menu text (right-aligned) — users learn them by
        # opening the menu once. We avoid Ctrl+R because earlier builds bound
        # it to "Auto-Range Plot"; some users still hit it out of habit.
        self._connect_action = QAction(_icon("mdi6.usb-port", _ic), "Connect", self)
        self._connect_action.setShortcut(QKeySequence("F9"))
        self._connect_action.triggered.connect(self._on_toggle_connect)

        self._polling_action = QAction(_icon("mdi6.play-circle-outline", _ic), "Start Auto-Fetch", self)
        self._polling_action.setCheckable(True)
        self._polling_action.setChecked(False)
        self._polling_action.setShortcut(QKeySequence("F10"))
        self._polling_action.triggered.connect(self._on_toggle_polling)

        self._logging_action = QAction(_icon("mdi6.record-rec", _ic), "Start Logging", self)
        self._logging_action.setShortcut("Ctrl+L")
        self._logging_action.triggered.connect(self._on_toggle_logging)

        self._load_config_action = QAction(_icon("mdi6.file-import-outline", _ic), "Import Config", self)
        self._load_config_action.setShortcut(QKeySequence("Ctrl+O"))
        self._load_config_action.triggered.connect(self._on_load_config)

        self._export_template_action = QAction(_icon("mdi6.file-export-outline", _ic), "Export Template", self)
        self._export_template_action.setShortcut(QKeySequence("Ctrl+E"))
        self._export_template_action.triggered.connect(self._on_export_template)

        self._clear_action = QAction(_icon("mdi6.broom", _ic), "Clear Console / Log", self)
        self._clear_action.setShortcut(QKeySequence("Ctrl+K"))
        self._clear_action.triggered.connect(self._on_clear)

        self._copy_value_action = QAction(_icon("mdi6.content-copy", _ic), "Copy Value", self)
        self._copy_value_action.setShortcut("Ctrl+Shift+C")
        self._copy_value_action.triggered.connect(self._on_copy_value)

        self._copy_table_action = QAction(_icon("mdi6.table-arrow-right", _ic), "Copy Table Snapshot", self)
        self._copy_table_action.setShortcut("Ctrl+Shift+T")
        self._copy_table_action.triggered.connect(self._on_copy_table)

        self._exit_action = QAction(_icon("mdi6.exit-to-app", _ic), "Exit", self)
        self._exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._exit_action.triggered.connect(self.close)

        self._info_action = QAction(_icon("mdi6.information-outline", _ic), "About Bytehound", self)
        self._info_action.triggered.connect(self._on_info)

        self._docs_action = QAction(_icon("mdi6.book-open-page-variant-outline", _ic), "View Documentation", self)
        self._docs_action.setShortcut(QKeySequence("F1"))
        self._docs_action.triggered.connect(self._on_view_docs)

        self._update_action = QAction(_icon("mdi6.cloud-download-outline", _ic), "Check for Updates", self)
        self._update_action.triggered.connect(self._on_check_updates)

        # Triage helper — copies version, OS, Qt, config + recent log lines
        # to the clipboard so bug reporters can paste a complete picture in
        # one step. Avoids the back-and-forth of "what version are you on?
        # what OS? can you find the log file?".
        self._diagnostics_action = QAction(_icon("mdi6.clipboard-text-outline", _ic), "Copy Diagnostics", self)
        self._diagnostics_action.triggered.connect(self._on_copy_diagnostics)

        # chart-multiple distinguishes the offline "Analysis Suite" (which
        # overlays many recordings) from the Live Plot panel which uses
        # plain chart-line.
        self._analysis_action = QAction(_icon("mdi6.chart-multiple", _ic), "Analysis Suite", self)
        self._analysis_action.setShortcut(QKeySequence("Ctrl+T"))
        self._analysis_action.triggered.connect(self._on_analysis_suite)

        self._logging_settings_action = QAction(_icon("mdi6.tune-vertical", _ic), "Logging Settings...", self)
        self._logging_settings_action.triggered.connect(self._on_logging_settings)

        self._plot_settings_action = QAction(_icon("mdi6.chart-line", _ic), "Plot Settings...", self)
        self._plot_settings_action.triggered.connect(self._on_plot_settings)

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
        file_menu.addAction(self._exit_action)
        _add_sep()

        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self._copy_value_action)
        edit_menu.addAction(self._copy_table_action)
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
        tools_menu.addAction(self._logging_settings_action)
        tools_menu.addAction(self._plot_settings_action)
        _add_sep()

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._docs_action)
        help_menu.addAction(self._update_action)
        help_menu.addAction(self._diagnostics_action)
        help_menu.addSeparator()
        help_menu.addAction(self._info_action)

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

        self.addToolBar(toolbar)

    def _promote_dock_to_window(self, dock, floating: bool) -> None:
        """Give every floated QDockWidget the OS minimize/maximize controls.

        Qt's default floating mode for QDockWidget paints only a thin tool
        title bar (float-toggle + close). On Windows that hides the standard
        ``— ▢ ✕`` control trio, so users can't maximise a popped-out dock
        onto a second monitor or minimise it independently of the main
        window. Promoting it to a real ``Qt.Window`` with full chrome on
        float, and letting Qt revert chrome on re-dock, fixes both. Wired
        uniformly for every dock (Live Plot, Bitfields, Enums, TX Commands,
        Parameter Editor, Raw Console, Activity Log) in
        ``_build_main_layout``.
        """
        if floating:
            dock.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowSystemMenuHint
                | Qt.WindowType.WindowMinMaxButtonsHint
                | Qt.WindowType.WindowCloseButtonHint
            )
            # setWindowFlags hides the widget; re-show to apply the new chrome.
            dock.show()

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
        self._status_delegate = _StatusBadgeDelegate(self._table, settings=self._settings)
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

        self._group_combo = _CheckableGroupCombo(center_widget)
        self._group_combo.selection_changed.connect(self._apply_group_filter)

        self._show_calcs_check = QCheckBox("Show calculations", center_widget)
        self._show_calcs_check.setChecked(True)
        self._show_calcs_check.toggled.connect(self._apply_group_filter)

        self._search_input.textChanged.connect(self._apply_group_filter)

        top_row.addWidget(self._search_input, 1)
        top_row.addWidget(QLabel("Group", center_widget))
        top_row.addWidget(self._group_combo)
        top_row.addWidget(self._show_calcs_check)

        # Config/logging status labels — kept as hidden attributes so
        # _refresh_config_status / logging helpers can still update their text.
        # Visible via View → Config Info...
        self._config_label = QLabel("No config loaded")
        self._protocol_label = QLabel("-")
        self._frames_label = QLabel("-")
        self._logging_label = QLabel("Logging: stopped")
        self._open_log_btn = QPushButton("\U0001f4c2")
        self._open_log_btn.setToolTip("Open Log Folder")
        self._open_log_btn.clicked.connect(self._on_open_log_folder)

        center_layout.addLayout(top_row)
        center_layout.addWidget(self._table)

        # Two-page stack: empty-state for first launch / no config loaded,
        # full table view once a config is present. _refresh_action_state
        # flips the page so the swap is automatic on load + on disconnect.
        self._central_stack = QStackedWidget(self)
        self._central_stack.addWidget(self._build_empty_state())  # index 0
        self._central_stack.addWidget(center_widget)               # index 1
        self.setCentralWidget(self._central_stack)

        # Connection dock REMOVED — Connect button opens ConnectionDialog popup.
        # Poll Configure accessible via Device menu.
        # Config/logging status shown in the central info bar.

        # ── Right column: tabbed panels (top) ─────────────────────────────
        self._plot_dock = QDockWidget("Live Plot", self)
        self._plot_dock.setObjectName("PlotDock")
        self._plot_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._plot_dock.setWidget(self._build_plot_tab())
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._plot_dock)

        self._bitfields_dock = QDockWidget("Bitfields", self)
        self._bitfields_dock.setObjectName("BitfieldsDock")
        self._bitfields_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._bitfields_dock.setWidget(self._build_bitfield_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._bitfields_dock)

        self._enums_dock = QDockWidget("Enums", self)
        self._enums_dock.setObjectName("EnumsDock")
        self._enums_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._enums_dock.setWidget(self._build_enum_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._enums_dock)
        self.tabifyDockWidget(self._bitfields_dock, self._enums_dock)

        self._tx_dock = QDockWidget("TX Commands", self)
        self._tx_dock.setObjectName("TxDock")
        self._tx_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._tx_dock.setWidget(self._build_tx_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tx_dock)
        self.tabifyDockWidget(self._bitfields_dock, self._tx_dock)

        self._editor_dock = QDockWidget("Parameter Editor", self)
        self._editor_dock.setObjectName("EditorDock")
        self._editor_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._editor_dock.setWidget(self._build_editor_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._editor_dock)
        self.tabifyDockWidget(self._bitfields_dock, self._editor_dock)

        self._tx_dock.raise_()

        # Build the left-panel widgets (recent config combo, poll list, etc.)
        # without attaching them to a dock — they are accessed by other methods.
        self._build_left_panel()

        # ── Logs: bottom-right, split below the panel tabs ─────────────────
        self._console = QPlainTextEdit(self)
        self._console.setReadOnly(True)
        self._console.setPlaceholderText("Raw RX/TX frames will appear here...")
        self._console.setMaximumBlockCount(3000)
        self._console.setFont(QFont("Consolas", 10))

        self._console_dock = QDockWidget("Raw Console", self)
        self._console_dock.setObjectName("ConsoleDock")
        self._console_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        self._console_dock.setWidget(self._console)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._console_dock)

        self._activity_log = QPlainTextEdit(self)
        self._activity_log.setReadOnly(True)
        self._activity_log.setPlaceholderText("Application activity will appear here...")
        self._activity_log.setMaximumBlockCount(5000)
        self._activity_log.setFont(QFont("Consolas", 10))

        self._activity_dock = QDockWidget("Activity Log", self)
        self._activity_dock.setObjectName("ActivityDock")
        self._activity_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        self._activity_dock.setWidget(self._activity_log)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._activity_dock)
        self.tabifyDockWidget(self._console_dock, self._activity_dock)
        self._activity_dock.raise_()

        # NOTE: splitDockWidget is deferred to showEvent — Qt ignores it
        # during __init__ before the window geometry is finalised.


        for dock in (
            self._plot_dock,
            self._bitfields_dock,
            self._enums_dock,
            self._tx_dock,
            self._editor_dock,
            self._console_dock,
            self._activity_dock,
        ):
            _pad_dock_content(dock)
            # Every dock, when popped out, becomes a fully independent
            # top-level window with OS Min/Max/Restore chrome — see
            # _promote_dock_to_window for the rationale.
            dock.topLevelChanged.connect(
                lambda floating, d=dock: self._promote_dock_to_window(d, floating)
            )

        self._populate_view_menu()

    def _build_empty_state(self) -> QWidget:
        """Friendly first-run / no-config-loaded view shown in the central area.

        Orients new users in five seconds: a headline that names the
        missing prerequisite, a one-line explanation, and two buttons
        that invoke the most likely next actions (import a config, or
        export a blank template to fill out). Both buttons reuse the
        existing QActions so keyboard shortcuts and behaviour stay in
        lockstep with the menu/toolbar.
        """
        from .theming import resolve_theme
        _saved_theme = str(self._settings.value("ui/theme", "dark"))
        _ic = "#F8FAFC" if resolve_theme(_saved_theme) == "dark" else "#1F2937"

        outer = QWidget(self)
        outer.setObjectName("emptyState")
        v = QVBoxLayout(outer)
        v.setContentsMargins(40, 40, 40, 40)
        v.setSpacing(16)
        v.addStretch(1)

        # Decorative big icon — only shown if qtawesome is available
        # (_icon degrades to an empty QIcon if not). pixmap() handles
        # the empty case by simply producing a null pixmap (no crash).
        icon_label = QLabel(outer)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        big_icon = _icon("mdi6.import", _ic).pixmap(96, 96)
        if not big_icon.isNull():
            icon_label.setPixmap(big_icon)
            v.addWidget(icon_label)

        headline = QLabel("No configuration loaded", outer)
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Larger than ambient. Kept in pt so OS text-scaling works.
        headline.setStyleSheet("font-size: 16pt; font-weight: 600;")
        v.addWidget(headline)

        subtitle = QLabel(
            "Bytehound needs a frame-decoding config to know how to read "
            "your serial data.\nImport an existing config or export a blank "
            "template to fill out.",
            outer,
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 11pt;")
        v.addWidget(subtitle)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch(1)

        import_btn = QPushButton(
            _icon("mdi6.file-import-outline", _ic),
            "  Import Config…",
            outer,
        )
        import_btn.setMinimumHeight(36)
        import_btn.setMinimumWidth(180)
        import_btn.clicked.connect(self._load_config_action.trigger)
        buttons.addWidget(import_btn)

        template_btn = QPushButton(
            _icon("mdi6.file-export-outline", _ic),
            "  Export Template…",
            outer,
        )
        template_btn.setMinimumHeight(36)
        template_btn.setMinimumWidth(180)
        template_btn.clicked.connect(self._export_template_action.trigger)
        buttons.addWidget(template_btn)

        buttons.addStretch(1)
        v.addLayout(buttons)

        hint = QLabel(
            "Tip: also accessible from File → Import Config (Ctrl+O)",
            outer,
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setEnabled(False)
        hint.setStyleSheet("font-size: 10pt;")
        v.addWidget(hint)

        v.addStretch(2)
        return outer

    def _build_left_panel(self) -> None:
        """Initialise sidebar-only widgets (not visible anywhere in the UI).
        These attributes are read by _on_load_recent_config, _populate_polling_list, etc.
        """
        self._recent_config_combo = QComboBox()
        self._recent_config_combo.setMinimumWidth(120)

        self._poll_status_label = QLabel("No targets loaded")
        self._poll_status_label.setWordWrap(True)

        self._polling_list = QListWidget()
        self._polling_list.setMaximumHeight(130)
        self._polling_list.setEnabled(False)

    def _build_plot_tab(self) -> QWidget:
        outer = QWidget(self)
        root_layout = QVBoxLayout(outer)
        # Outer margins are applied by _pad_dock_content on the dock host.
        root_layout.setSpacing(4)

        # ── Top control bar ────────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(8)

        hint = QLabel("Right-click a row → Add to Plot   ·   Space = Pause/Live")
        hint.setEnabled(False)
        hint.setStyleSheet("font-size: 9pt;")
        # Ignored horizontal policy lets the long hint text clip when the user
        # shrinks the window (e.g. snapping to a 50% screen split). Without
        # this, the label's full-text sizeHint forced the entire plot dock
        # — and therefore the MainWindow — wider than half a 1080p screen.
        hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        hint.setMinimumWidth(0)
        controls.addWidget(hint, 1)

        # Hover readout — shows time + value(s) under the mouse on any subplot.
        self._hover_label = QLabel("", outer)
        self._hover_label.setObjectName("hoverReadout")
        self._hover_label.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 9pt; padding: 0 6px;"
        )
        # 280px was the old minimum — too wide to fit a 50/50 split. The
        # readout content ("T+10s 3.45V") rarely needs more than ~150px;
        # let the label expand opportunistically up to its preferred width
        # but allow it to collapse on narrow windows.
        self._hover_label.setMinimumWidth(120)
        self._hover_label.setMaximumWidth(420)
        self._hover_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._hover_label.setToolTip("Time and signal values under the mouse cursor.")
        controls.addWidget(self._hover_label)

        controls.addWidget(QLabel("Layout:"))
        self._layout_combo = QComboBox(outer)
        self._layout_combo.addItems(list(GRID_LAYOUTS.keys()))
        saved_layout = str(self._settings.value("plot/layout", "2×1")).lower().replace("x", "×")
        self._layout_combo.setCurrentText(saved_layout if saved_layout in GRID_LAYOUTS else "2×1")
        self._layout_combo.currentTextChanged.connect(self._on_layout_changed)
        controls.addWidget(self._layout_combo)

        controls.addWidget(QLabel("Time:"))
        self._time_mode_combo = QComboBox(outer)
        self._time_mode_combo.addItems(["Elapsed", "Clock"])
        self._time_mode_combo.setCurrentIndex(0 if self._plot_time_mode == "elapsed" else 1)
        self._time_mode_combo.setToolTip("Elapsed (mm:ss) or wall-clock (HH:MM:SS) axis labels.")
        self._time_mode_combo.currentIndexChanged.connect(self._on_plot_time_mode_changed)
        controls.addWidget(self._time_mode_combo)

        # Sliding display window. Samples are always retained in full
        # (TimeSeriesBuffer keeps every value since session start);
        # this selector only changes how much of the history is shown.
        controls.addWidget(QLabel("Window:"))
        # Options entries are (short_label, full_label, seconds_or_None).
        # The short label still drives the visible combo text; the full
        # label is the tooltip for each option.
        self._plot_window_options: list[tuple[str, str, "int | None"]] = [
            ("1m",  "Last 1 minute",   60),
            ("5m",  "Last 5 minutes",  5 * 60),
            ("10m", "Last 10 minutes", 10 * 60),
            ("30m", "Last 30 minutes", 30 * 60),
            ("1h",  "Last 1 hour",     60 * 60),
            ("2h",  "Last 2 hours",    2 * 60 * 60),
            ("All", "All session",     None),
        ]
        current_secs = self._plot_window_seconds
        selected_idx = next(
            (i for i, (_, _, s) in enumerate(self._plot_window_options) if s == current_secs),
            1,  # default: 5m
        )
        self._plot_window_combo = QComboBox(outer)
        self._plot_window_combo.setFixedHeight(24)
        self._plot_window_combo.setStyleSheet(
            "QComboBox { font-size: 9pt; padding: 0 6px; min-width: 70px; }"
        )
        for short, full, _seconds in self._plot_window_options:
            # Show the short label in the combo itself, and set the full description
            # as a tooltip on the item. This keeps the combo box very narrow
            # to prevent layout clipping while preserving the descriptive text.
            self._plot_window_combo.addItem(short)
            self._plot_window_combo.setItemData(self._plot_window_combo.count() - 1, full, Qt.ItemDataRole.ToolTipRole)
        self._plot_window_combo.setCurrentIndex(selected_idx)
        self._plot_window_combo.setToolTip(
            "How much history to show in Live mode. "
            "All samples are kept in memory regardless of this setting."
        )
        self._plot_window_combo.currentIndexChanged.connect(self._on_plot_window_changed)
        controls.addWidget(self._plot_window_combo)

        # Unified tri-state plot button: Live / Explore / Paused. The button
        # face always shows the current state; clicking transitions according
        # to a state machine documented on _on_plot_state_btn_clicked. Replaces
        # the previous two-button Pause + mode-indicator pair, which had
        # confusing semantic overlap (both showed "what state is the plot in"
        # but only one was clickable in each direction).
        self._plot_state_btn = QPushButton("⏵ Live", outer)
        self._plot_state_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plot_state_btn.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self._plot_state_btn.clicked.connect(self._on_plot_state_btn_clicked)
        controls.addWidget(self._plot_state_btn)

        self._trigger_btn = QPushButton("Trigger...", outer)
        self._trigger_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._trigger_btn.setToolTip("Configure auto-pause trigger")
        self._trigger_btn.clicked.connect(self._on_plot_trigger_clicked)
        controls.addWidget(self._trigger_btn)

        # Session clock — updates every second via _flush_ui
        self._session_clock_label = QLabel("⏱ 0:00:00", outer)
        self._session_clock_label.setObjectName("auxReadout")
        self._session_clock_label.setToolTip("Elapsed time since session start (or last config load).")
        # Explicit per-theme colours come from the cascaded card QSS (QLabel#auxReadout
        # rule in _QSS_DARK_OVERRIDES / _QSS_LIGHT_OVERRIDES) so theme switches are
        # crisp. Previous palette(placeholderText) approach cached the resolved
        # colour on first paint and stayed stale after a qdarktheme palette swap.
        self._session_clock_label.setStyleSheet("font-size:9pt; padding-left:8px;")
        self._session_clock_label.setMinimumWidth(70)
        controls.addWidget(self._session_clock_label)

        # Update-rate readout — packets/sec coming in. Computed by _flush_ui.
        self._rate_label = QLabel("0 Hz", outer)
        self._rate_label.setObjectName("auxReadout")
        self._rate_label.setStyleSheet("font-size:9pt; padding-left:8px;")
        self._rate_label.setMinimumWidth(50)
        self._rate_label.setToolTip("Incoming packet rate (averaged over the last second).")
        controls.addWidget(self._rate_label)

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
        # GraphicsLayoutWidget has no intrinsic minimum size, so without
        # this the layout would happily squash it to 0 when the dock
        # shrinks. 80 px keeps at least one curve visible without forcing
        # the dock to be tall — users can still drag the splitter down or
        # undock/float the panel freely.
        self._gl_widget.setMinimumHeight(80)
        # The pyqtgraph canvas is not a QWidget child so qdarktheme does not
        # paint it; we tint it explicitly per theme. Re-applied on every
        # theme switch by _apply_plot_theme().
        self._apply_plot_theme(str(self._settings.value("ui/theme", "dark")))
        root_layout.addWidget(self._gl_widget, 1)

        # Build the initial grid from saved (or default) layout
        rows, cols = GRID_LAYOUTS.get(self._layout_combo.currentText(), (2, 1))
        self._rebuild_plot_grid(rows, cols, restore=True)
        self._set_plot_live(self._plot_live)

        return outer

    def _build_bitfield_tab(self) -> QWidget:
        outer = QWidget(self)
        v = QVBoxLayout(outer)
        v.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("Group:", outer))
        self._bitfield_group_combo = _CheckableGroupCombo(outer)
        self._bitfield_group_combo.selection_changed.connect(self._apply_bitfield_group_filter)
        bar.addWidget(self._bitfield_group_combo, 1)
        v.addLayout(bar)

        self._bitfield_table = QTableWidget(0, 4, outer)
        self._bitfield_table.setHorizontalHeaderLabels(["Frame", "Variable", "Bit", "State"])
        self._bitfield_table.verticalHeader().setVisible(False)
        self._bitfield_table.horizontalHeader().setStretchLastSection(True)
        # Side index: key_text -> row, kept in sync with the table by
        # _upsert_detail_row and reset alongside _bitfield_table.setRowCount(0)
        # in _on_clear. Turns the previous O(rows) linear scan per signal
        # into O(1) — matters at high frame rates where every decoded packet
        # may touch the same bitfield rows.
        self._bitfield_row_index: Dict[str, int] = {}
        # Parallel cache: last values tuple per key. Used by _upsert_detail_row
        # to skip the entire Qt write when the row's values haven't changed.
        # Bitfield ON/OFF stays stable packet-to-packet for most bits.
        self._bitfield_last_values: Dict[str, tuple[str, ...]] = {}
        v.addWidget(self._bitfield_table, 1)
        return outer

    def _build_enum_tab(self) -> QWidget:
        outer = QWidget(self)
        v = QVBoxLayout(outer)
        v.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("Group:", outer))
        self._enum_group_combo = _CheckableGroupCombo(outer)
        self._enum_group_combo.selection_changed.connect(self._apply_enum_group_filter)
        bar.addWidget(self._enum_group_combo, 1)
        v.addLayout(bar)

        self._enum_table = QTableWidget(0, 4, outer)
        self._enum_table.setHorizontalHeaderLabels(["Frame", "Variable", "Raw", "Label"])
        self._enum_table.verticalHeader().setVisible(False)
        self._enum_table.horizontalHeader().setStretchLastSection(True)
        # See _bitfield_row_index — same pattern for the enum table.
        self._enum_row_index: Dict[str, int] = {}
        self._enum_last_values: Dict[str, tuple[str, ...]] = {}
        v.addWidget(self._enum_table, 1)
        return outer

    def _build_editor_tab(self) -> QWidget:
        outer = QWidget(self)
        vlay = QVBoxLayout(outer)
        vlay.setSpacing(4)

        info = QLabel(
            "🔒 Only signals marked  read–write (RW) or write-only (W)  in the config "
            "appear here. Connect to write a new value."
        )
        info.setObjectName("hintLabel")
        info.setWordWrap(True)
        info.setStyleSheet("font-size:9pt; padding-bottom:4px;")
        vlay.addWidget(info)

        self._editor_table = QTableWidget(0, 4, outer)
        self._editor_table.setHorizontalHeaderLabels(
            ["Frame ID", "Signal", "Live Value", "Write"]
        )
        self._editor_table.verticalHeader().setVisible(False)
        hdr = self._editor_table.horizontalHeader()
        hdr.setSectionResizeMode(0, hdr.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, hdr.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, hdr.ResizeMode.Stretch)
        self._editor_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._editor_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        vlay.addWidget(self._editor_table)
        return outer

