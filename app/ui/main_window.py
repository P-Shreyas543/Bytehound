"""PySide6 main window for the Serial monitor."""

from __future__ import annotations

import os
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Optional, Tuple

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, QObject, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QPixmap, QFont, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover - exercised only when optional dep missing
    pg = None

try:
    import qdarktheme
except ImportError:  # pragma: no cover
    qdarktheme = None

APP_ORG = "Decibels"
APP_NAME = "Serial-MonitorApp"
APP_DISPLAY_NAME = "Serial Monitor"

from .updater import UpdateChecker, UpdateDownloader, launch_installer
from ..commands.tx_command_builder import CommandBuildError, build_tx_command
from ..decoder.config_loader import ConfigError, load_config
from ..decoder.frame_decoder import DecodedFrame, DecodedSignal, decode_frame
from ..decoder.template_io import export_excel_template, snapshot_config
from ..decoder.types import FrameConfig
from ..serial_logging.decoded_logger import DecodedLogger
from ..serial_logging.raw_logger import RawLogger
from ..protocol.packet_parser import create_parser, ParserProtocol, ParsedPacket
from ..serial_io.replay_source import parse_log_file, replay_bytes
from ..serial_io.serial_worker import SerialSettings, PollingWorker, available_ports

class OutputLogger(QObject):
    emit_text = Signal(str)

    def write(self, text):
        if text.strip():
            self.emit_text.emit(text.strip())

    def flush(self):
        pass


_COLUMNS = (
    ("Frame", 130),
    ("Group", 90),
    ("Variable", 190),
    ("Index", 55),
    ("Raw", 95),
    ("Value", 95),
    ("Unit", 70),
    ("Status", 190),
    ("Updated", 110),
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1400, 820)

        self._config: Optional[FrameConfig] = None
        self._config_path: Optional[Path] = None
        self._parser: Optional[ParserProtocol] = None
        self._serial: Optional[PollingWorker] = None
        self._delta_t_ms = 0.0
        self._row_index: Dict[Tuple[int, str], int] = {}
        self._packet_count = 0
        self._error_count = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._logging = False
        self._raw_logger: Optional[RawLogger] = None
        self._decoded_logger: Optional[DecodedLogger] = None
        self._settings = QSettings(APP_ORG, APP_NAME)
        self._tx_field_inputs: Dict[str, QLineEdit] = {}

        # Timer removed; using PollingWorker QThread

        self._plot_history: Dict[Tuple[int, str], Deque[Tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=1500)
        )
        self._session_started = datetime.now()

        self._build_ui()
        
        self._stdout_logger = OutputLogger()
        self._stdout_logger.emit_text.connect(self._append_to_console)
        sys.stdout = self._stdout_logger
        self._stderr_logger = OutputLogger()
        self._stderr_logger.emit_text.connect(self._append_to_console)
        sys.stderr = self._stderr_logger
        
        self._load_default_config()
        self._refresh_ports()
        self._refresh_action_state()

        self._default_state = self.saveState()
        self._default_geometry = self.saveGeometry()
        self._restore_window_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_main_layout()

        self._led_label = QLabel("⬤")
        self._led_label.setStyleSheet("color: red;")
        self._led_label.setToolTip("Disconnected")
        self._status_label = QLabel("")
        self._counts_label = QLabel("")
        bar = QStatusBar(self)
        bar.addWidget(self._led_label)
        bar.addWidget(self._status_label, 1)
        bar.addPermanentWidget(self._counts_label)
        self.setStatusBar(bar)

        # Subtle "card" styling for compact panels.
        self.setStyleSheet(
            (self.styleSheet() or "")
            + "\n"
            + """
            QFrame[card=\"true\"] {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 10px;
            }
            QLabel[cardTitle=\"true\"] {
                font-weight: 600;
            }
            """
        )

    def _build_actions(self) -> None:
        self._port_combo = QComboBox(self)
        self._port_combo.setMinimumWidth(130)
        self._baud_combo = QComboBox(self)
        self._baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self._baud_combo.setCurrentText("115200")

        self._connect_action = QAction("Connect", self)
        self._connect_action.triggered.connect(self._on_toggle_connect)

        self._polling_action = QAction("Start Polling", self)
        self._polling_action.setCheckable(True)
        self._polling_action.setChecked(True)
        self._polling_action.triggered.connect(self._on_toggle_polling)

        self._polling_action = QAction("Start Polling", self)
        self._polling_action.setCheckable(True)
        self._polling_action.setChecked(True)
        self._polling_action.triggered.connect(self._on_toggle_polling)

        self._logging_action = QAction("Start Logging", self)
        self._logging_action.triggered.connect(self._on_toggle_logging)

        self._load_config_action = QAction("Import Config", self)
        self._load_config_action.triggered.connect(self._on_load_config)

        self._export_template_action = QAction("Export Template", self)
        self._export_template_action.triggered.connect(self._on_export_template)

        self._load_log_action = QAction("Load Raw Log", self)
        self._load_log_action.triggered.connect(self._on_load_log)

        self._clear_action = QAction("Clear", self)
        self._clear_action.triggered.connect(self._on_clear)

        self._exit_action = QAction("Exit", self)
        self._exit_action.triggered.connect(self.close)

        self._info_action = QAction("Info", self)
        self._info_action.triggered.connect(self._on_info)
        
        self._docs_action = QAction("View Documentation", self)
        self._docs_action.triggered.connect(self._on_view_docs)

        self._update_action = QAction("Check for Updates", self)
        self._update_action.triggered.connect(self._on_check_updates)

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._load_config_action)
        file_menu.addAction(self._export_template_action)
        file_menu.addSeparator()
        file_menu.addAction(self._load_log_action)
        file_menu.addAction(self._logging_action)
        file_menu.addSeparator()
        file_menu.addAction(self._exit_action)

        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self._clear_action)

        self._view_menu = menubar.addMenu("&View")
        self._panels_menu = menubar.addMenu("&Panels")

        run_menu = menubar.addMenu("&Run")
        run_menu.addAction(self._connect_action)

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._update_action)
        help_menu.addAction(self._docs_action)
        help_menu.addAction(self._info_action)

    def _on_check_updates(self) -> None:
        self._update_checker = UpdateChecker()
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.up_to_date.connect(lambda: QMessageBox.information(self, "Updater", "You are on the latest version."))
        self._update_checker.error.connect(lambda e: QMessageBox.warning(self, "Updater", f"Failed to check for updates:\n{e}"))
        self._update_checker.start()
        self._set_status("Checking for updates...")

    def _on_update_available(self, version: str, url: str, release_notes: str) -> None:
        reply = QMessageBox.question(
            self,
            "Update Available",
            f"Version {version} is available.\n\nNotes:\n{release_notes}\n\nWould you like to download and install it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_update(url)

    def _download_update(self, url: str) -> None:
        self._progress = QProgressDialog("Downloading update...", "Cancel", 0, 100, self)
        self._progress.setWindowTitle("Updater")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.show()

        dest_path = str(Path(os.environ.get("TEMP", ".")) / f"{APP_NAME}_Update.exe")
        self._downloader = UpdateDownloader(url, dest_path)
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(lambda e: QMessageBox.critical(self, "Updater Error", f"Download failed:\n{e}"))
        self._progress.canceled.connect(self._downloader.requestInterruption)
        self._downloader.start()

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        self._progress.setMaximum(total)
        self._progress.setValue(downloaded)

    def _on_download_finished(self, dest_path: str) -> None:
        self._progress.close()
        reply = QMessageBox.question(
            self,
            "Update Ready",
            "Download complete. Install now? The application will restart.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            launch_installer(dest_path)

    def _on_info(self) -> None:
        QMessageBox.about(
            self,
            "Info",
            f"{APP_DISPLAY_NAME} App\n\n"
            "Version: 0.1.0\n"
            "Publisher: Decibels\n"
            "Build Date: May 2026\n"
            "Website: https://lms.decibelslab.com/\n\n"
            "Serial Data Logger and Visualizer.\n"
            "Configuration-driven decoding."
        )

    def _on_view_docs(self) -> None:
        docs_path = Path(__file__).resolve().parents[1] / "resources" / "index.html"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(docs_path)))

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        self._toolbar = toolbar

        toolbar.addAction(self._load_config_action)
        toolbar.addAction(self._export_template_action)
        toolbar.addSeparator()
        toolbar.addAction(self._load_log_action)
        toolbar.addAction(self._logging_action)
        toolbar.addSeparator()
        toolbar.addAction(self._connect_action)
        toolbar.addSeparator()
        toolbar.addAction(self._polling_action)
        toolbar.addSeparator()
        toolbar.addAction(self._polling_action)
        
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self._logo_button = QPushButton()
        self._logo_button.setIcon(QIcon(str(Path(__file__).resolve().parents[2] / "logo_rec.png")))
        self._logo_button.setFlat(True)
        self._logo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logo_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://lms.decibelslab.com/")))
        toolbar.addWidget(self._logo_button)

        self.addToolBar(toolbar)

    def _build_main_layout(self) -> None:
        self.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)

        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels([column[0] for column in _COLUMNS])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setFont(QFont("Consolas", 10))
        for index, (_, width) in enumerate(_COLUMNS):
            self._table.setColumnWidth(index, width)

        center_widget = QWidget(self)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(8, 8, 8, 8)

        top_row = QHBoxLayout()
        self._search_input = QLineEdit(center_widget)
        self._search_input.setPlaceholderText("Search / Filter variables...")

        self._group_combo = QComboBox(center_widget)
        self._group_combo.addItem("All")
        self._group_combo.setMinimumWidth(150)
        self._group_combo.currentTextChanged.connect(self._apply_group_filter)

        self._show_calcs_check = QCheckBox("Show calculations", center_widget)
        self._show_calcs_check.setChecked(True)
        self._show_calcs_check.toggled.connect(lambda: self._apply_group_filter(self._group_combo.currentText()))

        self._search_input.textChanged.connect(lambda: self._apply_group_filter(self._group_combo.currentText()))

        top_row.addWidget(self._search_input, 1)
        top_row.addWidget(QLabel("Group", center_widget))
        top_row.addWidget(self._group_combo)
        top_row.addWidget(self._show_calcs_check)

        center_layout.addLayout(top_row)
        center_layout.addWidget(self._table)
        
        self.setCentralWidget(center_widget)

        self._settings_dock = QDockWidget("Settings", self)
        self._settings_dock.setObjectName("SettingsDock")
        self._settings_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._settings_dock.setWidget(self._build_left_panel())
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._settings_dock)

        self._plot_dock = QDockWidget("Live Plot", self)
        self._plot_dock.setObjectName("PlotDock")
        self._plot_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._plot_dock.setWidget(self._build_plot_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._plot_dock)

        self._bitfields_dock = QDockWidget("Bitfields", self)
        self._bitfields_dock.setObjectName("BitfieldsDock")
        self._bitfields_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._bitfields_dock.setWidget(self._build_bitfield_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._bitfields_dock)
        self.tabifyDockWidget(self._plot_dock, self._bitfields_dock)

        self._enums_dock = QDockWidget("Enums", self)
        self._enums_dock.setObjectName("EnumsDock")
        self._enums_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._enums_dock.setWidget(self._build_enum_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._enums_dock)
        self.tabifyDockWidget(self._plot_dock, self._enums_dock)

        self._tx_dock = QDockWidget("TX Commands", self)
        self._tx_dock.setObjectName("TxDock")
        self._tx_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._tx_dock.setWidget(self._build_tx_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tx_dock)
        self.tabifyDockWidget(self._plot_dock, self._tx_dock)

        self._editor_dock = QDockWidget("Parameter Editor", self)
        self._editor_dock.setObjectName("EditorDock")
        self._editor_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self._editor_dock.setWidget(self._build_editor_tab())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._editor_dock)
        self.tabifyDockWidget(self._plot_dock, self._editor_dock)



        self._plot_dock.raise_()

        self._console = QPlainTextEdit(self)
        self._console.setReadOnly(True)
        self._console.setPlaceholderText("Raw RX/TX frames will appear here...")
        self._console.setMaximumBlockCount(3000)
        self._console.setFont(QFont("Consolas", 10))

        self._console_dock = QDockWidget("Raw Console", self)
        self._console_dock.setObjectName("ConsoleDock")
        self._console_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self._console_dock.setWidget(self._console)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._console_dock)

        self._activity_log = QPlainTextEdit(self)
        self._activity_log.setReadOnly(True)
        self._activity_log.setPlaceholderText("Application activity will appear here...")
        self._activity_log.setMaximumBlockCount(5000)
        self._activity_log.setFont(QFont("Consolas", 10))

        self._activity_dock = QDockWidget("Activity Log", self)
        self._activity_dock.setObjectName("ActivityDock")
        self._activity_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self._activity_dock.setWidget(self._activity_log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._activity_dock)
        self.tabifyDockWidget(self._console_dock, self._activity_dock)
        self._console_dock.raise_()

        self._populate_view_menu()
        self._populate_panels_menu()

    def _populate_view_menu(self) -> None:
        menu = self._view_menu
        menu.clear()

        theme_menu = menu.addMenu("Theme")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        current_theme = str(self._settings.value("ui/theme", "dark"))
        for label, key in (("Dark", "dark"), ("Light", "light"), ("System", "auto")):
            action = QAction(label, self, checkable=True)
            action.setData(key)
            action.setChecked(key == current_theme)
            action.triggered.connect(lambda _checked=False, k=key: self._apply_theme(k))
            self._theme_group.addAction(action)
            theme_menu.addAction(action)

        menu.addSeparator()

        reset_plot_action = QAction("Auto-Range Plot", self)
        reset_plot_action.setShortcut("Ctrl+R")
        reset_plot_action.triggered.connect(self._reset_plot_view)
        menu.addAction(reset_plot_action)

        reset_layout_action = QAction("Reset Window Layout", self)
        reset_layout_action.triggered.connect(self._reset_window_layout)
        menu.addAction(reset_layout_action)

    def _populate_panels_menu(self) -> None:
        menu = self._panels_menu
        menu.clear()

        toolbar_action = self._toolbar.toggleViewAction()
        toolbar_action.setText("Toolbar")
        menu.addAction(toolbar_action)

        menu.addSeparator()

        settings_action = self._settings_dock.toggleViewAction()
        settings_action.setText("Settings")
        menu.addAction(settings_action)

        analysis_menu = menu.addMenu("Analysis")
        for dock, label in (
            (self._plot_dock, "Live Plot"),
            (self._bitfields_dock, "Bitfields"),
            (self._enums_dock, "Enums"),
            (self._tx_dock, "TX Commands"),
            (self._editor_dock, "Parameter Editor"),
        ):
            action = dock.toggleViewAction()
            action.setText(label)
            analysis_menu.addAction(action)

        logs_menu = menu.addMenu("Logs")
        for dock, label in (
            (self._console_dock, "Raw Console"),
            (self._activity_dock, "Activity Log"),
        ):
            action = dock.toggleViewAction()
            action.setText(label)
            logs_menu.addAction(action)

    def _apply_theme(self, theme: str) -> None:
        if qdarktheme is None:
            return
        try:
            qdarktheme.setup_theme(theme, corner_shape="rounded")
        except Exception as exc:
            QMessageBox.warning(self, "Theme", f"Failed to apply theme: {exc}")
            return
        self._settings.setValue("ui/theme", theme)
        self._set_status(f"Theme: {theme}")

    def _reset_plot_view(self) -> None:
        if pg is None or self._plot_widget is None:
            return
        self._plot_widget.enableAutoRange()
        self._plot_widget.getPlotItem().getViewBox().autoRange()

    def _reset_window_layout(self) -> None:
        self.restoreGeometry(self._default_geometry)
        self.restoreState(self._default_state)
        for dock in (
            self._settings_dock,
            self._plot_dock,
            self._bitfields_dock,
            self._enums_dock,
            self._tx_dock,
            self._editor_dock,
            self._editor_dock,
            self._console_dock,
            self._activity_dock,
        ):
            dock.setVisible(True)
        self._toolbar.setVisible(True)

    def _save_window_state(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/state", self.saveState())

    def _restore_window_state(self) -> None:
        geometry = self._settings.value("window/geometry")
        state = self._settings.value("window/state")
        if geometry:
            self.restoreGeometry(geometry)
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

    def _build_left_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- Connection card -------------------------------------------------
        connection_card, connection_layout = self._card("Connection", panel)

        form_widget = QWidget(connection_card)
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 0, 0, 0)

        port_row = QWidget(form_widget)
        port_row_layout = QHBoxLayout(port_row)
        port_row_layout.setContentsMargins(0, 0, 0, 0)
        refresh_button = QPushButton("Refresh", port_row)
        refresh_button.clicked.connect(self._refresh_ports)
        port_row_layout.addWidget(self._port_combo, 1)
        port_row_layout.addWidget(refresh_button)

        self._data_bits_combo = QComboBox(form_widget)
        self._data_bits_combo.addItems(["8", "7"])
        self._stop_bits_combo = QComboBox(form_widget)
        self._stop_bits_combo.addItems(["1", "1.5", "2"])
        self._parity_combo = QComboBox(form_widget)
        self._parity_combo.addItems(["N", "E", "O"])
        self._timeout_combo = QComboBox(form_widget)
        self._timeout_combo.addItems(["20", "50", "100", "250", "500", "1000"])
        self._timeout_combo.setCurrentText("50")

        form.addRow("Port", port_row)
        form.addRow("Baud", self._baud_combo)
        form.addRow("Data bits", self._data_bits_combo)
        form.addRow("Stop bits", self._stop_bits_combo)
        form.addRow("Parity", self._parity_combo)
        form.addRow("Timeout ms", self._timeout_combo)
        connection_layout.addWidget(form_widget)

        self._connect_button = QPushButton(self._connect_action.text(), connection_card)
        self._connect_button.clicked.connect(self._on_toggle_connect)
        connection_layout.addWidget(self._connect_button)

        self._connection_label = QLabel("Serial: disconnected", connection_card)
        self._connection_label.setWordWrap(True)
        connection_layout.addWidget(self._connection_label)

        # --- Config/status card ---------------------------------------------
        status_card, status_layout = self._card("Config", panel)
        recent_row = QHBoxLayout()
        self._recent_config_combo = QComboBox(status_card)
        self._recent_config_combo.setMinimumWidth(120)
        recent_load = QPushButton("Load", status_card)
        recent_load.clicked.connect(self._on_load_recent_config)
        recent_row.addWidget(self._recent_config_combo, 1)
        recent_row.addWidget(recent_load)
        status_layout.addLayout(recent_row)

        self._config_label = QLabel("No config loaded", status_card)
        self._protocol_label = QLabel("-", status_card)
        self._frames_label = QLabel("-", status_card)
        self._logging_label = QLabel("Logging: stopped", status_card)
        for label in (
            self._config_label,
            self._protocol_label,
            self._frames_label,
            self._logging_label,
        ):
            label.setWordWrap(True)
            status_layout.addWidget(label)

        logging_row = QHBoxLayout()
        logging_row.addWidget(self._logging_label, 1)
        self._open_log_btn = QPushButton("📂")
        self._open_log_btn.setToolTip("Open Log Folder")
        self._open_log_btn.setFixedWidth(28)
        self._open_log_btn.clicked.connect(self._on_open_log_folder)
        logging_row.addWidget(self._open_log_btn)
        status_layout.addLayout(logging_row)

        layout.addWidget(connection_card)
        layout.addWidget(status_card)

        # --- Polling card ---
        polling_card, polling_layout = self._card("Active Polling", panel)
        self._polling_list = QListWidget(polling_card)
        self._polling_list.setMaximumHeight(150)
        self._polling_list.itemChanged.connect(self._on_polling_item_changed)
        polling_layout.addWidget(self._polling_list)
        layout.addWidget(polling_card)

        layout.addStretch(1)
        panel.setMinimumWidth(280)
        return panel

    def _build_plot_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        controls = QHBoxLayout()
        
        self._plot_variable_list = QListWidget(widget)
        self._plot_variable_list.setMaximumHeight(100)
        self._plot_variable_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._plot_variable_list.itemChanged.connect(self._redraw_plot)
        self._plot_variable_list.itemClicked.connect(self._toggle_plot_item)

        self._plot_window_combo = QComboBox(widget)
        self._plot_window_combo.addItems(["60", "120", "300", "600"])
        self._plot_window_combo.setCurrentText("300")
        self._plot_window_combo.currentIndexChanged.connect(self._redraw_plot)
        clear_plot = QPushButton("Clear", widget)
        clear_plot.clicked.connect(self._clear_plot)
        export_plot = QPushButton("Export", widget)
        export_plot.clicked.connect(self._export_plot_data)
        
        controls.addWidget(QLabel("Window s"))
        controls.addWidget(self._plot_window_combo)
        controls.addWidget(clear_plot)
        controls.addWidget(export_plot)
        controls.addStretch(1)

        layout.addWidget(QLabel("Select Variables to Plot:"))
        layout.addWidget(self._plot_variable_list)
        layout.addLayout(controls)

        self._plot_curves = {}

        if pg is not None:
            self._plot_widget = pg.PlotWidget(widget)
            self._plot_widget.setBackground(pg.mkColor("#1e1e1e"))
            self._plot_widget.showGrid(x=True, y=True, alpha=0.25)
            self._plot_widget.addLegend()
            
            # Setup interactive crosshairs
            self._vLine = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("w", style=Qt.PenStyle.DashLine))
            self._hLine = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("w", style=Qt.PenStyle.DashLine))
            self._plot_widget.addItem(self._vLine, ignoreBounds=True)
            self._plot_widget.addItem(self._hLine, ignoreBounds=True)
            
            self._proxy = pg.SignalProxy(self._plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._mouseMoved)
            
            layout.addWidget(self._plot_widget, 1)
        else:
            self._plot_widget = None
            layout.addWidget(QLabel("pyqtgraph is not installed.", widget), 1)
        return widget

    def _toggle_plot_item(self, item: QListWidgetItem) -> None:
        item.setCheckState(
            Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
        )

    def _mouseMoved(self, evt):
        if self._plot_widget is None:
            return
        pos = evt[0]
        if self._plot_widget.sceneBoundingRect().contains(pos):
            mousePoint = self._plot_widget.plotItem.vb.mapSceneToView(pos)
            self._vLine.setPos(mousePoint.x())
            self._hLine.setPos(mousePoint.y())

    def _build_bitfield_tab(self) -> QWidget:
        self._bitfield_table = QTableWidget(0, 4, self)
        self._bitfield_table.setHorizontalHeaderLabels(["Frame", "Variable", "Bit", "State"])
        self._bitfield_table.verticalHeader().setVisible(False)
        self._bitfield_table.horizontalHeader().setStretchLastSection(True)
        return self._bitfield_table

    def _build_enum_tab(self) -> QWidget:
        self._enum_table = QTableWidget(0, 4, self)
        self._enum_table.setHorizontalHeaderLabels(["Frame", "Variable", "Raw", "Label"])
        self._enum_table.verticalHeader().setVisible(False)
        self._enum_table.horizontalHeader().setStretchLastSection(True)
        return self._enum_table

    
    def _build_editor_tab(self) -> QWidget:
        self._editor_table = QTableWidget(0, 4, self)
        self._editor_table.setHorizontalHeaderLabels(["Target ID", "Variable", "Current", "Action"])
        self._editor_table.verticalHeader().setVisible(False)
        self._editor_table.horizontalHeader().setStretchLastSection(True)
        return self._editor_table

    
    def _build_editor_tab(self) -> QWidget:
        self._editor_table = QTableWidget(0, 4, self)
        self._editor_table.setHorizontalHeaderLabels(["Target ID", "Variable", "Current", "Action"])
        self._editor_table.verticalHeader().setVisible(False)
        self._editor_table.horizontalHeader().setStretchLastSection(True)
        return self._editor_table

    def _build_tx_tab(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        self._tx_command_combo = QComboBox(widget)
        self._tx_command_combo.currentIndexChanged.connect(self._rebuild_tx_fields)
        self._tx_fields_widget = QWidget(widget)
        self._tx_fields_form = QFormLayout(self._tx_fields_widget)
        self._tx_preview = QPlainTextEdit(widget)
        self._tx_preview.setReadOnly(True)
        self._tx_preview.setMaximumHeight(90)
        build_button = QPushButton("Build", widget)
        build_button.clicked.connect(self._preview_tx_command)
        send_button = QPushButton("Send", widget)
        send_button.clicked.connect(self._send_tx_command)
        buttons = QHBoxLayout()
        buttons.addWidget(build_button)
        buttons.addWidget(send_button)
        layout.addWidget(QLabel("Command"))
        layout.addWidget(self._tx_command_combo)
        layout.addWidget(self._tx_fields_widget)
        layout.addLayout(buttons)
        layout.addWidget(QLabel("Packet Preview"))
        layout.addWidget(self._tx_preview)
        layout.addStretch(1)
        return widget

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
            QMessageBox.warning(self, "Config error", f"Unsupported config selection: {chosen.name}")
            return

        try:
            self._load_config_from_path(path)
        except ConfigError as exc:
            QMessageBox.critical(self, "Config error", str(exc))

    def _load_config_from_path(self, path: Path) -> None:
        self._config = load_config(path)
        self._config_path = path
        self._parser = create_parser(self._config.protocol)
        self._session_started = datetime.now()
        self._plot_history.clear()
        self._packet_count = 0
        self._error_count = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._console.clear()
        self._populate_table_from_config()
        self._populate_group_selector()
        self._populate_plot_selector()
        self._populate_tx_commands()
        self._populate_polling_list()
        self._populate_editor_table()
        self._apply_serial_defaults()
        self._refresh_config_status()
        self._remember_config(path)
        self._refresh_action_state()
        self._set_status(f"Loaded config from {path}")
        self._log_activity(f"Loaded config: {path}")

    def _on_load_recent_config(self) -> None:
        path_text = self._recent_config_combo.currentText()
        if not path_text:
            return
        try:
            self._load_config_from_path(Path(path_text))
        except ConfigError as exc:
            QMessageBox.critical(self, "Config error", str(exc))

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
        if self._config_path is None:
            QMessageBox.information(self, "Export template", "Load a config first.")
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export Excel template",
            str(Path.home() / "frame_config_template.xlsx"),
            "Excel workbook (*.xlsx)",
        )
        if not target:
            return
        try:
            export_excel_template(self._config_path, target)
        except Exception as exc:
            QMessageBox.critical(self, "Export template", str(exc))
            return
        self._set_status(f"Exported Excel template to {target}")

    def _on_load_log(self) -> None:
        if self._config is None or self._parser is None:
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select raw log file", "", "Log files (*.txt *.log);;All files (*)"
        )
        if not path_str:
            return

        rows, errors = parse_log_file(path_str)
        if errors:
            QMessageBox.warning(
                self,
                "Log parse warnings",
                f"{len(errors)} line(s) skipped:\n" + "\n".join(errors[:5]),
            )
        for chunk in replay_bytes(rows):
            self._rx_bytes += len(chunk)
            self._parser.feed(chunk)
        self._drain_parser()
        self._set_status(f"Replayed {len(rows)} log row(s) from {Path(path_str).name}")



    def _on_toggle_connect(self) -> None:
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
            self._serial = None
            self._set_connection_ui(False)
            self._set_status("Disconnected")
            self._log_activity("Disconnected")
            return

        if self._config is None:
            QMessageBox.warning(self, "Connect", "Please load a configuration first.")
            return

        settings = SerialSettings(
            port=self._port_combo.currentText(),
            baud_rate=int(self._baud_combo.currentText()),
            data_bits=int(self._data_bits_combo.currentText()),
            stop_bits=float(self._stop_bits_combo.currentText()),
            parity=self._parity_combo.currentText(),
            timeout_ms=int(self._timeout_combo.currentText()),
        )

        try:
            self._serial = PollingWorker(settings, self._config.protocol, self._config.polling_schedules)
            self._serial.packet_received.connect(self._on_packet_received)
            self._serial.metrics_updated.connect(self._on_metrics_updated)
            self._serial.error_occurred.connect(self._on_serial_error)
            self._serial.tx_recorded.connect(self._on_tx_recorded)
            self._serial.open()
            self._serial.set_polling_global(self._polling_action.isChecked())
            
            self._set_connection_ui(True)
            self._set_status(f"Connected to {settings.port}")
            self._log_activity(f"Connected to {settings.port} @ {settings.baud_rate}")
        except Exception as exc:
            self._serial = None
            QMessageBox.critical(self, "Connection Error", str(exc))

    def _on_serial_error(self, err: str) -> None:
        self._log_activity(f"Serial Error: {err}")
        self._set_status(f"Error: {err}")
        if self._serial:
            self._serial.close()
            self._serial = None
        self._set_connection_ui(False)

    def _on_packet_received(self, packet: ParsedPacket, delta_t_ms: float) -> None:
        self._delta_t_ms = delta_t_ms
        self._handle_packet(packet)

    def _on_metrics_updated(self, timeouts: int, crc: int, rx_bytes: int) -> None:
        self._rx_bytes = rx_bytes
        self._error_count = crc
        buffered = self._parser.buffered_bytes if self._parser else 0
        self._counts_label.setText(
            f"frames: {self._packet_count}   errors/crc: {self._error_count}   "
            f"timeouts: {timeouts}   "
            f"RX: {self._rx_bytes}B   TX: {self._tx_bytes}B   lat: {self._delta_t_ms:.1f}ms"
        )

    def _update_counts(self) -> None:
        if hasattr(self, "_counts_label"):
            self._counts_label.setText(
                f"frames: {self._packet_count}   errors/crc: {self._error_count}   "
                f"RX: {self._rx_bytes}B   TX: {self._tx_bytes}B   lat: {self._delta_t_ms:.1f}ms"
            )
        
    def _on_tx_recorded(self, packet: bytes) -> None:
        self._tx_bytes += len(packet)
        if self._raw_logger:
            self._raw_logger.log("TX", packet)
        self._console.appendPlainText(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, TX, {packet.hex(' ').upper()}")

    def _on_toggle_logging(self) -> None:
        if self._logging:
            self._stop_logging()
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

        default_dir = Path(os.path.expanduser("~")) / "Documents" / "Decibels" / APP_NAME
        default_dir.mkdir(parents=True, exist_ok=True)
        default_file = default_dir / "serial_log.csv"

        target, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            str(default_file),
            "CSV files (*.csv);;All files (*)",
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
            decoded_path = base.with_name(f"{base_stem}_decoded.csv")
        elif log_raw:
            raw_path = base.with_name(f"{base_stem}.csv")
        else:
            decoded_path = base.with_name(f"{base_stem}.csv")

        self._raw_logger = RawLogger(raw_path) if raw_path else None
        self._decoded_logger = DecodedLogger(decoded_path) if decoded_path else None

        if self._config_path is not None:
            snapshot_config(self._config_path, base.with_name(f"{base_stem}_session"))

        self._logging = True
        self._logging_action.setText("Stop Logging")

        label_parts = []
        if raw_path:
            label_parts.append(f"raw → {raw_path.name}")
        if decoded_path:
            label_parts.append(f"decoded → {decoded_path.name}")
        summary = ", ".join(label_parts)
        self._logging_label.setText(f"Logging: {summary}")
        self._set_status(f"Logging started ({choice}): {summary}")
        self._log_activity(f"Logging started ({choice}): {summary}")

    def _stop_logging(self) -> None:
        if self._raw_logger:
            self._raw_logger.close()
        if self._decoded_logger:
            self._decoded_logger.close()
        self._raw_logger = None
        self._decoded_logger = None
        self._logging = False
        self._logging_action.setText("Start Logging")
        self._logging_label.setText("Logging: stopped")
        self._set_status("Logging stopped")

    def _on_open_log_folder(self) -> None:
        default_dir = Path(os.path.expanduser("~")) / "Documents" / "Decibels" / APP_NAME
        if default_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(default_dir)))
        else:
            QMessageBox.information(self, "Logs", f"Log directory does not exist yet:\n{default_dir}")

    def _on_clear(self) -> None:
        self._console.clear()
        self._packet_count = 0
        self._error_count = 0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._plot_history.clear()
        self._bitfield_table.setRowCount(0)
        self._enum_table.setRowCount(0)
        for row in range(self._table.rowCount()):
            for col in (4, 5, 7, 8):
                self._table.setItem(row, col, QTableWidgetItem("-"))
        self._redraw_plot()
        self._update_counts()
        self._set_status("Cleared decoded values and console")

    def _populate_tx_commands(self) -> None:
        self._tx_command_combo.clear()
        self._tx_field_inputs.clear()
        if self._config is None:
            return
        self._tx_command_combo.addItems(sorted(self._config.tx_commands))
        self._rebuild_tx_fields()

    def _rebuild_tx_fields(self) -> None:
        while self._tx_fields_form.rowCount():
            self._tx_fields_form.removeRow(0)
        self._tx_field_inputs.clear()
        if self._config is None:
            return
        command = self._config.tx_commands.get(self._tx_command_combo.currentText())
        if command is None:
            return
        for field in command.fields:
            editor = QLineEdit(self._tx_fields_widget)
            if field.default is not None:
                editor.setText(f"{field.default:g}")
            suffix = f" ({field.unit})" if field.unit else ""
            self._tx_fields_form.addRow(f"{field.field_name}{suffix}", editor)
            self._tx_field_inputs[field.field_name] = editor
        self._preview_tx_command()

    def _tx_values(self) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for name, editor in self._tx_field_inputs.items():
            text = editor.text().strip()
            if text:
                values[name] = float(text)
        return values

    def _build_current_tx_packet(self) -> bytes:
        if self._config is None:
            raise CommandBuildError("No configuration loaded")
        return build_tx_command(
            self._config, self._tx_command_combo.currentText(), self._tx_values()
        )

    def _preview_tx_command(self) -> None:
        try:
            packet = self._build_current_tx_packet()
        except (CommandBuildError, ValueError) as exc:
            self._tx_preview.setPlainText(str(exc))
            return
        self._tx_preview.setPlainText(packet.hex(" ").upper())

    def _send_tx_command(self) -> None:
        try:
            packet = self._build_current_tx_packet()
        except (CommandBuildError, ValueError) as exc:
            QMessageBox.warning(self, "TX command", str(exc))
            return
        if self._serial is None or not self._serial.is_open:
            QMessageBox.warning(self, "TX command", "Connect a serial port before sending.")
            return
        written = self._serial.write(packet)
        self._tx_bytes += written
        if self._raw_logger:
            self._raw_logger.log("TX", packet)
        self._console.appendPlainText(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, TX, {packet.hex(' ').upper()}")
        self._update_counts()

    # ------------------------------------------------------------------
    # Data feed
    # ------------------------------------------------------------------
    

    def _handle_packet(self, packet: ParsedPacket) -> None:
        self._packet_count += 1
        self._console.appendPlainText(self._format_console_row(packet))
        if self._raw_logger:
            self._raw_logger.log("RX", packet.raw, delta_t_ms=self._delta_t_ms)
        if not packet.ok:
            print(f"[DEBUG] Packet NOT ok: {packet.error}")
            self._error_count += 1
            self._update_counts()
            return

        print(f"[DEBUG] Packet OK: {packet.frame_id} payload: {packet.payload.hex()}")
        assert self._config is not None
        decoded = decode_frame(self._config, packet.frame_id, packet.payload)
        print(f"[DEBUG] Decoded frame signals count: {len(decoded.signals)}")
        self._apply_decoded(decoded)
        if self._decoded_logger:
            self._decoded_logger.log_frame(self._packet_count, decoded)
        self._update_counts()

    # ------------------------------------------------------------------
    # Table, tabs, and plot maintenance
    # ------------------------------------------------------------------
    
    def _populate_polling_list(self) -> None:
        self._polling_list.clear()
        if not self._config: return
        for sched in self._config.polling_schedules:
            item = QListWidgetItem(f"Target 0x{sched.target_id:04X} ({sched.interval_ms}ms)")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if sched.enabled else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, sched.target_id)
            self._polling_list.addItem(item)

    def _on_polling_item_changed(self, item: QListWidgetItem) -> None:
        target_id = item.data(Qt.ItemDataRole.UserRole)
        enabled = item.checkState() == Qt.CheckState.Checked
        if self._serial:
            self._serial.toggle_schedule(target_id, enabled)

    def _on_toggle_polling(self) -> None:
        enabled = self._polling_action.isChecked()
        self._polling_action.setText("Stop Polling" if enabled else "Start Polling")
        if self._serial:
            self._serial.set_polling_global(enabled)

    def _populate_editor_table(self) -> None:
        self._editor_table.setRowCount(0)
        if not self._config: return
        rw_signals = [s for s in self._config.all_signals if s.read_write in ("W", "RW")]
        for s in rw_signals:
            row = self._editor_table.rowCount()
            self._editor_table.insertRow(row)
            self._editor_table.setItem(row, 0, QTableWidgetItem(f"0x{s.frame_id:04X}"))
            self._editor_table.setItem(row, 1, QTableWidgetItem(s.signal_name))
            
            curr_val = QTableWidgetItem("-")
            self._editor_table.setItem(row, 2, curr_val)
            
            # Action layout: LineEdit + Write Button
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            inp = QLineEdit()
            btn = QPushButton("Write")
            btn.clicked.connect(lambda _, inp=inp, s=s: self._on_editor_write(s, inp.text()))
            layout.addWidget(inp)
            layout.addWidget(btn)
            self._editor_table.setCellWidget(row, 3, widget)

    def _on_editor_write(self, signal, text: str) -> None:
        if not self._serial or not self._serial.is_open:
            QMessageBox.warning(self, "Write", "Not connected")
            return
        try:
            val = float(text)
            if signal.min_value is not None and val < signal.min_value:
                raise ValueError(f"Min value is {signal.min_value}")
            if signal.max_value is not None and val > signal.max_value:
                raise ValueError(f"Max value is {signal.max_value}")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Input", str(e))
            return
            
        # Build write packet
        from ..protocol.packet_builder import build_packet, build_modbus_packet
        if self._config.protocol.parser_type == "modbus_rtu":
            # For FC06 write single register (simplified: convert val to 2 bytes)
            payload = int(val).to_bytes(2, "big", signed=True)
            pkt = build_modbus_packet(self._config.protocol, signal.frame_id, payload)
        else:
            QMessageBox.warning(self, "Write", "Parameter editing for framed protocol not yet fully implemented")
            return
            
        self._serial.enqueue_priority_tx(pkt)
        self._log_activity(f"Priority Write: {signal.signal_name} = {val}")

    
    def _populate_polling_list(self) -> None:
        self._polling_list.clear()
        if not self._config: return
        for sched in self._config.polling_schedules:
            item = QListWidgetItem(f"Target 0x{sched.target_id:04X} ({sched.interval_ms}ms)")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if sched.enabled else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, sched.target_id)
            self._polling_list.addItem(item)

    def _on_polling_item_changed(self, item: QListWidgetItem) -> None:
        target_id = item.data(Qt.ItemDataRole.UserRole)
        enabled = item.checkState() == Qt.CheckState.Checked
        if self._serial:
            self._serial.toggle_schedule(target_id, enabled)

    def _on_toggle_polling(self) -> None:
        enabled = self._polling_action.isChecked()
        self._polling_action.setText("Stop Polling" if enabled else "Start Polling")
        if self._serial:
            self._serial.set_polling_global(enabled)

    def _populate_editor_table(self) -> None:
        self._editor_table.setRowCount(0)
        if not self._config: return
        rw_signals = [s for s in self._config.all_signals if s.read_write in ("W", "RW")]
        for s in rw_signals:
            row = self._editor_table.rowCount()
            self._editor_table.insertRow(row)
            self._editor_table.setItem(row, 0, QTableWidgetItem(f"0x{s.frame_id:04X}"))
            self._editor_table.setItem(row, 1, QTableWidgetItem(s.signal_name))
            
            curr_val = QTableWidgetItem("-")
            self._editor_table.setItem(row, 2, curr_val)
            
            # Action layout: LineEdit + Write Button
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            inp = QLineEdit()
            btn = QPushButton("Write")
            btn.clicked.connect(lambda _, inp=inp, s=s: self._on_editor_write(s, inp.text()))
            layout.addWidget(inp)
            layout.addWidget(btn)
            self._editor_table.setCellWidget(row, 3, widget)

    def _on_editor_write(self, signal, text: str) -> None:
        if not self._serial or not self._serial.is_open:
            QMessageBox.warning(self, "Write", "Not connected")
            return
        try:
            val = float(text)
            if signal.min_value is not None and val < signal.min_value:
                raise ValueError(f"Min value is {signal.min_value}")
            if signal.max_value is not None and val > signal.max_value:
                raise ValueError(f"Max value is {signal.max_value}")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Input", str(e))
            return
            
        # Build write packet
        from ..protocol.packet_builder import build_packet, build_modbus_packet
        if self._config.protocol.parser_type == "modbus_rtu":
            # For FC06 write single register (simplified: convert val to 2 bytes)
            payload = int(val).to_bytes(2, "big", signed=True)
            pkt = build_modbus_packet(self._config.protocol, signal.frame_id, payload)
        else:
            QMessageBox.warning(self, "Write", "Parameter editing for framed protocol not yet fully implemented")
            return
            
        self._serial.enqueue_priority_tx(pkt)
        self._log_activity(f"Priority Write: {signal.signal_name} = {val}")

    def _populate_table_from_config(self) -> None:
        assert self._config is not None
        self._table.setRowCount(0)
        self._row_index.clear()
        row_no = 0
        for frame_id, signals in self._config.signals_by_frame.items():
            for signal in signals:
                self._add_signal_row(row_no, frame_id, signal.frame_name, signal.signal_name, signal.group, signal.index, signal.unit)
                row_no += 1

    def _add_signal_row(
        self,
        row: int,
        frame_id: int,
        frame_name: str,
        signal_name: str,
        group: str,
        index: Optional[int],
        unit: str,
        is_calculated: bool = False,
    ) -> None:
        self._table.insertRow(row)
        self._set_cell(row, 0, f"0x{frame_id:04X}  {frame_name}")
        self._set_cell(row, 1, group or "-")
        self._set_cell(row, 2, signal_name)
        self._set_cell(row, 3, "" if index is None else str(index))
        self._set_cell(row, 4, "-")
        self._set_cell(row, 5, "-")
        self._set_cell(row, 6, unit)
        self._set_cell(row, 7, "-")
        self._set_cell(row, 8, "-")
        group_item = self._table.item(row, 1)
        if group_item is not None:
            group_item.setData(Qt.ItemDataRole.UserRole, is_calculated)
        self._row_index[(frame_id, signal_name)] = row

    def _apply_decoded(self, decoded: DecodedFrame) -> None:
        if decoded.error is not None:
            self._console.appendPlainText(f"[decode] {decoded.error}")
            self._error_count += 1
            return
        for warning in decoded.warnings:
            self._console.appendPlainText(f"[decode warning] {warning}")

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        elapsed = (datetime.now() - self._session_started).total_seconds()
        for signal in [*decoded.signals, *decoded.calculations]:
            row = self._row_index.get((signal.frame_id, signal.signal_name))
            print(f"[DEBUG] applying signal {signal.signal_name}: row={row}, raw={signal.raw_value}, scaled={signal.scaled_value}")
            if row is None:
                row = self._table.rowCount()
                self._add_signal_row(
                    row,
                    signal.frame_id,
                    signal.frame_name,
                    signal.signal_name,
                    signal.group,
                    signal.index,
                    signal.unit,
                    signal.is_calculated,
                )
            raw_text = "-" if signal.raw_value is None else _format_number(signal.raw_value)
            value_text = "-" if signal.scaled_value is None else _format_number(signal.scaled_value)
            print(f"[DEBUG] updating row {row}: raw_text={raw_text}, value_text={value_text}")
            self._set_cell(row, 4, raw_text)
            self._set_cell(row, 5, signal.display_value or value_text)
            self._set_cell(row, 7, self._status_text(signal))
            self._set_cell(row, 8, timestamp)
            self._apply_group_filter(self._group_combo.currentText())
            
            self._update_detail_tabs(signal)
            # Update editor table
            for row in range(self._editor_table.rowCount()):
                if self._editor_table.item(row, 1).text() == signal.signal_name:
                    self._editor_table.item(row, 2).setText(signal.display_value or value_text)
            
            if signal.scaled_value is not None and signal.status == "ok":

                key = (signal.frame_id, signal.signal_name)
                self._plot_history[key].append((elapsed, signal.scaled_value))
                self._prune_plot_history(key, elapsed)
            if signal.status != "ok":
                self._error_count += 1
        self._redraw_plot()

    def _status_text(self, signal: DecodedSignal) -> str:
        if signal.enum_label:
            return f"{signal.status}: {signal.enum_label}"
        if signal.bit_values:
            active = [name for name, active_state in signal.bit_values.items() if active_state]
            return f"{signal.status}: {', '.join(active) if active else 'None'}"
        return signal.status

    def _update_detail_tabs(self, signal: DecodedSignal) -> None:
        if signal.bit_values:
            for bit_name, active in signal.bit_values.items():
                self._upsert_detail_row(
                    self._bitfield_table,
                    (f"0x{signal.frame_id:04X}", signal.signal_name, bit_name),
                    [f"0x{signal.frame_id:04X}", signal.signal_name, bit_name, "ON" if active else "OFF"],
                )
        if signal.enum_label:
            self._upsert_detail_row(
                self._enum_table,
                (f"0x{signal.frame_id:04X}", signal.signal_name),
                [
                    f"0x{signal.frame_id:04X}",
                    signal.signal_name,
                    "" if signal.raw_value is None else str(signal.raw_value),
                    signal.enum_label,
                ],
            )

    def _upsert_detail_row(self, table: QTableWidget, key: tuple[str, ...], values: list[str]) -> None:
        key_text = "\x1f".join(key)
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == key_text:
                for col, value in enumerate(values):
                    table.setItem(row, col, QTableWidgetItem(value))
                table.item(row, 0).setData(Qt.ItemDataRole.UserRole, key_text)
                return
        row = table.rowCount()
        table.insertRow(row)
        for col, value in enumerate(values):
            table.setItem(row, col, QTableWidgetItem(value))
        table.item(row, 0).setData(Qt.ItemDataRole.UserRole, key_text)

    def _populate_group_selector(self) -> None:
        assert self._config is not None
        current = self._group_combo.currentText()
        groups = sorted({signal.group for signal in self._config.all_signals if signal.group})
        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem("All")
        self._group_combo.addItems(groups)
        index = self._group_combo.findText(current)
        self._group_combo.setCurrentIndex(max(0, index))
        self._group_combo.blockSignals(False)

    def _populate_plot_selector(self) -> None:
        assert self._config is not None
        self._plot_variable_list.clear()
        for signal in self._config.all_signals:
            item = QListWidgetItem(f"0x{signal.frame_id:04X} {signal.signal_name}")
            item.setData(Qt.ItemDataRole.UserRole, (signal.frame_id, signal.signal_name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._plot_variable_list.addItem(item)

    def _apply_group_filter(self, group: str) -> None:
        search_text = ""
        if hasattr(self, "_search_input"):
            search_text = self._search_input.text().lower()

        for row in range(self._table.rowCount()):
            item_group = self._table.item(row, 1)
            item_name = self._table.item(row, 2)
            row_group = item_group.text() if item_group else ""
            row_name = item_name.text().lower() if item_name else ""
            
            is_calculated = bool(item_group.data(Qt.ItemDataRole.UserRole)) if item_group else False
            
            visible = group in ("", "All") or row_group == group
            if is_calculated and not self._show_calcs_check.isChecked():
                visible = False
            if search_text and search_text not in row_name:
                visible = False
                
            self._table.setRowHidden(row, not visible)

    def _clear_plot(self) -> None:
        self._plot_history.clear()
        self._redraw_plot()

    def _prune_plot_history(self, key: Tuple[int, str], now_seconds: float) -> None:
        try:
            window = float(self._plot_window_combo.currentText())
        except ValueError:
            window = 300.0
        history = self._plot_history[key]
        while history and now_seconds - history[0][0] > window:
            history.popleft()

    def _export_plot_data(self) -> None:
        selected_keys = []
        for i in range(self._plot_variable_list.count()):
            item = self._plot_variable_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_keys.append(item.data(Qt.ItemDataRole.UserRole))
                
        if not selected_keys:
            QMessageBox.information(self, "Export plot", "No variables selected for plotting.")
            return

        target, _ = QFileDialog.getSaveFileName(
            self, "Export plot data", "plot_data.csv", "CSV files (*.csv)"
        )
        if not target:
            return
            
        with Path(target).open("w", encoding="utf-8", newline="") as fp:
            for key in selected_keys:
                values = list(self._plot_history.get(key, []))
                if not values:
                    continue
                fp.write(f"--- {key[1]} (0x{key[0]:04X}) ---\n")
                fp.write("seconds,value\n")
                for seconds, value in values:
                    fp.write(f"{seconds:.3f},{value:.12g}\n")
                fp.write("\n")
                
        self._set_status(f"Exported plot data to {target}")

    def _redraw_plot(self) -> None:
        if pg is None or self._plot_widget is None:
            return
            
        selected_items = []
        for i in range(self._plot_variable_list.count()):
            item = self._plot_variable_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_items.append(item)

        # Clear curves that are no longer selected
        active_keys = {item.data(Qt.ItemDataRole.UserRole) for item in selected_items}
        for key in list(self._plot_curves.keys()):
            if key not in active_keys:
                self._plot_widget.removeItem(self._plot_curves[key])
                del self._plot_curves[key]
                
        # Add and update selected curves
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2"]
        for idx, item in enumerate(selected_items):
            key = item.data(Qt.ItemDataRole.UserRole)
            values = list(self._plot_history.get(key, []))
            if not values:
                x_values, y_values = [], []
            else:
                x_values, y_values = zip(*values)
                
            if key not in self._plot_curves:
                color = colors[idx % len(colors)]
                self._plot_curves[key] = self._plot_widget.plot(name=item.text(), pen=pg.mkPen(color, width=2))
                
            self._plot_curves[key].setData(list(x_values), list(y_values))

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        if col in (3, 4, 5):
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
        if col == 7:
            lower_text = text.lower()
            if "ok" in lower_text and not "error" in lower_text:
                item.setForeground(QColor("#10b981")) # Green
            elif "error" in lower_text or "fail" in lower_text:
                item.setForeground(QColor("#ef4444")) # Red
            elif text != "-":
                item.setForeground(QColor("#eab308")) # Yellow
                
        self._table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _refresh_ports(self) -> None:
        current = self._port_combo.currentText()
        ports = list(available_ports())
        self._port_combo.clear()
        self._port_combo.addItems(ports or ["No ports"])
        index = self._port_combo.findText(current)
        if index >= 0:
            self._port_combo.setCurrentIndex(index)

    def _apply_serial_defaults(self) -> None:
        if self._config is None:
            return
        defaults = self._config.serial_defaults
        self._baud_combo.setCurrentText(str(defaults.baud_rate))
        self._data_bits_combo.setCurrentText(str(defaults.data_bits))
        self._stop_bits_combo.setCurrentText(f"{defaults.stop_bits:g}")
        self._parity_combo.setCurrentText(defaults.parity)
        self._timeout_combo.setCurrentText(str(defaults.timeout_ms))

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
        self._logging_action.setEnabled(ready)

    def _set_connection_ui(self, connected: bool) -> None:
        text = "Disconnect" if connected else "Connect"
        self._connect_action.setText(text)
        if hasattr(self, "_connect_button"):
            self._connect_button.setText(text)
        self._port_combo.setEnabled(not connected)
        self._baud_combo.setEnabled(not connected)
        self._data_bits_combo.setEnabled(not connected)
        self._stop_bits_combo.setEnabled(not connected)
        self._parity_combo.setEnabled(not connected)
        self._timeout_combo.setEnabled(not connected)
        if hasattr(self, "_connection_label"):
            self._connection_label.setText(f"Serial: {'connected' if connected else 'disconnected'}")

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _log_activity(self, text: str) -> None:
        if not hasattr(self, "_activity_log") or self._activity_log is None:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self._activity_log.appendPlainText(f"{timestamp}  {text}")



    def _append_to_console(self, text: str) -> None:
        if hasattr(self, "_console"):
            self._console.appendPlainText(text)

    def _format_console_row(self, packet: ParsedPacket) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        hex_text = packet.raw.hex(" ").upper()
        if packet.ok:
            return f"{timestamp}, RX, {hex_text}"
        return f"{timestamp}, ERR, {packet.error or 'unknown'}, {hex_text}"

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._serial:
            self._serial.close()
        if self._logging:
            self._stop_logging()
        self._save_window_state()
        super().closeEvent(event)


def _format_number(value) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
