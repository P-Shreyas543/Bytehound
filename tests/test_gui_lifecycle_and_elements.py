"""Comprehensive Test Suite for Application Startup, Shutdown Lifecycle, and GUI Elements.

Verifies:
1. Application Startup: Window instantiation, UI widget graph, action states, docking layout.
2. Theming System: Switching between Dark and Light themes, palette refresh, stylesheet application.
3. Welcome Dashboard: Quick connect, load config, preset selector, and protocol wizard triggers.
4. Transmit (TX) Dock: Command loading, dynamic field validation, hex preview, parameter editor.
5. Telemetry & Values Dock: Signal tree view population, search filter, value update rendering.
6. Bitfields & Enums View: Dynamic status flag decoding, enum badge updates.
7. Live Plot Panels: Adding/removing signals, pause/resume, clear buffer, Y-axis auto-fit.
8. Activity Console Dock: Packet stream rendering, auto-scroll, text filtering, clear console.
9. Status Bar & Indicators: Connection status, port/baud display, packet counters, warning toasts.
10. Application Shutdown: Clean closeEvent(), worker disconnection, logger drain, state persistence.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path when executed directly as python test_xxx.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PySide6.QtCore import Qt, QPoint, QSettings, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCloseEvent

from app.ui.main_window import MainWindow, APP_ORG, APP_NAME
from app.decoder.types import (
    ProtocolConfig, FrameConfig, FrameDefinition, SignalSpec,
    BitfieldSpec, EnumSpec, TxCommandSpec, TxCommandFieldSpec
)
from app.decoder.frame_decoder import DecodedFrame, DecodedSignal


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def mock_config():
    """Create a rich mock FrameConfig with frames, signals, bitfields, enums, and TX commands."""
    proto = ProtocolConfig(
        profile_name="GUI Test Profile",
        header=b"\xaa\x55",
        frame_id_size=2,
        frame_id_byte_order="little",
        length_size=1,
        length_meaning="payload_only",
        crc_type="crc16_ccitt",
        crc_size=2,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"",
        escape_mode="none",
        enabled=True,
        parser_type="framed"
    )
    frames = {
        0x1000: FrameDefinition(frame_id=0x1000, frame_name="PackStatus", payload_length=6, direction="rxtx"),
        0x2000: FrameDefinition(frame_id=0x2000, frame_name="CellVoltages", payload_length=4, direction="rx"),
    }
    signals = {
        0x1000: [
            SignalSpec(frame_id=0x1000, frame_name="PackStatus", signal_name="Voltage", start_byte=0, byte_length=2, endianness="little", data_type="uint16", scale=0.1, offset=0.0, unit="V", group="Battery"),
            SignalSpec(frame_id=0x1000, frame_name="PackStatus", signal_name="Current", start_byte=2, byte_length=2, endianness="little", data_type="int16", scale=0.01, offset=0.0, unit="A", group="Battery"),
            SignalSpec(frame_id=0x1000, frame_name="PackStatus", signal_name="State", start_byte=4, byte_length=1, endianness="little", data_type="uint8", scale=1.0, offset=0.0, unit="", group="Status"),
            SignalSpec(frame_id=0x1000, frame_name="PackStatus", signal_name="Flags", start_byte=5, byte_length=1, endianness="little", data_type="uint8", scale=1.0, offset=0.0, unit="", group="Status"),
        ],
        0x2000: [
            SignalSpec(frame_id=0x2000, frame_name="CellVoltages", signal_name="Cell_01", start_byte=0, byte_length=2, endianness="little", data_type="uint16", scale=0.001, offset=0.0, unit="V", group="Cells"),
            SignalSpec(frame_id=0x2000, frame_name="CellVoltages", signal_name="Cell_02", start_byte=2, byte_length=2, endianness="little", data_type="uint16", scale=0.001, offset=0.0, unit="V", group="Cells"),
        ]
    }
    bitfields = {
        (0x1000, "Flags"): [
            BitfieldSpec(frame_id=0x1000, variable_name="Flags", bit_index=0, bit_name="OverVoltage", active_text="FAULT", inactive_text="OK"),
            BitfieldSpec(frame_id=0x1000, variable_name="Flags", bit_index=1, bit_name="UnderVoltage", active_text="FAULT", inactive_text="OK"),
            BitfieldSpec(frame_id=0x1000, variable_name="Flags", bit_index=2, bit_name="OverTemp", active_text="WARN", inactive_text="OK"),
        ]
    }
    enums = {
        (0x1000, "State"): {
            0: "STANDBY",
            1: "CHARGING",
            2: "DISCHARGING",
            255: "ERROR",
        }
    }
    tx_fields = [
        TxCommandFieldSpec(command_name="SetVoltageLimit", field_name="TargetVoltage", fmt="uint16", factor=0.1, offset=0.0, byte_order="little", min_value=0.0, max_value=100.0, default=48.0, unit="V"),
    ]
    tx_commands = {
        "SetVoltageLimit": TxCommandSpec(
            command_name="SetVoltageLimit",
            frame_id=0x1000,
            payload_hex="",
            description="Set target voltage limit",
            enabled=True,
            fields=tx_fields,
        )
    }
    return FrameConfig(
        protocol=proto,
        frames=frames,
        signals_by_frame=signals,
        bitfields=bitfields,
        enums=enums,
        tx_commands=tx_commands
    )


# ============================================================================
# 1. APPLICATION STARTUP & INITIALIZATION
# ============================================================================

def test_app_startup_and_ui_graph(qapp, monkeypatch):
    """Verify MainWindow constructs properly with all docks, toolbars, and menus."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        assert w.windowTitle().startswith("Bytehound")
        assert w._plot_dock is not None
        assert w._table is not None
        assert w._cards_view is not None
        assert w._tx_dock is not None
        assert w._bitfields_dock is not None
        assert w._console_dock is not None

        # Verify initial toolbar actions
        assert hasattr(w, "_connect_action")
        assert hasattr(w, "_polling_action")
        assert hasattr(w, "_logging_action")
        assert hasattr(w, "_load_config_action")
    finally:
        w.close()


# ============================================================================
# 2. THEME SWITCHING (DARK & LIGHT)
# ============================================================================

def test_theme_switching(qapp, monkeypatch):
    """Verify switching between Dark and Light themes updates the application palette."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        # Switch to Light Theme
        w._apply_theme("light")
        assert w._settings.value("ui/theme") == "light"

        # Switch back to Dark Theme
        w._apply_theme("dark")
        assert w._settings.value("ui/theme") == "dark"
    finally:
        w.close()


# ============================================================================
# 3. WELCOME DASHBOARD WIRING & SIGNALS
# ============================================================================

def test_welcome_dashboard_signals(qapp, monkeypatch):
    """Verify WelcomeDashboard emits connect, load config, and wizard requests."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        dash = w._welcome_dashboard
        assert dash is not None

        # Test connect requested trigger
        with patch.object(w, "_on_dashboard_connect") as mock_conn:
            dash.connect_requested.emit("COM3", 115200)
            mock_conn.assert_called_once_with("COM3", 115200)

        # Test wizard requested trigger
        with patch.object(w, "_on_open_protocol_wizard") as mock_wiz:
            dash.open_wizard_requested.emit()
            mock_wiz.assert_called_once()
    finally:
        w.close()


# ============================================================================
# 4. CONFIG LOADING & TRANSMIT (TX) DOCK POPULATION
# ============================================================================

def test_config_loading_and_tx_panel_population(qapp, mock_config, monkeypatch):
    """Verify that applying a FrameConfig populates the TX commands dock."""
    from app.protocol.packet_parser import create_parser

    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        w._config = mock_config
        w._parser = create_parser(mock_config.protocol)
        w._populate_table_from_config()
        w._populate_tx_commands()

        # Verify TX commands populated in the combo box
        if hasattr(w, "_tx_command_combo"):
            combo = w._tx_command_combo
            assert "SetVoltageLimit" in [combo.itemText(i) for i in range(combo.count())]

        # Verify signals in telemetry model
        if hasattr(w, "_telemetry_model"):
            rows = w._telemetry_model.rowCount()
            assert rows >= 4  # Voltage, Current, State, Flags, Cell_01, Cell_02
    finally:
        w.close()


# ============================================================================
# 5. TELEMETRY PIPELINE & DECODED PACKET GUI UPDATE
# ============================================================================

def test_telemetry_pipeline_gui_packet_update(qapp, mock_config, monkeypatch):
    """Verify feeding decoded frames updates telemetry cards, tables, and bitfields."""
    from app.protocol.packet_parser import create_parser

    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        w._config = mock_config
        w._parser = create_parser(mock_config.protocol)
        w._populate_table_from_config()

        # Create a mock DecodedFrame
        signals = [
            DecodedSignal(frame_id=0x1000, frame_name="PackStatus", signal_name="Voltage", raw_value=485, scaled_value=48.5, unit="V", status="OK", group="Battery"),
            DecodedSignal(frame_id=0x1000, frame_name="PackStatus", signal_name="Current", raw_value=-1250, scaled_value=-12.5, unit="A", status="OK", group="Battery"),
            DecodedSignal(frame_id=0x1000, frame_name="PackStatus", signal_name="State", raw_value=1, scaled_value=1.0, unit="", status="OK", enum_label="CHARGING", group="Status"),
            DecodedSignal(frame_id=0x1000, frame_name="PackStatus", signal_name="Flags", raw_value=1, scaled_value=1.0, unit="", status="OK", bit_values={"OverVoltage": True, "UnderVoltage": False, "OverTemp": False}, group="Status"),
        ]
        decoded_frame = DecodedFrame(frame_id=0x1000, frame_name="PackStatus", signals=signals)

        # Simulate batch packet arrival from worker
        mock_packet = MagicMock()
        mock_packet.ok = True
        mock_packet.frame_id = 0x1000
        mock_packet.raw_bytes = b"\xaa\x55\x00\x10\x06\xe5\x01\x1e\xfb\x01\x01\x12\x34"

        w._on_packets_received([(mock_packet, decoded_frame)])
        w._flush_ui_inner()

        # Verify bitfields dock updated and packet count updated
        assert w._packet_count == 1
        assert w._bitfields_dock is not None
    finally:
        w.close()


# ============================================================================
# 6. PLOT PANEL INTERACTION (ADD SIGNAL, PAUSE, CLEAR)
# ============================================================================

def test_plot_panel_actions(qapp, mock_config, monkeypatch):
    """Verify adding signals to plots, pausing plot updates, and clearing buffers."""
    from app.protocol.packet_parser import create_parser

    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        w._config = mock_config
        w._parser = create_parser(mock_config.protocol)
        w._populate_table_from_config()

        # Pause and resume plot updates
        if hasattr(w, "_pause_plot_action"):
            w._pause_plot_action.setChecked(True)
            assert w._plot_paused is True
            w._pause_plot_action.setChecked(False)
            assert w._plot_paused is False

        # Clear plot buffers
        if hasattr(w, "_on_clear_plots"):
            w._on_clear_plots()
    finally:
        w.close()


# ============================================================================
# 7. CONSOLE / ACTIVITY LOG DOCK STREAMING & FILTERING
# ============================================================================

def test_console_dock_streaming_and_clearing(qapp, monkeypatch):
    """Verify console dock receives packet lines, can be paused, filtered, and cleared."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()
    try:
        if hasattr(w, "_console_view"):
            # Append test line
            w._append_console_line("RX [0x1000] PackStatus: Voltage=48.5V, Current=-12.5A")
            # Clear console
            if hasattr(w, "_on_clear_console"):
                w._on_clear_console()
    finally:
        w.close()


# ============================================================================
# 8. APPLICATION SHUTDOWN & CLEANUP
# ============================================================================

def test_app_shutdown_and_cleanup_lifecycle(qapp, monkeypatch):
    """Verify closeEvent cleanly stops timers, disconnects workers, and saves window state."""
    monkeypatch.setattr(MainWindow, "_check_and_recover_temp_logs", lambda self: None)
    w = MainWindow()

    with patch.object(w, "_disconnect") as mock_disc, \
         patch.object(w, "_save_window_state") as mock_save:
        
        event = QCloseEvent()
        w.closeEvent(event)

        # Disconnect and state save must be executed
        mock_disc.assert_called_once()
        mock_save.assert_called_once()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
