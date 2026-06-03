"""Tests for dialogs."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from app.ui.dialogs import PlotTriggerDialog, PollingConfigDialog, AboutDialog
from app.decoder.types import PollingScheduleSpec


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_plot_trigger_dialog(qapp):
    dlg = PlotTriggerDialog(["Voltage", "Current"])
    
    # Test setting values
    dlg._param_combo.setCurrentText("Voltage")
    dlg._op_combo.setCurrentText(">")
    dlg._val_spin.setValue(12.5)
    
    dlg._action_pause.setChecked(True)
    dlg._action_log.setChecked(False)
    
    res = dlg.get_trigger()
    assert res["param"] == "Voltage"
    assert res["op"] == ">"
    assert res["value"] == 12.5
    assert res["pause"] is True
    assert res["log"] is False


def test_polling_config_dialog_modbus(qapp):
    settings = QSettings("BytehoundTest", "Test")
    settings.clear()

    # Configure some settings
    settings.setValue("poll/pipelining", True)
    settings.setValue("poll/pipeline_depth", 4)

    schedules = [
        PollingScheduleSpec(target_id=0x01, interval_ms=1000, timeout_ms=100, enabled=True)
    ]

    # Test Modbus RTU is True
    dlg_modbus = PollingConfigDialog(schedules, settings, is_modbus=True)

    # Verify pipelining controls are disabled and checked state is False
    assert not dlg_modbus._pipeline_chk.isEnabled()
    assert not dlg_modbus._pipeline_chk.isChecked()
    assert not dlg_modbus._pipeline_depth.isEnabled()
    assert dlg_modbus._pipeline_depth.value() == 1

    enabled_pipe, depth, gap = dlg_modbus.get_pipelining()
    assert enabled_pipe is False
    assert depth == 1

    # Test Modbus RTU is False
    dlg_normal = PollingConfigDialog(schedules, settings, is_modbus=False)

    # Verify pipelining controls are enabled
    assert dlg_normal._pipeline_chk.isEnabled()
    assert dlg_normal._pipeline_chk.isChecked()
    assert dlg_normal._pipeline_depth.isEnabled()
    assert dlg_normal._pipeline_depth.value() == 4

    enabled_pipe, depth, gap = dlg_normal.get_pipelining()
    assert enabled_pipe is True
    assert depth == 4

    settings.clear()


def test_about_dialog(qapp):
    version_info = {
        "version": "1.2.3",
        "Developer": "Test Developer",
        "developer_github": "https://github.com/testdev",
        "publisher": "Test Publisher",
        "publisher_webpage": "https://example.com/pub",
        "build_date": "2026-01-01",
        "license": "MIT",
        "license_url": "https://example.com/license",
        "homepage": "https://example.com/home"
    }
    dlg = AboutDialog(version_info, logo_path=None)
    assert dlg.windowTitle() == "About Bytehound"
    assert dlg.isModal() is True


def test_frame_format_widget(qapp):
    from app.ui.widgets import FrameFormatWidget
    from app.decoder.types import ProtocolConfig, FrameConfig

    # 1. Modbus RTU
    p_modbus = ProtocolConfig(
        profile_name="Modbus Test",
        header=b"\x01",
        frame_id_size=1,
        frame_id_byte_order="big",
        length_size=1,
        length_meaning="payload_only",
        crc_type="crc16_modbus",
        crc_size=2,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"",
        escape_mode="none",
        enabled=True,
        parser_type="modbus_rtu",
        modbus_node_address=5
    )
    cfg_modbus = FrameConfig(protocol=p_modbus)
    w_modbus = FrameFormatWidget(cfg_modbus)
    # Check that it builds grid cells inside _grid_widget
    layout = w_modbus._grid_widget.layout()
    assert layout is not None
    from PySide6.QtWidgets import QLabel
    labels = [layout.itemAt(i).widget() for i in range(layout.count()) if isinstance(layout.itemAt(i).widget(), QLabel)]
    # We should have "Byte 0" to "Byte 7" (8 bytes total) in row 0, and the spanned labels in row 1
    assert len(labels) > 8

    # 2. Framed Protocol
    p_framed = ProtocolConfig(
        profile_name="Framed Test",
        header=b"\xAA\x55",
        frame_id_size=2,
        frame_id_byte_order="big",
        length_size=1,
        length_meaning="payload_only",
        crc_type="crc16_modbus",
        crc_size=2,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"\x0D",
        escape_mode="none",
        enabled=True,
        parser_type="framed"
    )
    cfg_framed = FrameConfig(protocol=p_framed)
    w_framed = FrameFormatWidget(cfg_framed)
    layout_framed = w_framed._grid_widget.layout()
    assert layout_framed is not None
    labels_framed = [layout_framed.itemAt(i).widget() for i in range(layout_framed.count()) if isinstance(layout_framed.itemAt(i).widget(), QLabel)]
    assert len(labels_framed) > 10

    # 3. Framed Protocol with tx_pad_length
    p_padded = ProtocolConfig(
        profile_name="Padded Test",
        header=b"\xAA\x55",
        frame_id_size=2,
        frame_id_byte_order="big",
        length_size=1,
        length_meaning="payload_only",
        crc_type="crc16_modbus",
        crc_size=2,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"",
        escape_mode="none",
        enabled=True,
        parser_type="framed",
        tx_pad_length=12
    )
    cfg_padded = FrameConfig(protocol=p_padded)
    w_padded = FrameFormatWidget(cfg_padded)
    layout_padded = w_padded._grid_widget.layout()
    assert layout_padded is not None
    labels_padded = [layout_padded.itemAt(i).widget() for i in range(layout_padded.count()) if isinstance(layout_padded.itemAt(i).widget(), QLabel)]
    byte_labels = [l for l in labels_padded if l.text().startswith("Byte ")]
    assert len(byte_labels) == 12

    # 4. Framed Protocol with TX commands and Tab Widget
    p_tx = ProtocolConfig(
        profile_name="TX Test",
        header=b"\xAA\x55",
        frame_id_size=2,
        frame_id_byte_order="big",
        length_size=1,
        length_meaning="payload_only",
        crc_type="crc16_modbus",
        crc_size=2,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"",
        escape_mode="none",
        enabled=True,
        parser_type="framed",
    )
    from app.decoder.types import TxCommandSpec, TxCommandFieldSpec
    tx_cmds = {
        "TestCmd": TxCommandSpec(
            command_name="TestCmd",
            frame_id=0x1000,
            payload_hex="AA BB",
            description="Test Description",
            enabled=True,
            fields=[
                TxCommandFieldSpec(
                    command_name="TestCmd",
                    field_name="Field1",
                    fmt="uint16",
                    byte_order="little",
                    factor=1.0,
                    offset=0.0
                )
            ]
        )
    }
    cfg_tx = FrameConfig(protocol=p_tx, tx_commands=tx_cmds)
    w_tx = FrameFormatWidget(cfg_tx)

    assert hasattr(w_tx, "_tab_widget")
    assert w_tx._tab_widget.count() == 2

    assert w_tx._tx_combo.count() == 2  # default + TestCmd
    w_tx._tx_combo.setCurrentIndex(1)
    
    assert w_tx._tx_grid_widget is not None
    layout_tx = w_tx._tx_grid_widget.layout()
    assert layout_tx is not None
    labels_tx = [layout_tx.itemAt(i).widget() for i in range(layout_tx.count()) if isinstance(layout_tx.itemAt(i).widget(), QLabel)]
    has_field_label = any(l.text() == "Field1" or "Field1" in l.text() for l in labels_tx)
    assert has_field_label

    # 5. Modbus RTU Protocol with TX commands and Tab Widget
    p_modbus_tx = ProtocolConfig(
        profile_name="Modbus TX Test",
        header=b"\x01",
        frame_id_size=1,
        frame_id_byte_order="big",
        length_size=1,
        length_meaning="payload_only",
        crc_type="crc16_modbus",
        crc_size=2,
        crc_byte_order="little",
        crc_coverage="header_to_payload",
        footer=b"",
        escape_mode="none",
        enabled=True,
        parser_type="modbus_rtu",
        modbus_node_address=5
    )
    tx_cmds_modbus = {
        "WriteReg": TxCommandSpec(
            command_name="WriteReg",
            frame_id=0x2000,
            payload_hex="CC DD",
            description="Modbus Write Command",
            enabled=True,
            fields=[]
        ),
        "WriteMultiple": TxCommandSpec(
            command_name="WriteMultiple",
            frame_id=0x2000,
            payload_hex="11 22 33 44",
            description="Modbus Write Multiple Command",
            enabled=True,
            fields=[]
        )
    }
    cfg_modbus_tx = FrameConfig(protocol=p_modbus_tx, tx_commands=tx_cmds_modbus)
    w_modbus_tx = FrameFormatWidget(cfg_modbus_tx)

    assert hasattr(w_modbus_tx, "_tab_widget")
    assert w_modbus_tx._tx_combo.count() == 3  # default + WriteReg + WriteMultiple
    
    # Select WriteReg (total payload size = 2, so FC 06)
    w_modbus_tx._tx_combo.setCurrentIndex(1)
    layout_mr = w_modbus_tx._tx_grid_widget.layout()
    labels_mr = [layout_mr.itemAt(i).widget() for i in range(layout_mr.count()) if isinstance(layout_mr.itemAt(i).widget(), QLabel)]
    assert any("Func Code" in l.text() for l in labels_mr)
    
    # Select WriteMultiple (total payload size = 4, so FC 16)
    w_modbus_tx._tx_combo.setCurrentIndex(2)
    layout_wm = w_modbus_tx._tx_grid_widget.layout()
    labels_wm = [layout_wm.itemAt(i).widget() for i in range(layout_wm.count()) if isinstance(layout_wm.itemAt(i).widget(), QLabel)]
    assert any("Func Code" in l.text() for l in labels_wm)


def test_report_issue_dialog_and_reporter(qapp, monkeypatch):
    import urllib.request
    from app.ui.dialogs import ReportIssueDialog, QMessageBox
    from app.ui.report_issue import IssueReporter

    # Mock QMessageBox warning
    warn_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, message: warn_calls.append((title, message)),
    )

    dlg = ReportIssueDialog()
    assert dlg.windowTitle() == "Report Issue"

    # Test validation on empty
    dlg._on_accept()
    assert len(warn_calls) == 1
    assert "Title" in warn_calls[0][1]

    # Test description validation
    dlg._title_input.setText("Test Title")
    dlg._on_accept()
    assert len(warn_calls) == 2
    assert "Description" in warn_calls[1][1]

    # Test valid accept
    dlg._desc_input.setPlainText("Test Description")
    dlg._on_accept()
    assert len(warn_calls) == 2

    title, desc, include_log = dlg.get_data()
    assert title == "Test Title"
    assert desc == "Test Description"
    assert include_log is True

    # Test IssueReporter
    class MockResponse:
        def __init__(self, status):
            self.status = status
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    reporter = IssueReporter("My Title", "My Desc", "My Diag", "My Log")
    finished_calls = []
    reporter.finished.connect(lambda s, m: finished_calls.append((s, m)))

    # Mock successful POST (HTTP 201)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, *args, **kwargs: MockResponse(201),
    )
    reporter.run()
    assert len(finished_calls) == 1
    assert finished_calls[0][0] is True
    assert "successfully" in finished_calls[0][1]

    # Mock failed POST (HTTP 400)
    finished_calls.clear()
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, *args, **kwargs: MockResponse(400),
    )
    reporter.run()
    assert len(finished_calls) == 1
    assert finished_calls[0][0] is False
    assert "Status code: 400" in finished_calls[0][1]



