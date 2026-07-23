"""Network (TCP/IP) printer connection implementation."""

from __future__ import annotations

import ipaddress
import socket

from print_agent.connections.base import PrinterConnection, PrinterConnectionError


def _is_ipv6(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).version == 6
    except ValueError:
        return False


class NetworkPrinterConnection(PrinterConnection):
    """Raw TCP socket connection for port 9100 printing."""

    def __init__(self, host: str, port: int = 9100) -> None:
        self._host = host
        self._port = port
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        try:
            af = socket.AF_INET6 if _is_ipv6(self._host) else socket.AF_INET
            self._socket = socket.socket(af, socket.SOCK_STREAM)
            self._socket.connect((self._host, self._port))
        except Exception as e:
            self._socket = None
            raise PrinterConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {e}"
            ) from e

    def send(self, data: bytes) -> None:
        if self._socket is None:
            raise PrinterConnectionError("Network printer not connected")
        try:
            self._socket.sendall(data)
        except Exception as e:
            raise PrinterConnectionError(f"Network write failed: {e}") from e

    def disconnect(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def is_available(self) -> bool:
        return self._socket is not None
