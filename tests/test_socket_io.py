from __future__ import annotations

import socket
import pytest
import serial
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.serial_io.serial_worker import TcpSocketWrapper, UdpSocketWrapper, SerialSettings
from app.ui.dialogs import ConnectionDialog
from app.decoder.types import SerialDefaults


# ------------------------------------------------------------------
# Socket Wrappers Tests
# ------------------------------------------------------------------

@patch("socket.socket")
def test_tcp_socket_wrapper_lifecycle(mock_socket_class):
    mock_sock = MagicMock()
    mock_socket_class.return_value = mock_sock

    wrapper = TcpSocketWrapper(host="127.0.0.1", port=8888)
    assert not wrapper.is_open

    # Test open
    wrapper.open()
    assert wrapper.is_open
    mock_socket_class.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
    mock_sock.connect.assert_called_once_with(("127.0.0.1", 8888))
    mock_sock.setblocking.assert_called_once_with(False)

    # Test write
    mock_sock.send.return_value = 5
    assert wrapper.write(b"hello") == 5
    mock_sock.send.assert_called_once_with(b"hello")

    # Test read / in_waiting / select
    with patch("select.select") as mock_select:
        ready_states = [([mock_sock], [], [])]
        mock_select.side_effect = lambda *args, **kwargs: ready_states.pop(0) if ready_states else ([], [], [])
        mock_sock.recv.return_value = b"world"
        
        # in_waiting triggers _fill_buffer
        assert wrapper.in_waiting == 5
        assert wrapper.read(5) == b"world"
        assert wrapper.in_waiting == 0

    # Test connection closed trigger
    with patch("select.select") as mock_select:
        mock_select.side_effect = [([mock_sock], [], [])]
        mock_sock.recv.return_value = b""
        with pytest.raises(serial.SerialException) as exc:
            _ = wrapper.in_waiting
        assert "closed by remote peer" in str(exc.value)

    # Test close
    wrapper.close()
    assert not wrapper.is_open
    mock_sock.close.assert_called_once()


@patch("socket.socket")
def test_udp_socket_wrapper_lifecycle(mock_socket_class):
    mock_sock = MagicMock()
    mock_socket_class.return_value = mock_sock

    # With local bind port
    wrapper = UdpSocketWrapper(host="127.0.0.1", port=9999, local_port=5000)
    wrapper.open()
    mock_sock.bind.assert_called_once_with(("", 5000))
    mock_sock.connect.assert_called_once_with(("127.0.0.1", 9999))
    mock_sock.setblocking.assert_called_once_with(False)

    # Test write
    mock_sock.send.return_value = 4
    assert wrapper.write(b"test") == 4
    mock_sock.send.assert_called_once_with(b"test")

    # Test close
    wrapper.close()
    mock_sock.close.assert_called_once()


# ------------------------------------------------------------------
# ConnectionDialog Page / Settings persistence Tests
# ------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fresh_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_connection_dialog_defaults_serial(qapp, fresh_settings):
    """By default, the dialog starts on the Serial page."""
    dlg = ConnectionDialog(fresh_settings)
    assert dlg._type_combo.currentData() == "serial"
    assert dlg._stack.currentIndex() == 0

    settings = dlg.get_settings()
    assert settings.connection_type == "serial"
    assert settings.baud_rate == 115200


def test_connection_dialog_switch_to_tcp(qapp, fresh_settings):
    dlg = ConnectionDialog(fresh_settings)
    
    # Change connection type to TCP Client
    dlg._type_combo.setCurrentIndex(1)  # Index 1 is TCP Client
    assert dlg._stack.currentIndex() == 1
    
    dlg._tcp_host.setText("192.168.1.50")
    dlg._tcp_port.setValue(9001)
    
    settings = dlg.get_settings()
    assert settings.connection_type == "tcp"
    assert settings.host == "192.168.1.50"
    assert settings.port_num == 9001
    assert settings.port == "192.168.1.50:9001"


def test_connection_dialog_switch_to_udp(qapp, fresh_settings):
    dlg = ConnectionDialog(fresh_settings)
    
    # Change connection type to UDP Client
    dlg._type_combo.setCurrentIndex(2)  # Index 2 is UDP Client
    assert dlg._stack.currentIndex() == 2
    
    dlg._udp_host.setText("10.0.0.5")
    dlg._udp_port.setValue(5002)
    dlg._udp_local_port.setValue(6002)
    
    settings = dlg.get_settings()
    assert settings.connection_type == "udp"
    assert settings.host == "10.0.0.5"
    assert settings.port_num == 5002
    assert settings.local_port == 6002
    assert settings.port == "10.0.0.5:5002"


def test_connection_dialog_settings_roundtrip(qapp, fresh_settings):
    # Set QSettings explicitly for TCP
    fresh_settings.setValue("conn/type", "tcp")
    fresh_settings.setValue("conn/tcp_host", "192.168.1.100")
    fresh_settings.setValue("conn/tcp_port", 8888)
    fresh_settings.setValue("conn/timeout_ms", "250")
    fresh_settings.setValue("conn/auto_reconnect", "true")

    dlg = ConnectionDialog(fresh_settings)
    assert dlg._type_combo.currentData() == "tcp"
    assert dlg._stack.currentIndex() == 1
    assert dlg._tcp_host.text() == "192.168.1.100"
    assert dlg._tcp_port.value() == 8888
    assert dlg._timeout_combo.currentText() == "250"
    assert dlg._auto_reconnect_chk.isChecked() is True

    # Accept the dialog to write back and check get_settings
    dlg._on_accept()
    settings = dlg.get_settings()
    assert settings.connection_type == "tcp"
    assert settings.host == "192.168.1.100"
    assert settings.port_num == 8888
    assert settings.timeout_ms == 250
    assert settings.auto_reconnect is True
