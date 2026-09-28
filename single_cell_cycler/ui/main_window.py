"""Main Window for Single-Cell BMS Cell Cycler Application."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import serial.tools.list_ports
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..comm.packet_codec import (
    BoardParamsTelemetry,
    CellDataTelemetry,
    FaultSoCTelemetry,
)
from ..comm.protocol_defs import DEFAULT_BAUD_RATE
from ..comm.transceiver import SerialTransceiver, TransceiverState
from ..config.cycler_config import DEFAULT_LOG_DIR
from ..core.cycler_engine import CyclerEngine, EngineState
from ..core.metrics_tracker import CycleSummary, StepMetrics
from ..data.async_logger import AsyncTelemetryLogger
from ..data.summary_writer import write_cycle_summary_csv, write_step_summary_csv
from .theme import (
    BG_CARD,
    COLOR_ACCENT,
    COLOR_CHARGE,
    COLOR_DANGER,
    COLOR_WARNING,
    MAIN_STYLESHEET,
)
from .widgets.kpi_dashboard import KPIDashboard
from .widgets.live_plots import LivePlotWidget
from .widgets.manual_control import ManualControlWidget
from .widgets.profile_editor import ProfileEditorWidget
from .widgets.safety_panel import SafetyPanelWidget
from .widgets.step_tracker_table import StepTrackerTableWidget

logger = logging.getLogger("SingleCellCycler.MainWindow")


class MainWindow(QMainWindow):
    """Master window for Single-Cell BMS Cell Cycler."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Bytehound Single-Cell BMS Cycler & Characterization Workstation")
        self.resize(1340, 880)
        self.setStyleSheet(MAIN_STYLESHEET)

        # 1. Background Workers & Engines
        self.transceiver = SerialTransceiver(parent=self)
        self.engine = CyclerEngine(command_sender=self._on_command_dispatch, parent=self)
        self.logger = AsyncTelemetryLogger(log_dir=DEFAULT_LOG_DIR)
        self._last_board_params: Optional[BoardParamsTelemetry] = None
        self._last_fault_soc: Optional[FaultSoCTelemetry] = None

        # 2. UI Layout
        self._setup_ui()
        self._wire_signals()
        self._refresh_com_ports()

    def _setup_ui(self) -> None:
        # Toolbar
        self.toolbar = QToolBar("Controls")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # Port & Baud controls
        self.toolbar.addWidget(QLabel("Port: "))
        self.combo_port = QComboBox()
        self.combo_port.setMinimumWidth(110)
        self.toolbar.addWidget(self.combo_port)

        self.btn_refresh_ports = QPushButton("↻")
        self.btn_refresh_ports.setToolTip("Refresh COM ports")
        self.btn_refresh_ports.clicked.connect(self._refresh_com_ports)
        self.toolbar.addWidget(self.btn_refresh_ports)

        self.toolbar.addWidget(QLabel(" Baud: "))
        self.combo_baud = QComboBox()
        for baud in [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]:
            self.combo_baud.addItem(str(baud), baud)
        self.combo_baud.setCurrentText("115200")
        self.toolbar.addWidget(self.combo_baud)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self._toggle_connection)
        self.toolbar.addWidget(self.btn_connect)

        # Active Cell Selection (0x6000 Bit 1)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Cell: "))
        self.combo_active_cell = QComboBox()
        self.combo_active_cell.addItem("Cell 1", 1)
        self.combo_active_cell.addItem("Cell 2", 2)
        self.combo_active_cell.setToolTip("Active cell relay position (0x6000 Bit 1: 0=Cell 1, 1=Cell 2)")
        self.combo_active_cell.currentIndexChanged.connect(self._on_cell_selection_changed)
        self.toolbar.addWidget(self.combo_active_cell)

        # Test Execution Controls
        self.toolbar.addSeparator()
        self.btn_start = QPushButton("▶  START TEST")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self._start_test)
        self.toolbar.addWidget(self.btn_start)

        self.btn_pause = QPushButton("⏸  Pause")
        self.btn_pause.setObjectName("btn_pause")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.toolbar.addWidget(self.btn_pause)

        self.btn_skip = QPushButton("⏭  Skip Step")
        self.btn_skip.setEnabled(False)
        self.btn_skip.clicked.connect(self.engine.skip_step)
        self.toolbar.addWidget(self.btn_skip)

        self.btn_stop = QPushButton("⏹  Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_test)
        self.toolbar.addWidget(self.btn_stop)

        # Spacer and Emergency Stop
        spacer = QWidget()
        spacer.setSizePolicy(
            self.toolbar.sizePolicy().horizontalPolicy().Expanding,
            self.toolbar.sizePolicy().verticalPolicy().Preferred,
        )
        self.toolbar.addWidget(spacer)

        self.btn_estop = QPushButton("🛑 EMERGENCY STOP")
        self.btn_estop.setObjectName("btn_estop")
        self.btn_estop.clicked.connect(self._emergency_stop)
        self.toolbar.addWidget(self.btn_estop)

        # Central Layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Top Section: KPI Dashboard
        self.dashboard = KPIDashboard()
        main_layout.addWidget(self.dashboard)

        # 2. Bottom Section: Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=1)

        # Tab 1: Live Plotting Suite
        self.live_plots = LivePlotWidget()
        self.tabs.addTab(self.live_plots, "Live Charts")

        # Tab 2: Test Profile Sequencer
        self.profile_editor = ProfileEditorWidget()
        self.tabs.addTab(self.profile_editor, "Test Recipe Sequencer")

        # Tab 3: Step & Cycle Tracker Table
        self.tracker_table = StepTrackerTableWidget()
        self.tabs.addTab(self.tracker_table, "Execution Tracker & History")

        # Tab 4: Manual Hardware Override
        self.manual_control = ManualControlWidget(command_sender=self._on_command_dispatch)
        self.tabs.addTab(self.manual_control, "Manual Hardware Control")

        # Tab 5: Safety & BMS Fault Panel
        self.safety_panel = SafetyPanelWidget(reset_callback=self._on_reset_safety)
        self.tabs.addTab(self.safety_panel, "BMS Safety & Diagnostics")

        # Status Bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.lbl_status_comm = QLabel("Comm: Disconnected")
        self.lbl_status_engine = QLabel("Engine: Idle")
        self.lbl_status_stats = QLabel("RX: 0 | TX: 0")
        self.lbl_status_log = QLabel("Log: Idle")

        self.statusBar.addPermanentWidget(self.lbl_status_comm)
        self.statusBar.addPermanentWidget(self.lbl_status_engine)
        self.statusBar.addPermanentWidget(self.lbl_status_stats)
        self.statusBar.addPermanentWidget(self.lbl_status_log)

    def _wire_signals(self) -> None:
        # Transceiver signals
        self.transceiver.connection_changed.connect(self._on_connection_changed)
        self.transceiver.cell_data_received.connect(self._on_cell_data)
        self.transceiver.board_params_received.connect(self._on_board_params)
        self.transceiver.fault_soc_received.connect(self._on_fault_soc)
        self.transceiver.command_transmitted.connect(self._on_command_transmitted)
        self.transceiver.stats_updated.connect(self._on_stats_updated)

        # Engine signals
        self.engine.state_changed.connect(self._on_engine_state_changed)
        self.engine.step_started.connect(self._on_step_started)
        self.engine.step_completed.connect(self._on_step_completed)
        self.engine.cycle_completed.connect(self._on_cycle_completed)
        self.engine.recipe_completed.connect(self._on_recipe_completed)
        self.engine.safety_tripped.connect(self._on_safety_tripped)

        # Profile editor
        self.profile_editor.recipe_loaded.connect(self._on_recipe_loaded)
        if self.profile_editor.current_recipe:
            self.engine.load_recipe(self.profile_editor.current_recipe)

    def _refresh_com_ports(self) -> None:
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.combo_port.addItem(f"{p.device} ({p.description})", p.device)
        if not ports:
            self.combo_port.addItem("No COM ports", "")

    def _toggle_connection(self) -> None:
        if self.transceiver.isRunning():
            self.transceiver.disconnect_serial()
            self.btn_connect.setText("Connect")
        else:
            port = self.combo_port.currentData()
            if not port:
                QMessageBox.warning(self, "No Port", "Please select a valid COM port")
                return
            baud = self.combo_baud.currentData()
            self.transceiver.connect_serial(port, baud)
            self.btn_connect.setText("Disconnect")

    def _on_connection_changed(self, state: str, msg: str) -> None:
        self.lbl_status_comm.setText(f"Comm: {state}")
        self.statusBar.showMessage(msg, 3000)

    def _on_command_dispatch(self, frame_id: int, payload_byte: int, priority: int = 1) -> None:
        self.transceiver.send_command(frame_id, payload_byte, priority)

    def _on_cell_data(self, data: CellDataTelemetry) -> None:
        self.dashboard.update_cell_data(data)
        self.engine.on_cell_telemetry(data)

        step_m = self.engine.metrics_tracker.current_step_metrics
        step_mah = step_m.capacity_mah if step_m else 0.0
        self.live_plots.add_telemetry(data, step_mah)

        if self.engine.state == EngineState.RUNNING:
            mt = self.engine.metrics_tracker
            self.dashboard.update_metrics(
                step_mah=mt.current_step_metrics.capacity_mah if mt.current_step_metrics else 0.0,
                step_mwh=mt.current_step_metrics.energy_mwh if mt.current_step_metrics else 0.0,
                tot_chg_mah=mt.cumulative_charge_mah,
                tot_dis_mah=mt.cumulative_discharge_mah,
                tot_chg_mwh=mt.cumulative_charge_mwh,
                tot_dis_mwh=mt.cumulative_discharge_mwh,
                cycle_idx=self.engine.current_cycle,
                step_name=self.engine.active_step.name if self.engine.active_step else "Idle",
            )

            # Log record with merged board params & faults
            bp = self._last_board_params
            fs = self._last_fault_soc
            self.logger.log_record({
                "timestamp_iso": "",
                "epoch_s": data.timestamp,
                "cycle_index": self.engine.current_cycle,
                "step_index": self.engine.current_step_idx + 1,
                "step_name": self.engine.active_step.name if self.engine.active_step else "",
                "step_type": self.engine.active_step.step_type.value if self.engine.active_step else "",
                "voltage_v": data.voltage,
                "current_a": data.current,
                "power_w": round(data.voltage * data.current, 3),
                "terminal_temp_c": data.terminal_temp,
                "body_temp_c": data.body_temp,
                "ambient_temp_c": bp.ambient_temp if bp else 0.0,
                "charge_bus_v": bp.charge_voltage if bp else 0.0,
                "load_bus_v": bp.load_voltage if bp else 0.0,
                "soc_ocv_pct": fs.soc_ocv if fs else 0.0,
                "soc_cc_pct": fs.soc_cc if fs else 0.0,
                "fault_byte": fs.fault_byte if fs else 0,
                "step_capacity_mah": round(step_mah, 2),
                "step_energy_mwh": round(step_m.energy_mwh if step_m else 0.0, 2),
                "total_charge_mah": round(mt.cumulative_charge_mah, 2),
                "total_discharge_mah": round(mt.cumulative_discharge_mah, 2),
            })

    def _on_cell_selection_changed(self, index: int) -> None:
        cell_num = self.combo_active_cell.currentData()
        self.engine.selected_cell = cell_num
        logger.info(f"Active test cell set to: Cell {cell_num}")
        # If test is actively running, update hardware relay connection immediately
        if self.engine.state == EngineState.RUNNING and self.engine.active_step:
            self.engine._apply_hardware_for_step(self.engine.active_step)

    def _on_command_transmitted(self, frame_id: int, payload_byte: int, wire_bytes: bytes) -> None:
        hex_wire = wire_bytes.hex(" ").upper()
        logger.info(f"TX Frame 0x{frame_id:04X} -> Payload: 0x{payload_byte:02X} [{hex_wire}]")
        self.statusBar.showMessage(f"TX: 0x{frame_id:04X} (0x{payload_byte:02X}) -> {hex_wire}", 2500)

    def _on_board_params(self, params: BoardParamsTelemetry) -> None:
        self._last_board_params = params
        self.dashboard.update_board_params(params)

    def _on_fault_soc(self, fault_soc: FaultSoCTelemetry) -> None:
        self._last_fault_soc = fault_soc
        self.dashboard.update_fault_soc(fault_soc)
        self.safety_panel.update_faults(fault_soc)
        self.engine.on_fault_soc_telemetry(fault_soc)

    def _on_stats_updated(self, rx: int, tx: int, err: int) -> None:
        self.lbl_status_stats.setText(f"RX: {rx} | TX: {tx} | Err: {err}")

    def _on_recipe_loaded(self, recipe) -> None:
        self.engine.load_recipe(recipe)

    def _start_test(self) -> None:
        import time
        now = time.time()
        time_since_telemetry = now - self.engine.safety_monitor.last_telemetry_time

        # Pre-flight check: Ensure communication link is active
        if not self.transceiver.isRunning():
            QMessageBox.warning(
                self,
                "Not Connected",
                "Cannot start test: No active serial connection.\n\n"
                "Please select your BMS hardware COM port and click 'Connect' before starting the test.",
            )
            return

        if time_since_telemetry > 3.0:
            QMessageBox.warning(
                self,
                "Telemetry Link Offline",
                f"Cannot start test: No telemetry received for {time_since_telemetry:.1f} seconds.\n\n"
                "Please verify that your single-cell BMS board is powered, connected, and transmitting.",
            )
            return

        try:
            # Start background logger
            rec_name = self.engine.recipe.recipe_name.lower().replace(" ", "_") if self.engine.recipe else "test"
            log_path = self.logger.start_session(session_prefix=rec_name)
            self.lbl_status_log.setText(f"Logging: {log_path.name}")

            self.live_plots.reset_all()
            self.tracker_table.reset_all()
            self.engine.start_test()

            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_skip.setEnabled(True)
            self.btn_stop.setEnabled(True)
        except Exception as exc:
            QMessageBox.critical(self, "Start Error", str(exc))

    def _toggle_pause(self) -> None:
        if self.engine.state == EngineState.RUNNING:
            self.engine.pause_test()
            self.btn_pause.setText("▶ Resume")
        elif self.engine.state == EngineState.PAUSED:
            self.engine.resume_test()
            self.btn_pause.setText("⏸ Pause")

    def _stop_test(self) -> None:
        self.engine.stop_test()
        self._finish_ui_session("Test Stopped")

    def _emergency_stop(self) -> None:
        self.engine.emergency_stop()
        self._finish_ui_session("EMERGENCY STOP")

    def _on_reset_safety(self) -> None:
        self.engine.safety_monitor.reset_safety()
        self.engine._set_state(EngineState.IDLE, "Safety Interlock Reset")

    def _on_safety_tripped(self, reason: str) -> None:
        import os
        self.safety_panel.set_tripped(reason)
        self._finish_ui_session(f"SAFETY TRIP: {reason}")
        if self.isVisible() and os.getenv("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.critical(self, "Safety Interlock Tripped", reason)

    def _on_step_started(self, cycle_idx: int, step_idx: int, name: str, stype: str) -> None:
        self.tracker_table.set_active_step(cycle_idx, step_idx, name, stype)
        self.live_plots.reset_step_vq()

    def _on_step_completed(self, metrics: StepMetrics) -> None:
        self.tracker_table.add_completed_step(metrics)

    def _on_cycle_completed(self, summary: CycleSummary) -> None:
        self.live_plots.add_cycle_summary(summary.cycle_index, summary.discharge_capacity_mah, summary.coulombic_efficiency_pct)

    def _on_recipe_completed(self, msg: str) -> None:
        import os
        self._finish_ui_session("Completed")
        if self.isVisible() and os.getenv("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.information(self, "Test Completed", msg)

    def _on_engine_state_changed(self, state: str, msg: str) -> None:
        self.lbl_status_engine.setText(f"Engine: {state}")
        self.statusBar.showMessage(msg, 3000)

    def _finish_ui_session(self, status: str) -> None:
        self.logger.stop_session()
        self.lbl_status_log.setText("Log: Idle")
        self.tracker_table.set_idle(f"STATUS: {status.upper()}")

        # Export completed step and cycle summaries
        if self.engine.metrics_tracker.step_history:
            sum_path = DEFAULT_LOG_DIR / f"summary_steps_{int(self.engine.metrics_tracker.total_test_start_time)}.csv"
            write_step_summary_csv(sum_path, self.engine.metrics_tracker.step_history)
        if self.engine.metrics_tracker.cycle_summaries:
            csum_path = DEFAULT_LOG_DIR / f"summary_cycles_{int(self.engine.metrics_tracker.total_test_start_time)}.csv"
            write_cycle_summary_csv(csum_path, self.engine.metrics_tracker.cycle_summaries)

        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        self.btn_skip.setEnabled(False)
        self.btn_stop.setEnabled(False)

    def closeEvent(self, event) -> None:
        self.engine.emergency_stop()
        self.transceiver.disconnect_serial()
        self.logger.stop_session()
        event.accept()
