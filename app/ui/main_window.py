"""PySide6 main window for the Serial monitor."""

from __future__ import annotations

import os
import sys
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover - exercised only when optional dep missing
    pg = None


if pg is not None:
    # Global, intentional: keeps rendering consistent across Live Plot and Analysis Suite.
    # useOpenGL offloads QPainter primitives to the GPU — meaningful CPU reduction
    # at high refresh rates with multiple panels.
    pg.setConfigOptions(antialias=True, useOpenGL=True)


try:
    import qdarktheme
except ImportError:  # pragma: no cover
    qdarktheme = None

APP_ORG  = "Bytehound"
APP_NAME = "Bytehound"
APP_DISPLAY_NAME = "Bytehound"

# Bump whenever a dock objectName, toolbar objectName, or addDockWidget
# topology changes. saveState() encodes widgets by objectName; restoring
# state from a different schema produces stranded docks at the edges of
# the window. On mismatch we drop the stored state and fall back to the
# default layout — users see one layout reset, not a broken window.
_WINDOW_STATE_VERSION = 1

# Bumped when default QSettings values change so users get migrated to
# the new defaults without losing values they explicitly customised. The
# migration runs once on launch; see _migrate_settings.
_SETTINGS_MIGRATION_VERSION = 2


def _migrate_settings(settings) -> None:
    """One-time per-version migrations of stored user settings.

    Idempotent. Skips entirely if the stored migration version is already
    >= the current target.
    """
    try:
        stored_version = int(settings.value("settings/migration_version", 0))
    except (TypeError, ValueError):
        stored_version = 0
    if stored_version >= _SETTINGS_MIGRATION_VERSION:
        return

    # v0/v1 -> v2: reset polling to hardware-safe sequential defaults.
    # An earlier release shipped with auto-bumped pipelining=on/depth=8,
    # which broke devices that process one command at a time. Bump the
    # tx_gap from the original 30 ms default to 100 ms — real-hardware
    # testing on a multi-target BMS showed 30 ms drops every other poll
    # and 100 ms is the smallest gap that holds. Users who set a specific
    # gap other than 30 keep their choice.
    if stored_version < 2:
        settings.setValue("poll/pipelining", False)
        settings.setValue("poll/pipeline_depth", 1)
        if settings.contains("poll/pipeline_tx_gap_ms"):
            try:
                old_gap = int(settings.value("poll/pipeline_tx_gap_ms", 30))
            except (TypeError, ValueError):
                old_gap = 30
            if old_gap == 30:
                settings.setValue("poll/pipeline_tx_gap_ms", 100)

    settings.setValue("settings/migration_version", _SETTINGS_MIGRATION_VERSION)


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


from .parameter_editor import ParameterEditorMixin
from .telemetry_pipeline import TelemetryPipelineMixin
from app.ui.widgets import (
    _BTN_GREEN,
    _BTN_PINK,
    _BTN_YELLOW,
    _apply_windows_dark_titlebar,
    _icon,
)



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
            "  • Another application is using the port (Serial Monitor, PuTTY, another terminal, or a previous instance of this app).\n"
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

from .dialogs import ConnectionDialog, AboutDialog
from ..decoder.template_io import export_excel_template
from ..decoder.types import FrameConfig
from ..serial_logging.decoded_logger import DecodedLogger
from ..serial_logging.raw_logger import RawLogger
from ..protocol.packet_parser import ParserProtocol
from ..serial_io.serial_worker import PollingWorker, SerialSettings



# ---------------------------------------------------------------------------
# QSS stylesheets
# ---------------------------------------------------------------------------







# ---------------------------------------------------------------------------


from app.ui.plot_panel import (
    GRID_LAYOUTS,
    PlotPanel,
    TimeSeriesBuffer,
)


# ---------------------------------------------------------------------------
# Configuration dialogs
# ---------------------------------------------------------------------------

from app.ui.config_loader import ConfigLoaderMixin
from app.ui.detail_tabs import DetailTabsMixin
from app.ui.logging_session import LoggingSessionMixin
from app.ui.plot_orchestration import PlotOrchestrationMixin
from app.ui.polling_session import PollingSessionMixin
from app.ui.popups import PopupsMixin
from app.ui.theming import ThemingMixin, _PLOT_PALETTE_DARK
from app.ui.tx_panel import TxPanelMixin
from app.ui.ui_builders import UIBuildersMixin
from app.ui.updater_wiring import UpdaterWiringMixin
from app.ui.report_issue import ReportIssueMixin


class MainWindow(
    UIBuildersMixin,
    ThemingMixin,
    PlotOrchestrationMixin,
    ConfigLoaderMixin,
    LoggingSessionMixin,
    PollingSessionMixin,
    DetailTabsMixin,
    TxPanelMixin,
    UpdaterWiringMixin,
    ReportIssueMixin,
    PopupsMixin,
    TelemetryPipelineMixin,
    ParameterEditorMixin,
    QMainWindow,
):
    def _make_history_buffer(self) -> "TimeSeriesBuffer":
        """Factory for per-signal entries in ``self._plot_history``.

        Append-only chunked store. ``_plot_history_max_samples`` acts as a
        soft cap (``None`` = unbounded — keep every sample for the whole
        session). Existing buffers keep their cap until cleared; the cap
        is reapplied when the user changes the display window.
        """
        cap = getattr(self, "_plot_history_max_samples", None)
        return TimeSeriesBuffer(cap)


    def __init__(self) -> None:
        super().__init__()
        try:
            import json as _json
            with (_project_root() / "version.json").open("r", encoding="utf-8") as fp:
                self._version_info = _json.load(fp)
        except Exception:
            self._version_info = {}
        self._version = self._version_info.get("version", "0.0.0")
        self.setWindowTitle(f"{APP_DISPLAY_NAME} v{self._version}")
        self.resize(1280, 780)
        # Explicit minimum so the user can snap the window to half-screen on
        # a 1080p display without Qt blocking the resize. The actual floor
        # is still set by child widgets' implicit minimums; this just
        # documents the supported lower bound and matches the targets we
        # tuned in _build_plot_tab (hover/hint width relaxation).
        self.setMinimumSize(640, 480)

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
        _migrate_settings(self._settings)
        self._apply_logging_level(str(self._settings.value("logging/level", "INFO")))
        self._tx_field_inputs: Dict[str, QLineEdit] = {}
        self._seen_decode_warnings: set[tuple[int, str, int]] = set()
        self._unsolicited_detected = False

        # Timer removed; using PollingWorker QThread

        # Live-plot history. One TimeSeriesBuffer per signal.
        # Default soft cap of 100,000 samples per signal acts as a marathon-run
        # safety valve to prevent RAM exhaustion (OOM crashes) during 2-3 day runs.
        raw_cap = self._settings.value("plot/history_max_samples", 100_000)
        try:
            cap_int = int(raw_cap)
        except (TypeError, ValueError):
            cap_int = 100_000
        if cap_int <= 0:
            cap_int = 100_000  # Enforce marathon-run safety cap
        self._plot_history_max_samples: Optional[int] = cap_int
        # Display window in seconds. 0 / None means "All session".
        raw_window = self._settings.value("plot/window_seconds", 300)  # default 5 min
        try:
            window_int = int(raw_window)
        except (TypeError, ValueError):
            window_int = 300
        self._plot_window_seconds: Optional[int] = window_int if window_int > 0 else None
        self._plot_history: Dict[Tuple[int, str], TimeSeriesBuffer] = (
            defaultdict(self._make_history_buffer))
        # Multi-grid plot state
        self._plot_panels: List[PlotPanel] = []   # one entry per subplot cell
        self._gl_widget = None                     # pg.GraphicsLayoutWidget
        self._plot_widget = None                   # alias → panels[0].plot_item (compat)
        self._tx_logger_parser = None
        self._wire_recorded_connected = False
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
        self._plot_trigger: Optional[dict] = None
        self._plot_range_changing: bool = False   # re-entrancy guard for setXRange calls
        self._initial_show_done: bool = False     # startup guard to ignore initial resize event range changes
        self._seen_faults: set[Tuple[int, str]] = set()

        # Packet queue + 60 Hz throttle timer
        # Bounded deque prevents OOM if the Qt event loop stalls (e.g. user
        # drags the window title bar for several seconds): oldest packets are
        # silently dropped rather than growing the list without bound.
        self._pending_packets: deque = deque(maxlen=10_000)
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(16)  # ~60 Hz
        self._ui_timer.timeout.connect(self._flush_ui)

        # Reconnect timer for exponential backoff on USB disconnect
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._on_reconnect_timeout)
        self._reconnect_attempts = 0
        self._saved_settings: Optional[SerialSettings] = None

        # 2 Hz Y-axis autofit. Y-autorange on every packet costs ~10s of profile
        # time at 100 Hz; throttling to 500 ms is visually indistinguishable for
        # telemetry and cuts the axis-paint cost roughly proportionally.
        self._y_autofit_timer = QTimer(self)
        self._y_autofit_timer.setInterval(500)
        self._y_autofit_timer.timeout.connect(self._throttled_y_autofit)
        self._y_autofit_timer.start()

        self._pending_console_lines: List[str] = []
        self._build_ui()
        if hasattr(self, "_console_dock") and self._console_dock is not None:
            self._console_dock.visibilityChanged.connect(self._on_console_dock_visibility_changed)
        self._load_default_config()
        self._refresh_action_state()
        # Rebuild icon tints after all widgets exist so secondary menu/toolbar
        # icons get the correct colour even without a manual theme switch.
        _saved_theme = str(self._settings.value("ui/theme", "dark"))
        self._apply_theme(_saved_theme)

        self._default_state = self.saveState()
        self._default_geometry = self.saveGeometry()
        self._restore_window_state()
        QTimer.singleShot(100, self._check_and_recover_temp_logs)

        if hasattr(self, "_welcome_dashboard") and self._welcome_dashboard is not None:
            from app.serial_io.serial_worker import list_available_ports
            self._welcome_dashboard.connect_requested.connect(self._on_dashboard_connect)
            self._welcome_dashboard.load_config_requested.connect(self._on_load_config)
            self._welcome_dashboard.preset_selected.connect(self._on_load_preset)
            self._welcome_dashboard.open_wizard_requested.connect(self._on_open_protocol_wizard)
            self._welcome_dashboard.open_manual_requested.connect(self._on_view_docs)
            self._welcome_dashboard.recent_config_selected.connect(lambda p: self._load_config_from_path(Path(p)))
            ports = list_available_ports()
            self._welcome_dashboard.update_ports(ports)
            self._welcome_dashboard.set_recent_configs(self._recent_paths())
            self._welcome_dashboard.refresh_ports_btn.clicked.connect(
                lambda: self._welcome_dashboard.update_ports(list_available_ports())
            )

        if hasattr(self, "_cards_view") and self._cards_view is not None:
            self._cards_view.quick_plot_requested.connect(self._on_quick_plot_signal)

        self._log_activity(f"[SESSION] Started {APP_DISPLAY_NAME} v{self._version}")

    # ------------------------------------------------------------------
    # UI construction & Handlers
    # ------------------------------------------------------------------

    def _on_dashboard_connect(self, port: str, baud: int) -> None:
        if self._config is None:
            from ..decoder.protocol_presets import PRESET_SINGLE_CELL_BMS
            self._load_config_from_path(PRESET_SINGLE_CELL_BMS)
        from ..serial_io.serial_worker import SerialSettings
        settings = SerialSettings(port=port, baud_rate=baud)
        self._attempt_connect(settings)

    def _on_open_protocol_wizard(self) -> None:
        self._log_activity("[ACTION] Open Protocol Wizard")
        from .config_wizard import ProtocolWizardDialog
        dlg = ProtocolWizardDialog(parent=self)
        dlg.protocol_created.connect(lambda path: self._load_config_from_path(Path(path)))
        dlg.exec()

    def _on_system_diagnostic(self) -> None:
        self._log_activity("[ACTION] Open System Diagnostic Checkup")
        from .diagnostics_assistant import SystemDiagnosticDialog
        port = self._saved_settings.port if self._saved_settings else ""
        baud = self._saved_settings.baud_rate if self._saved_settings else 115200
        dlg = SystemDiagnosticDialog(config=self._config, active_port=port, active_baud=baud, parent=self)
        dlg.exec()

    def _on_load_preset(self, preset_name: str) -> None:
        from app.decoder.protocol_presets import BUILTIN_PRESETS
        if preset_name in BUILTIN_PRESETS:
            self._log_activity(f"[ACTION] Load Preset: {preset_name}")
            try:
                self._load_config_from_path(BUILTIN_PRESETS[preset_name])
                self._toast(f"Loaded preset '{preset_name}'")
            except Exception as exc:
                self._popup_critical("Preset Error", str(exc))

    def _on_quick_plot_signal(self, signal_name: str, target_widget: Optional[QWidget] = None) -> None:
        if self._config is None:
            return
        for frame_id, sigs in self._config.signals_by_frame.items():
            for sig in sigs:
                if sig.signal_name == signal_name:
                    key = (frame_id, signal_name)
                    if len(self._plot_panels) > 1:
                        self._show_panel_selection_menu(key, target_widget)
                    else:
                        if key not in self._plot_keys:
                            self._add_signal_to_panel(0, key)
                        else:
                            self._remove_signal_from_panel(0, key)
                    if hasattr(self, "_cards_view") and self._cards_view is not None:
                        self._cards_view.sync_plot_active_states(self._plot_panels)
                    return

    def _show_panel_selection_menu(self, key: Tuple[int, str], target_widget: Optional[QWidget] = None) -> None:
        from PySide6.QtGui import QCursor
        menu = QMenu(self)
        title_act = menu.addAction(f"📊 Live Plot Panels for '{key[1]}':")
        title_act.setEnabled(False)
        menu.addSeparator()

        for idx, panel in enumerate(self._plot_panels):
            is_on_panel = key in panel.assigned_keys
            act = menu.addAction(f"Graph Panel {idx + 1}")
            act.setCheckable(True)
            act.setChecked(is_on_panel)
            act.setData((idx, is_on_panel))

        menu.addSeparator()
        add_new_act = menu.addAction("➕ Add to New Graph Panel")
        add_new_act.setData(("new", False))

        pos = target_widget.mapToGlobal(target_widget.rect().bottomLeft()) if target_widget and hasattr(target_widget, "mapToGlobal") else QCursor.pos()
        selected = menu.exec(pos)
        if selected is None or selected == title_act:
            return

        data = selected.data()
        if not data:
            return
        panel_idx, is_on_panel = data
        if panel_idx == "new":
            if hasattr(self, "_layout_combo") and self._layout_combo is not None:
                curr_idx = self._layout_combo.currentIndex()
                if curr_idx + 1 < self._layout_combo.count():
                    self._layout_combo.setCurrentIndex(curr_idx + 1)
            new_idx = len(self._plot_panels) - 1
            self._add_signal_to_panel(new_idx, key)
        else:
            if is_on_panel:
                self._remove_signal_from_panel(panel_idx, key)
            else:
                self._add_signal_to_panel(panel_idx, key)

        if hasattr(self, "_cards_view") and self._cards_view is not None:
            self._cards_view.sync_plot_active_states(self._plot_panels)






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

    def _on_copy_table(self) -> None:
        """Copy the entire telemetry table as tab-separated text."""
        from .telemetry_model import COLUMN_HEADERS, NUM_COLS
        lines = ["\t".join(COLUMN_HEADERS)]
        for row in range(self._table_model.row_count()):
            cells = [self._table_model.cell_text(row, col) for col in range(NUM_COLS)]
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
        self._toast(f"Copied {self._table_model.row_count()} rows")
        self._log_activity("[ACTION] Copy table snapshot")

    def _on_info(self) -> None:
        logo_path = _find_logo("logo_sq.png") or _find_logo("logo.png")

        self._log_activity("[ACTION] Open About Dialog")
        dlg = AboutDialog(self._version_info, logo_path, self)
        dlg.exec()

    def _on_view_docs(self) -> None:
        self._log_activity("[ACTION] View documentation")
        docs_path = Path(__file__).resolve().parents[1] / "resources" / "index.html"
        try:
            version = _read_version()
            if version != "0.0.0" and docs_path.exists():
                content = docs_path.read_text(encoding="utf-8")
                import re
                new_content, count = re.subn(
                    r"Manual — Version \d+\.\d+\.\d+",
                    f"Manual — Version {version}",
                    content
                )
                if count > 0 and new_content != content:
                    docs_path.write_text(new_content, encoding="utf-8")
                    self._log_activity(f"[INFO] Dynamically updated index.html version to {version}")
        except Exception as e:
            self._log_activity(f"[WARN] Failed to dynamically update index.html version: {e}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(docs_path)))

    def _on_copy_diagnostics(self) -> None:
        """Copy a bug-report-ready snapshot to the clipboard.

        Includes app/runtime versions, OS, current config, connection +
        logging state, session counters, and the tail of bytehound.log.
        Goal: a user can paste this directly into an issue without us
        asking three follow-up questions.
        """
        import platform
        try:
            from PySide6 import __version__ as _pyside_version
        except Exception:
            _pyside_version = "unknown"
        try:
            from PySide6.QtCore import qVersion
            _qt_version = qVersion()
        except Exception:
            _qt_version = "unknown"

        conn = "disconnected"
        port_info = ""
        if self._serial is not None and self._serial.is_open:
            conn = "connected"
            if self._serial.settings.connection_type in ("tcp", "udp"):
                port_info = (
                    f"  Connection Type: {self._serial.settings.connection_type.upper()}\n"
                    f"  Host: {self._serial.settings.host}\n"
                    f"  Port: {self._serial.settings.port_num}"
                )
                if self._serial.settings.connection_type == "udp":
                    port_info += f"\n  Local Port: {self._serial.settings.local_port}"
            else:
                port_info = (
                    f"  Port: {self._serial.settings.port} @ "
                    f"{self._serial.settings.baud_rate} "
                    f"{self._serial.settings.data_bits}{self._serial.settings.parity}"
                    f"{self._serial.settings.stop_bits:g}"
                )

        log_path = self._find_log_file_path()
        log_tail = self._read_log_tail(log_path, lines=200) if log_path else "(log file not found)"

        diag = [
            f"=== {APP_DISPLAY_NAME} v{self._version} diagnostics ===",
            f"Captured: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "--- Runtime ---",
            f"OS:      {platform.system()} {platform.release()} ({platform.version()})",
            f"Python:  {sys.version.split()[0]}",
            f"PySide6: {_pyside_version}",
            f"Qt:      {_qt_version}",
            f"Frozen:  {getattr(sys, 'frozen', False)}",
            "",
            "--- Session ---",
            f"Config:      {self._config_path or '(none loaded)'}",
            f"Connection:  {conn}",
        ]
        if port_info:
            diag.append(port_info)
        diag += [
            f"Logging:     {'active' if self._logging else 'stopped'}",
            f"Started:     {self._session_started.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Frames RX:   {self._packet_count}",
            f"CRC errors:  {self._error_count}",
            f"Timeouts:    {self._timeouts}",
            f"RX bytes:    {self._rx_bytes}",
            f"TX bytes:    {self._tx_bytes}",
            "",
            f"--- Log file: {log_path or '(not configured)'} ---",
            log_tail,
        ]
        QApplication.clipboard().setText("\n".join(diag))
        self._toast("Diagnostics copied to clipboard")
        self._log_activity("[ACTION] Copied diagnostics to clipboard")

    @staticmethod
    def _find_log_file_path() -> Optional[Path]:
        """Locate the RotatingFileHandler's file from the root logger."""
        import logging as _logging
        for handler in _logging.getLogger().handlers:
            base = getattr(handler, "baseFilename", None)
            if base:
                return Path(base)
        return None

    @staticmethod
    def _read_log_tail(path: Path, *, lines: int) -> str:
        """Return the last ``lines`` lines of *path*, or an error placeholder."""
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fp:
                # deque(maxlen=...) keeps memory bounded for huge log files.
                tail = deque(fp, maxlen=lines)
            return "".join(tail).rstrip()
        except OSError as exc:
            return f"(could not read log file: {exc})"




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

        from .theming import resolve_theme
        theme = str(self._settings.value("ui/theme", "dark"))
        effective = resolve_theme(theme)
        if effective == "dark":
            disabled_bg = "#1E293B"
            disabled_fg = "#64748B"
            disabled_border = "1px solid #334155"
        else:
            disabled_bg = "#E2E8F0"
            disabled_fg = "#94A3B8"
            disabled_border = "1px solid #CBD5E1"

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
                background-color: {disabled_bg};
                color: {disabled_fg};
                border: {disabled_border};
            }}
            """
        )


    def _populate_view_menu(self) -> None:
        menu = self._view_menu
        menu.clear()
        from .theming import resolve_theme
        theme = str(self._settings.value("ui/theme", "dark"))
        ic = "#F8FAFC" if resolve_theme(theme) == "dark" else "#1F2937"

        # Each toggle gets a distinctive Material Design icon that hints at
        # the panel's content. Without these the Panels submenu was a wall
        # of plain-text toggles indistinguishable at a glance.
        panels_menu = menu.addMenu(_icon("mdi6.view-quilt-outline", ic), "Panels")
        for dock, label, dock_icon in (
            (self._plot_dock,       "Live Plot",        "mdi6.chart-line"),
            (self._bitfields_dock,  "Bitfields",        "mdi6.toggle-switch-outline"),
            (self._enums_dock,      "Enums",            "mdi6.format-list-bulleted-type"),
            (self._tx_dock,         "TX Commands",      "mdi6.send-outline"),
            (self._editor_dock,     "Parameter Editor", "mdi6.playlist-edit"),
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




















    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        from .theming import resolve_theme
        theme = str(self._settings.value("ui/theme", "dark"))
        dark = (resolve_theme(theme) == "dark")
        QTimer.singleShot(0, lambda: _apply_windows_dark_titlebar(self, dark=dark))
        # Split right column after the window is fully shown so Qt honours it.
        if not self._settings.value("window/state"):  # only on first launch
            QTimer.singleShot(50, self._apply_default_dock_split)
        # Clear the startup guard after layouts and resizes have settled
        QTimer.singleShot(50, lambda: setattr(self, "_initial_show_done", True))

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
        # The captured _default_state is whatever Qt happened to lay out at
        # construction time — usually fine but the Live Plot ends up wider
        # than ideal and the right column too narrow. Apply explicit
        # proportions so Reset always produces a tidy, useable layout.
        QTimer.singleShot(0, self._apply_tidy_dock_proportions)
        self._toast("Window layout reset")

    def _apply_tidy_dock_proportions(self) -> None:
        """Tune dock widths/heights to a sensible split.

        Right column ≈ 36% of width, bottom plot ≈ 38% of height. Right
        column's vertical split: panels 65% / logs 35%. Deferred via
        singleShot so the geometry restore has settled before we resize.
        """
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        # Width: pull the right column wider so the bottom plot dock has
        # less width to fill — addresses the "plot stretched on x" feel.
        right_docks = [
            self._bitfields_dock, self._enums_dock, self._tx_dock, self._editor_dock,
            self._console_dock, self._activity_dock,
        ]
        right_w = max(360, int(w * 0.36))
        self.resizeDocks(right_docks, [right_w] * len(right_docks), Qt.Orientation.Horizontal)
        # Height: bottom Live Plot gets ~38% of window height.
        self.resizeDocks([self._plot_dock], [int(h * 0.38)], Qt.Orientation.Vertical)
        # Right column vertical split: panels 65% / logs 35%.
        self.resizeDocks(
            [self._bitfields_dock, self._console_dock],
            [int(h * 0.65), int(h * 0.35)],
            Qt.Orientation.Vertical,
        )
        # Make sure the user's preferred tabs come back to the front.
        self._tx_dock.raise_()
        self._activity_dock.raise_()

    def _save_window_state(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/state", self.saveState())
        self._settings.setValue("window/state_version", _WINDOW_STATE_VERSION)

    def _restore_window_state(self) -> None:
        stored_version = self._settings.value("window/state_version", 0)
        try:
            stored_version = int(stored_version)
        except (TypeError, ValueError):
            stored_version = 0
        if stored_version != _WINDOW_STATE_VERSION:
            # Schema drift (or first launch after an upgrade that bumped
            # the version). Discard the stale blobs and let the default
            # layout from __init__ stand.
            self._settings.remove("window/geometry")
            self._settings.remove("window/state")
            self._settings.sync()
            return
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

    # ------------------------------------------------------------------
    # Grid management
    # ------------------------------------------------------------------






    def _on_layout_changed(self, label: str) -> None:
        rows, cols = GRID_LAYOUTS.get(label, (2, 1))
        self._clear_saved_y_ranges()
        self._rebuild_plot_grid(rows, cols, restore=False)
        self._redraw_plot()
        self._log_activity(f"[ACTION] Plot layout changed to {label} ({rows}x{cols})")


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
        hint.setObjectName("hintLabel")
        hint.setStyleSheet("font-size:9pt;")
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
                fid_label = f"0x{fid:04X}" if isinstance(fid, int) else str(fid)
                label = f"{fid_label}  {nm}"
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













    # ------------------------------------------------------------------
    # Config and toolbar handlers
    # ------------------------------------------------------------------







    def _on_edit_config(self) -> None:
        self._log_activity("[ACTION] Open Configuration Editor")
        from .config_editor import ConfigEditorWindow
        self._config_editor = ConfigEditorWindow(self)
        if hasattr(self, "_config_path") and self._config_path:
            import json
            from pathlib import Path
            from ..decoder.config_loader import _read_excel_tables, _read_csv_tables
            try:
                path_obj = Path(self._config_path)
                self._config_editor.set_active_config_path(path_obj)
                if path_obj.suffix.lower() == ".json":
                    with path_obj.open("r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    self._config_editor.load_data(data)
                elif path_obj.suffix.lower() in {".xlsx", ".xlsm"}:
                    data = _read_excel_tables(path_obj)
                    self._config_editor.load_data(data)
                elif path_obj.is_dir():
                    data = _read_csv_tables(path_obj)
                    self._config_editor.load_data(data)
            except Exception as e:
                self._log_activity(f"[ERROR] Failed to load config into editor: {e}")
        self._config_editor.show()

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

    def _disconnect(self, *, reason: str = "Disconnected") -> None:
        """Single shutdown path for every disconnect scenario.

        Guarantees the safe sequence:
          1. Stop the 60 Hz UI flush timer
          2. Stop the Y-autofit timer
          3. Stop logging (flushes final data while worker may still be alive)
          4. Stop the worker thread and wait for it to exit
          5. Null the reference
          6. Update the UI chrome

        Idempotent — safe to call even when already disconnected.
        """
        self._ui_timer.stop()
        self._wire_recorded_connected = False
        if hasattr(self, "_y_autofit_timer"):
            self._y_autofit_timer.stop()
        if self._logging:
            title = "Closing" if reason == "Application closed" else "Saving Log"
            self._stop_logging(title=title)
            self._log_activity("[INFO] Logging auto-stopped on disconnect")
        if hasattr(self, "_tx_frame_payload_cache"):
            self._tx_frame_payload_cache.clear()
        if hasattr(self, "_latest_payload_by_frame"):
            self._latest_payload_by_frame.clear()
        if self._serial is not None:
            try:
                self._serial.close()   # calls stop() + wait(2000) + port.close()
            except Exception:
                pass
            self._serial = None
        self._set_connection_ui(False)
        self._set_status(reason)
        if hasattr(self, "_warning_badge") and self._warning_badge is not None:
            self._warning_badge.setVisible(False)
        if hasattr(self, "_reconnect_timer") and self._reconnect_timer.isActive():
            self._reconnect_timer.stop()

    def _attempt_connect(self, settings: SerialSettings, is_retry: bool = False) -> bool:
        self._seen_decode_warnings.clear()
        if hasattr(self, "_warning_badge") and self._warning_badge is not None:
            self._warning_badge.setVisible(False)
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
            self._serial.warning_occurred.connect(self._on_serial_warning)
            self._serial.tx_recorded.connect(self._on_tx_recorded)
            if hasattr(self, "_console_dock") and self._console_dock is not None and self._console_dock.isVisible():
                self._serial.wire_recorded.connect(self._on_wire_recorded)
                self._wire_recorded_connected = True
            else:
                self._wire_recorded_connected = False
            self._serial.connection_lost.connect(self._on_connection_lost)
            self._serial.device_timeout.connect(self._on_device_timeout)
            self._serial.open()
            self._serial.set_polling_global(self._polling_action.isChecked())
            self._session_started = datetime.now()
            for buf in self._plot_history.values():
                buf.clear()
            self._ui_timer.start()

            self._set_connection_ui(True)
            if settings.connection_type in ("tcp", "udp"):
                self._set_status(f"Connected via {settings.connection_type.upper()} to {settings.port}")
                self._log_activity(f"Connected via {settings.connection_type.upper()} to {settings.port}")
            else:
                self._set_status(f"Connected to {settings.port}")
                self._log_activity(f"Connected to {settings.port} @ {settings.baud_rate}")
            self._saved_settings = settings
            self._reconnect_attempts = 0
            if hasattr(self, "_reconnect_timer") and self._reconnect_timer.isActive():
                self._reconnect_timer.stop()
            return True
        except Exception as exc:
            self._serial = None
            if is_retry:
                self._log_activity(f"[WARN] Reconnection attempt failed for {settings.port}: {exc}")
            else:
                self._popup_critical(
                    "Connection Error",
                    _format_serial_open_error(getattr(settings, "port", ""), exc),
                )
            return False

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

        dlg = ConnectionDialog(
            self._settings,
            parent=self,
            config_defaults=self._config.serial_defaults,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        settings = dlg.get_settings()
        if not settings.port:
            self._popup_warning("Connect", "No port selected. Please plug in a device and refresh.")
            return

        self._attempt_connect(settings)

    def _on_serial_error(self, err: str) -> None:
        """Handle non-fatal worker errors (per-schedule failures).

        The worker's ``error_occurred`` signal is only emitted for
        per-schedule problems (auto-disable, build failures) — never for
        connection-level errors. Disconnecting the session was wrong: a
        single broken schedule killed the entire live data stream. Fatal
        disconnects are handled by ``connection_lost``.
        """
        self._log_activity(f"[ERROR] {err}")
        if hasattr(self, "_warning_badge") and self._warning_badge is not None:
            self._warning_badge.setVisible(True)
            self._warning_badge.setToolTip(err)

    def _on_serial_warning(self, msg: str) -> None:
        self._log_activity(f"[WARN] {msg}")



    def _on_connection_lost(self) -> None:
        """Called when the worker detects a physical USB unplug."""
        try:
            self._disconnect(reason="USB device disconnected")
        except Exception:
            # _disconnect can fail if the serial port is in a bad state
            import logging
            logging.getLogger("bytehound.ui").exception(
                "_disconnect raised during connection_lost handling"
            )
        self._log_activity("[WARN] Connection lost — USB device was disconnected")

        # Trigger exponential backoff auto-reconnect if enabled
        if self._saved_settings and getattr(self._saved_settings, "auto_reconnect", False):
            self._reconnect_attempts = 0
            self._log_activity("[INFO] Auto-reconnect is enabled. Scheduling reconnection in 1.0s...")
            self._reconnect_timer.start(1000)

    def _on_reconnect_timeout(self) -> None:
        if not self._saved_settings:
            return

        self._reconnect_attempts += 1
        self._log_activity(f"[INFO] Auto-reconnect attempt {self._reconnect_attempts} for {self._saved_settings.port}...")

        if self._serial is not None and self._serial.is_open:
            self._reconnect_attempts = 0
            return

        success = self._attempt_connect(self._saved_settings, is_retry=True)
        if success:
            self._log_activity("[INFO] Auto-reconnect successful!")
        else:
            # Exponential backoff: 1s, 2s, 4s, 8s, up to 16s
            backoff = min(16000, 1000 * (2 ** self._reconnect_attempts))
            self._log_activity(f"[INFO] Scheduling next reconnect attempt in {backoff / 1000:.0f} seconds...")
            self._reconnect_timer.start(backoff)

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

    def _on_tx_recorded(self, packet: bytes) -> None:
        self._tx_bytes += len(packet)
        self._refresh_counts_label()

    def _on_wire_recorded(self, direction: str, packet: bytes, timestamp: datetime) -> None:
        direction = direction.upper()
        if self._raw_logger:
            self._raw_logger.log(direction, packet, timestamp=timestamp)
        if direction == "TX" and self._decoded_logger and self._config:
            import time
            from ..decoder.frame_decoder import decode_frame
            try:
                parser = self._tx_logger_parser
                if parser is None:
                    from ..protocol.packet_parser import create_parser
                    parser = create_parser(self._config.protocol)
                parser.feed(packet)
                parsed = parser.extract_all()
                if not hasattr(self, "_tx_signal_state"):
                    self._tx_signal_state = {}
                for p in parsed:
                    if p.ok and p.frame_id is not None:
                        decoded = decode_frame(self._config, p.frame_id, p.payload, self._tx_signal_state)
                        if self._log_started_perf is not None:
                            elapsed_ms = int((time.perf_counter() - self._log_started_perf) * 1000)
                        else:
                            t0 = self._log_started or self._session_started or datetime.now()
                            elapsed_ms = int((datetime.now() - t0).total_seconds() * 1000)
                        self._decoded_logger.log_frame(decoded, elapsed_ms)
            except Exception as e:
                import logging
                logging.getLogger("bytehound.ui").exception("Failed to parse/decode TX packet: %s", e)
        if hasattr(self, "_console_dock") and self._console_dock is not None and self._console_dock.isVisible():
            formatted_line = (
                f"{timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}, "
                f"{direction}, {packet.hex(' ').upper()}"
            )
            self._pending_console_lines.append(formatted_line)


    def _on_console_dock_visibility_changed(self, visible: bool) -> None:
        if self._serial is not None:
            if self._wire_recorded_connected:
                try:
                    self._serial.wire_recorded.disconnect(self._on_wire_recorded)
                except (RuntimeError, TypeError):
                    pass
                self._wire_recorded_connected = False
            if visible:
                try:
                    self._serial.wire_recorded.connect(self._on_wire_recorded)
                    self._wire_recorded_connected = True
                except (RuntimeError, TypeError):
                    pass


    def _log_flush_interval(self) -> float:
        value = self._settings.value("logging/flush_interval_s", 0.5)
        try:
            interval = float(value)
        except (TypeError, ValueError):
            interval = 0.5
        if interval < 0:
            interval = 0.0
        return interval


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
            metadata["connection_type"] = self._serial.settings.connection_type
            if self._serial.settings.connection_type in ("tcp", "udp"):
                metadata["host"] = self._serial.settings.host
                metadata["port"] = str(self._serial.settings.port_num)
                if self._serial.settings.connection_type == "udp":
                    metadata["local_port"] = str(self._serial.settings.local_port)
            else:
                metadata["serial_port"] = self._serial.settings.port
                metadata["baud_rate"] = str(self._serial.settings.baud_rate)
        return metadata



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
        # Hover-readout cache snapshots history per-key; without this, a
        # cursor read right after Clear would surface values from data
        # that no longer exists in _plot_history.
        if hasattr(self, "_hover_cache"):
            self._hover_cache.clear()
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
        self._refresh_counts_label()
        self._set_status("Cleared decoded values and console")
        self._log_activity("[ACTION] Cleared console and decoded values")

    # ------------------------------------------------------------------
    # Data feed
    # ------------------------------------------------------------------



    # ------------------------------------------------------------------
    # Table, tabs, and plot maintenance
    # ------------------------------------------------------------------










            # Per-signal decode failures (e.g. "Payload too short") are visible
            # via the row's status pill; we deliberately do NOT increment the
            # status-bar Errors counter for them — that field is reserved for
            # wire-level CRC failures, sourced from the worker.
        # NOTE: _redraw_plot() is intentionally NOT called here.
        # It is called once per batch in _flush_ui() to avoid per-packet redraws.












    # ------------------------------------------------------------------
    # Hover crosshair + value readout
    # ------------------------------------------------------------------

    def _on_plot_trigger_clicked(self) -> None:
        if not self._config:
            self._popup_warning("Trigger", "Load a configuration first.")
            return
        if self._plot_trigger is not None:
            # Currently armed; disarm it.
            self._plot_trigger = None
            if hasattr(self, "_trigger_btn"):
                self._trigger_btn.setText("Trigger...")
                self._trigger_btn.setStyleSheet("")
            return

        from .dialogs import PlotTriggerDialog
        signals = [s.signal_name for s in self._config.all_signals]
        # Add calc groups to available triggers
        for calc in self._config.calc_groups:
            signals.append(f"{calc.group} {calc.stat}")

        dlg = PlotTriggerDialog(signals, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._plot_trigger = dlg.get_trigger()
            self._set_plot_live(True, source="trigger")  # Ensure we are live to catch it
            if hasattr(self, "_trigger_btn"):
                self._trigger_btn.setText("Armed")
                self._trigger_btn.setStyleSheet("color: #e91e8c; font-weight: bold;")
                self._trigger_btn.setToolTip(f"Armed: {self._plot_trigger['param']} {self._plot_trigger['op']} {self._plot_trigger['value']}")

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






    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------


    def _refresh_action_state(self) -> None:
        ready = self._config is not None
        self._clear_action.setEnabled(ready)
        # Logging requires an active connection; _set_connection_ui controls this.
        # Only set enabled=True here if we're currently connected.
        self._logging_action.setEnabled(ready and self._serial is not None)
        # Flip the central stack: empty-state when no config, table view
        # once one is loaded. Guarded for the brief window during __init__
        # where _refresh_action_state can fire before _build_main_layout
        # has created the stack.
        stack = getattr(self, "_central_stack", None)
        if stack is not None:
            stack.setCurrentIndex(1 if ready else 0)

    def _set_connection_ui(self, connected: bool) -> None:
        self._unsolicited_detected = False
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
            from .theming import resolve_theme
            theme = str(self._settings.value("ui/theme", "dark"))
            if resolve_theme(theme) == "light":
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
                f"  font-size: 9pt;"
                f"}}"
            )
            toast.hide()
            self._toast_label = toast
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(toast.hide)

        toast.setText(text)
        toast.setMaximumWidth(int(self.width() * 0.7))
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

        lower_text = text.lower()
        if "queue full" in lower_text or "saturated" in lower_text or "dropped" in lower_text:
            if hasattr(self, "_warning_badge") and self._warning_badge is not None:
                self._warning_badge.setVisible(True)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._log_activity("[SESSION] Close requested by user")
        # Stop all recurring timers FIRST so they can't fire during teardown.
        self._ui_timer.stop()
        if hasattr(self, "_y_autofit_timer"):
            self._y_autofit_timer.stop()
        if hasattr(self, "_reconnect_timer"):
            self._reconnect_timer.stop()
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

