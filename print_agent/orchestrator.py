"""Poll loop orchestrator tying config, connections, rendering, and client together."""

from __future__ import annotations

import base64
import logging
import time
from typing import Protocol

from print_agent.config import (
    Config,
    PrinterConfig,
    NetworkPrinterConfig,
    UsbPrinterConfig,
    IppPrinterConfig,
)
from print_agent.connections.base import PrinterConnection, PrinterConnectionError
from print_agent.connections.network import NetworkPrinterConnection
from print_agent.connections.usb import UsbPrinterConnection
from print_agent.connections.ipp import IppPrinterConnection
from print_agent.odoo_client import OdooClient, OdooClientError
from print_agent.rendering import render_receipt

logger = logging.getLogger("print_agent.orchestrator")

# Backoff constants
BASE_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 60.0  # seconds
BACKOFF_MULTIPLIER = 2.0


def _prepare_ipp_data(payload) -> tuple[bytes, str]:
    """Prepare print data for IPP printers.

    Returns (data, content_type) tuple.
    IPP printers accept raw image/document data. The Odoo payload is
    a base64-encoded image, so we decode it and return raw bytes.
    """
    if isinstance(payload, str):
        try:
            data = base64.b64decode(payload)
            # Detect image type from magic bytes
            content_type = _detect_content_type(data)
            return data, content_type
        except Exception:
            raise ValueError(f"Invalid base64 payload for IPP printer")
    elif isinstance(payload, dict):
        content = payload.get("content", "")
        if isinstance(content, str) and len(content) > 100:
            # Likely base64 data in content field
            try:
                data = base64.b64decode(content)
                content_type = _detect_content_type(data)
                return data, content_type
            except Exception:
                pass
        # Fall back to rendering as ESC/POS
        from print_agent.rendering import render_receipt
        return render_receipt(payload), "application/octet-stream"
    else:
        from print_agent.rendering import render_receipt
        return render_receipt(payload), "application/octet-stream"


def _detect_content_type(data: bytes) -> str:
    """Detect MIME type from file magic bytes."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    return "application/octet-stream"


class Orchestrator:
    """Polls Odoo for pending jobs and prints them via configured connections.

    Design decisions:
    - On transient connection failure (socket timeout, temporary USB glitch),
      we do NOT ack the job — it stays pending for retry on the next cycle.
    - On non-transient errors (USB unplugged, permanent connection loss),
      we ack with status="failed" so Odoo knows the job won't print.
    - One printer's failure never blocks another printer's polling.
    - A configurable delay between jobs prevents overwhelming the printer.
    """

    def __init__(
        self,
        config: Config,
        client: OdooClient | None = None,
        ack_on_transient_failure: bool = False,
        job_delay: float = 2.0,
    ) -> None:
        self._config = config
        self._injected_client = client
        self._ack_on_transient_failure = ack_on_transient_failure
        self._job_delay = job_delay
        self._connections: dict[str, PrinterConnection] = {}
        self._clients: dict[str, OdooClient] = {}
        self._consecutive_errors: dict[str, int] = {}
        self._init_connections()

    def _init_connections(self) -> None:
        for printer in self._config.printers:
            conn = self._create_connection(printer)
            self._connections[printer.name] = conn
            if self._injected_client:
                self._clients[printer.name] = self._injected_client
            else:
                self._clients[printer.name] = OdooClient(
                    base_url=self._config.odoo_url,
                    api_key=printer.api_key,
                )

    def _create_connection(self, printer: PrinterConfig) -> PrinterConnection:
        if isinstance(printer, NetworkPrinterConfig):
            return NetworkPrinterConnection(host=printer.host, port=printer.port)
        if isinstance(printer, UsbPrinterConfig):
            return UsbPrinterConnection(
                vendor_id=printer.vendor_id,
                product_id=printer.product_id,
                device_path=printer.device_path,
            )
        if isinstance(printer, IppPrinterConfig):
            return IppPrinterConnection(
                host=printer.host,
                port=printer.port,
                printer_uri=printer.printer_uri,
            )
        raise ValueError(f"Unknown printer type: {type(printer)}")

    def _poll_once(self) -> None:
        """Single poll cycle for all printers."""
        for printer in self._config.printers:
            self._poll_printer(printer)

    def _poll_printer(self, printer: PrinterConfig) -> None:
        """Poll a single printer for pending jobs."""
        client = self._clients[printer.name]
        try:
            jobs = client.get_pending_jobs()
        except OdooClientError as e:
            logger.error("Failed to fetch jobs for %s: %s", printer.name, e)
            return

        for job in jobs:
            self._process_job(printer, job, client)

    def _process_job(self, printer, job, client: OdooClient) -> None:
        conn = self._connections[printer.name]
        try:
            if not conn.is_available():
                try:
                    conn.connect()
                except PrinterConnectionError as e:
                    logger.warning(
                        "Cannot connect to %s: %s", printer.name, e
                    )
                    client.ack_job(
                        job_id=job.id,
                        status="failed",
                        error_message=str(e),
                    )
                    return

            # IPP printers get raw image data; ESC/POS printers get rendered bytes
            if isinstance(printer, IppPrinterConfig):
                print_data, content_type = _prepare_ipp_data(job.payload)
                conn.send(print_data, content_type=content_type)
            else:
                print_data = render_receipt(job.payload)
                conn.send(print_data)

            # Wait for printer to finish before ACKing and moving to next job
            if self._job_delay > 0:
                time.sleep(self._job_delay)

            client.ack_job(job_id=job.id, status="printed")
            self._consecutive_errors[printer.name] = 0
            logger.info(
                "Printed job %d on %s", job.id, printer.name
            )

        except PrinterConnectionError as e:
            self._consecutive_errors[printer.name] = (
                self._consecutive_errors.get(printer.name, 0) + 1
            )
            logger.error(
                "Print job %d failed on %s: %s",
                job.id,
                printer.name,
                e,
            )
            client.ack_job(
                job_id=job.id,
                status="failed",
                error_message=str(e),
            )

    def run(self, max_cycles: int | None = None) -> None:
        """Run the poll loop.

        Args:
            max_cycles: If set, run this many cycles then stop (for testing).
                        If None, run forever.
        """
        cycle = 0
        while max_cycles is None or cycle < max_cycles:
            self._poll_once()
            cycle += 1
            if max_cycles is None:
                # In production, sleep between cycles
                backoff = self._calculate_backoff()
                time.sleep(backoff)

    def _calculate_backoff(self) -> float:
        """Calculate sleep time based on consecutive errors across all printers."""
        max_errors = max(self._consecutive_errors.values()) if self._consecutive_errors else 0
        if max_errors == 0:
            return BASE_BACKOFF
        backoff = min(
            BASE_BACKOFF * (BACKOFF_MULTIPLIER ** max_errors),
            MAX_BACKOFF,
        )
        return backoff
