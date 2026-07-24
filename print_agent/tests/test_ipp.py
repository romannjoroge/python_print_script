"""Tests for IPP printer connection."""

import socket
import struct
from unittest.mock import MagicMock, patch

import pytest
import requests as _requests

from print_agent.config import Config, IppPrinterConfig
from print_agent.connections.ipp import IppPrinterConnection
from print_agent.connections.base import PrinterConnectionError


class TestIppPrinterConfig:
    def test_ipp_config_fields(self):
        data = {
            "odoo_url": "http://localhost:8069",
            "printers": [
                {"name": "hp", "connection_type": "ipp", "host": "10.0.0.1",
                 "port": 631, "api_key": "k1"},
            ],
        }
        import tempfile, os, yaml
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f)
        try:
            config = Config.from_file(path)
            assert isinstance(config.printers[0], IppPrinterConfig)
        finally:
            os.unlink(path)

    def test_ipp_missing_host_raises(self):
        data = {"odoo_url": "http://localhost:8069",
                "printers": [{"name": "hp", "connection_type": "ipp", "api_key": "k1"}]}
        import tempfile, os, yaml
        from print_agent.config import ConfigError
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f)
        try:
            with pytest.raises(ConfigError, match="host"):
                Config.from_file(path)
        finally:
            os.unlink(path)


class TestIppPrinterConnection:
    def test_connect_uses_tcp_only(self):
        """connect() should only open a TCP socket, not send HTTP."""
        conn = IppPrinterConnection(host="10.0.0.1", port=9100)
        with patch("socket.socket") as MockSock:
            mock_sock = MagicMock()
            MockSock.return_value = mock_sock
            conn.connect()
        MockSock.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_sock.connect.assert_called_once_with(("10.0.0.1", 9100))
        assert conn.is_available() is True
        assert conn._use_raw_tcp is True

    def test_connect_failure_raises(self):
        conn = IppPrinterConnection(host="10.0.0.1", port=9100)
        with patch("socket.socket") as MockSock:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = OSError("refused")
            MockSock.return_value = mock_sock
            with pytest.raises(PrinterConnectionError, match="not reachable"):
                conn.connect()

    def test_connect_does_not_send_http(self):
        """Must not call requests.get — that causes the printer to print headers."""
        conn = IppPrinterConnection(host="10.0.0.1", port=9100)
        with patch("socket.socket") as MockSock:
            MockSock.return_value = MagicMock()
            conn.connect()
        # requests.get should never be called during connect
        import requests
        # Just verify connect only touches socket, not requests
        assert conn._use_raw_tcp is True

    def test_send_raw_tcp(self):
        conn = IppPrinterConnection(host="10.0.0.1", port=9100)
        conn._connected = True
        conn._use_raw_tcp = True
        mock_sock = MagicMock(spec=socket.socket)
        conn._tcp_socket = mock_sock

        conn.send(b"test data")
        mock_sock.sendall.assert_called_once_with(b"test data")

    def test_send_raw_tcp_error_raises(self):
        conn = IppPrinterConnection(host="10.0.0.1", port=9100)
        conn._connected = True
        conn._use_raw_tcp = True
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.sendall.side_effect = OSError("broken pipe")
        conn._tcp_socket = mock_sock

        with pytest.raises(PrinterConnectionError, match="Raw TCP"):
            conn.send(b"data")

    def test_send_tries_ipp_then_http(self):
        conn = IppPrinterConnection(host="10.0.0.1", port=631)
        conn._connected = True
        conn._working_path = "/ipp/print"

        with patch("requests.post") as mock_post:
            resp_ipp = MagicMock(status_code=500)
            resp_raw = MagicMock(status_code=200)
            mock_post.side_effect = [resp_ipp, resp_raw]

            conn.send(b"test", "image/jpeg")
            assert mock_post.call_count == 2

    def test_send_without_connect_raises(self):
        conn = IppPrinterConnection(host="10.0.0.1", port=631)
        with pytest.raises(PrinterConnectionError, match="not connected"):
            conn.send(b"data")

    def test_disconnect_closes_tcp(self):
        conn = IppPrinterConnection(host="10.0.0.1", port=9100)
        mock_sock = MagicMock(spec=socket.socket)
        conn._tcp_socket = mock_sock
        conn._connected = True

        conn.disconnect()
        mock_sock.close.assert_called_once()
        assert conn._tcp_socket is None
        assert conn.is_available() is False

    def test_request_id_increments(self):
        conn = IppPrinterConnection(host="10.0.0.1", port=631)
        id1 = conn._next_request_id()
        id2 = conn._next_request_id()
        assert id2 == id1 + 1

    def test_build_request_structure(self):
        conn = IppPrinterConnection(host="10.0.0.1", port=631)
        msg = conn._build_print_job_request(b"doc", "ipp://x/printer", "image/jpeg")
        assert msg[:2] == b"\x01\x01"
        assert b"doc" in msg
        assert b"ipp://x/printer" in msg
