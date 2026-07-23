"""Tests for PrinterConnection interface and implementations."""

import socket
from unittest.mock import MagicMock, patch

import pytest

from print_agent.connections.base import (
    PrinterConnection,
    PrinterConnectionError,
    PrinterNotAvailableError,
)
from print_agent.connections.usb import UsbPrinterConnection
from print_agent.connections.network import NetworkPrinterConnection


class TestPrinterConnectionInterface:
    """Verify the abstract interface contract."""

    def test_base_has_required_methods(self):
        assert hasattr(PrinterConnection, "connect")
        assert hasattr(PrinterConnection, "send")
        assert hasattr(PrinterConnection, "disconnect")
        assert hasattr(PrinterConnection, "is_available")

    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            PrinterConnection()


class TestUsbPrinterConnection:
    def test_send_writes_exact_bytes(self):
        conn = UsbPrinterConnection(vendor_id=0x0456, product_id=0x0808)
        mock_device = MagicMock()
        conn._device = mock_device

        data = b"\x1b\x40Hello\x1d\x56\x00"
        conn.send(data)

        mock_device.write.assert_called_once_with(data)

    def test_send_via_device_path(self):
        conn = UsbPrinterConnection(device_path="/dev/usb/lp0")
        mock_device = MagicMock()
        conn._device = mock_device

        conn.send(b"test")
        mock_device.write.assert_called_once_with(b"test")

    def test_connect_opens_device(self):
        with patch("escpos.escpos.Escpos") as MockEscpos:
            mock_instance = MagicMock()
            MockEscpos.return_value = mock_instance

            conn = UsbPrinterConnection(vendor_id=0x0456, product_id=0x0808)
            conn.connect()

            MockEscpos.assert_called_once()
            assert conn._device is not None

    def test_connect_failure_raises_connection_error(self):
        with patch("escpos.escpos.Escpos", side_effect=Exception("device not found")):
            conn = UsbPrinterConnection(vendor_id=0x0456, product_id=0x0808)
            with pytest.raises(PrinterConnectionError):
                conn.connect()

    def test_disconnect_closes_device(self):
        conn = UsbPrinterConnection(vendor_id=0x0456, product_id=0x0808)
        mock_device = MagicMock()
        conn._device = mock_device

        conn.disconnect()
        mock_device.close.assert_called_once()
        assert conn._device is None

    def test_disconnect_without_device_is_noop(self):
        conn = UsbPrinterConnection(vendor_id=0x0456, product_id=0x0808)
        conn.disconnect()  # should not raise

    def test_is_available_returns_false_when_no_device(self):
        conn = UsbPrinterConnection(vendor_id=0x0456, product_id=0x0808)
        assert conn.is_available() is False

    def test_is_available_returns_true_when_connected(self):
        conn = UsbPrinterConnection(vendor_id=0x0456, product_id=0x0808)
        conn._device = MagicMock()
        assert conn.is_available() is True

    def test_send_without_connection_raises(self):
        conn = UsbPrinterConnection(vendor_id=0x0456, product_id=0x0808)
        with pytest.raises(PrinterConnectionError, match="not connected"):
            conn.send(b"data")


class TestNetworkPrinterConnection:
    def test_send_writes_exact_bytes(self):
        conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
        mock_sock = MagicMock(spec=socket.socket)
        conn._socket = mock_sock

        data = b"\x1b\x40Hello\x1d\x56\x00"
        conn.send(data)

        mock_sock.sendall.assert_called_once_with(data)

    def test_connect_opens_socket(self):
        with patch("socket.socket") as MockSocket:
            mock_sock = MagicMock()
            MockSocket.return_value = mock_sock

            conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
            conn.connect()

            MockSocket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
            mock_sock.connect.assert_called_once_with(("10.0.0.1", 9100))
            assert conn._socket is mock_sock

    def test_connect_refused_raises_connection_error(self):
        with patch("socket.socket") as MockSocket:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            MockSocket.return_value = mock_sock

            conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
            with pytest.raises(PrinterConnectionError, match="refused"):
                conn.connect()

    def test_connect_timeout_raises_connection_error(self):
        with patch("socket.socket") as MockSocket:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = TimeoutError("timed out")
            MockSocket.return_value = mock_sock

            conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
            with pytest.raises(PrinterConnectionError, match="timed out"):
                conn.connect()

    def test_disconnect_closes_socket(self):
        conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
        mock_sock = MagicMock(spec=socket.socket)
        conn._socket = mock_sock

        conn.disconnect()
        mock_sock.close.assert_called_once()
        assert conn._socket is None

    def test_disconnect_without_socket_is_noop(self):
        conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
        conn.disconnect()  # should not raise

    def test_is_available_returns_false_when_no_socket(self):
        conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
        assert conn.is_available() is False

    def test_is_available_returns_true_when_connected(self):
        conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
        conn._socket = MagicMock(spec=socket.socket)
        assert conn.is_available() is True

    def test_send_without_connection_raises(self):
        conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
        with pytest.raises(PrinterConnectionError, match="not connected"):
            conn.send(b"data")

    def test_send_socket_error_raises_connection_error(self):
        conn = NetworkPrinterConnection(host="10.0.0.1", port=9100)
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.sendall.side_effect = OSError("broken pipe")
        conn._socket = mock_sock

        with pytest.raises(PrinterConnectionError):
            conn.send(b"data")


class TestNetworkPrinterConnectionIPv6:
    def test_ipv6_uses_af_inet6(self):
        with patch("socket.socket") as MockSocket:
            mock_sock = MagicMock()
            MockSocket.return_value = mock_sock

            conn = NetworkPrinterConnection(
                host="fe80::e273:e7ff:fe21:3c1e", port=9100
            )
            conn.connect()

            MockSocket.assert_called_once_with(socket.AF_INET6, socket.SOCK_STREAM)
            mock_sock.connect.assert_called_once_with(
                ("fe80::e273:e7ff:fe21:3c1e", 9100)
            )

    def test_ipv4_uses_af_inet(self):
        with patch("socket.socket") as MockSocket:
            mock_sock = MagicMock()
            MockSocket.return_value = mock_sock

            conn = NetworkPrinterConnection(host="192.168.1.1", port=9100)
            conn.connect()

            MockSocket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)

    def test_ipv6_loopback(self):
        with patch("socket.socket") as MockSocket:
            mock_sock = MagicMock()
            MockSocket.return_value = mock_sock

            conn = NetworkPrinterConnection(host="::1", port=9100)
            conn.connect()

            MockSocket.assert_called_once_with(socket.AF_INET6, socket.SOCK_STREAM)

    def test_ipv6_connect_failure(self):
        with patch("socket.socket") as MockSocket:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            MockSocket.return_value = mock_sock

            conn = NetworkPrinterConnection(
                host="fe80::1", port=9100
            )
            with pytest.raises(PrinterConnectionError, match="refused"):
                conn.connect()
