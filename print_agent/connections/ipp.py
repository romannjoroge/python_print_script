"""IPP printer connection for HP/standard printers.

Supports IPP over HTTP, raw HTTP POST, and raw TCP as fallbacks.
"""

from __future__ import annotations

import io
import socket
import struct

import requests

from print_agent.connections.base import PrinterConnection, PrinterConnectionError


class IppPrinterConnection(PrinterConnection):
    """Connection for HP inkjet/laser and other standard printers.

    Tries IPP protocol → raw HTTP → raw TCP in sequence.
    """

    _IPP_PRINT_JOB = 0x02
    _TAG_OPERATION = 0x01
    _TAG_END = 0x03
    _TAG_KEYWORD = 0x44
    _TAG_MIMETYPE = 0x49
    _TAG_URI = 0x45
    _TAG_CHARSET = 0x47
    _TAG_NATURAL_LANG = 0x48

    _IPP_PATHS = ["/ipp/print", "/printers", "/"]

    def __init__(self, host: str, port: int = 631, printer_uri: str = "",
                 timeout: float = 30.0) -> None:
        self._host = host
        self._port = port
        self._printer_uri = printer_uri
        self._timeout = timeout
        self._connected = False
        self._request_id = 0
        self._working_path: str | None = None
        self._use_raw_tcp = False
        self._tcp_socket: socket.socket | None = None

    def connect(self) -> None:
        """Try HTTP first, then raw TCP."""
        # Try HTTP endpoints
        for path in self._IPP_PATHS:
            try:
                resp = requests.get(f"http://{self._host}:{self._port}{path}", timeout=5)
                self._connected = True
                self._working_path = path
                return
            except Exception:
                continue

        # Try raw TCP (port 9100 or configured port)
        try:
            self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp_socket.settimeout(5)
            self._tcp_socket.connect((self._host, self._port))
            self._connected = True
            self._use_raw_tcp = True
            return
        except Exception:
            self._tcp_socket = None

        raise PrinterConnectionError(
            f"Printer at {self._host}:{self._port} not reachable via HTTP or TCP"
        )

    def send(self, data: bytes, content_type: str = "application/octet-stream") -> None:
        if not self._connected:
            raise PrinterConnectionError("Printer not connected")

        if self._use_raw_tcp:
            self._send_raw_tcp(data)
            return

        # Try IPP protocol
        try:
            self._send_ipp(data, content_type)
            return
        except PrinterConnectionError:
            pass

        # Fallback: raw HTTP POST
        self._send_raw_http(data, content_type)

    def _send_raw_tcp(self, data: bytes) -> None:
        """Send raw bytes directly over TCP socket."""
        if self._tcp_socket is None:
            raise PrinterConnectionError("Raw TCP socket not connected")
        try:
            self._tcp_socket.sendall(data)
        except Exception as e:
            raise PrinterConnectionError(f"Raw TCP send failed: {e}") from e

    def _send_ipp(self, data: bytes, content_type: str) -> None:
        path = self._working_path or "/ipp/print"
        uri = self._printer_uri or f"ipp://{self._host}:{self._port}/printers/printer"
        ipp_msg = self._build_print_job_request(data, uri, content_type)

        resp = requests.post(
            f"http://{self._host}:{self._port}{path}",
            data=ipp_msg,
            headers={"Content-Type": "application/ipp", "Accept": "application/ipp"},
            timeout=self._timeout,
        )
        if resp.status_code >= 400:
            raise PrinterConnectionError(f"IPP rejected: HTTP {resp.status_code}")
        if len(resp.content) >= 4:
            status = struct.unpack(">H", resp.content[2:4])[0]
            if status >= 0x400:
                raise PrinterConnectionError(f"IPP error: 0x{status:04x}")

    def _send_raw_http(self, data: bytes, content_type: str) -> None:
        path = self._working_path or "/"
        try:
            resp = requests.post(
                f"http://{self._host}:{self._port}{path}",
                data=data,
                headers={"Content-Type": content_type},
                timeout=self._timeout,
            )
            if resp.status_code >= 400:
                raise PrinterConnectionError(f"Print rejected: HTTP {resp.status_code}")
        except PrinterConnectionError:
            raise
        except requests.ConnectionError as e:
            raise PrinterConnectionError(f"Connection failed: {e}") from e
        except requests.Timeout as e:
            raise PrinterConnectionError(f"Print timed out: {e}") from e
        except Exception as e:
            raise PrinterConnectionError(f"Print failed: {e}") from e

    def disconnect(self) -> None:
        self._connected = False
        if self._tcp_socket:
            try:
                self._tcp_socket.close()
            except Exception:
                pass
            self._tcp_socket = None

    def is_available(self) -> bool:
        return self._connected

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _build_print_job_request(self, document: bytes, printer_uri: str,
                                  content_type: str) -> bytes:
        buf = io.BytesIO()
        buf.write(b"\x01\x01")  # IPP 1.1
        buf.write(struct.pack(">H", self._IPP_PRINT_JOB))
        buf.write(struct.pack(">I", self._next_request_id()))
        buf.write(bytes([self._TAG_OPERATION]))
        self._write_attr(buf, "attributes-charset", self._TAG_KEYWORD, b"utf-8")
        self._write_attr(buf, "attributes-natural-language", self._TAG_KEYWORD, b"en")
        self._write_attr(buf, "printer-uri", self._TAG_URI, printer_uri.encode())
        self._write_attr(buf, "document-format", self._TAG_MIMETYPE, content_type.encode())
        buf.write(bytes([self._TAG_END]))
        buf.write(document)
        return buf.getvalue()

    def _write_attr(self, buf: io.BytesIO, name: str, value_tag: int, value: bytes) -> None:
        name_bytes = name.encode()
        buf.write(struct.pack(">H", len(name_bytes)))
        buf.write(name_bytes)
        buf.write(bytes([value_tag]))
        buf.write(struct.pack(">H", len(value)))
        buf.write(value)
