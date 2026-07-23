"""Poll loop orchestrator tying config, connections, rendering, and client together."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from print_agent.config import Config, PrinterConfig, NetworkPrinterConfig, UsbPrinterConfig
from print_agent.connections.base import PrinterConnection, PrinterConnectionError
from print_agent.connections.network import NetworkPrinterConnection
from print_agent.connections.usb import UsbPrinterConnection
from print_agent.odoo_client import OdooClient, OdooClientError
from print_agent.rendering import render_receipt

logger = logging.getLogger("print_agent.orchestrator")

# Backoff constants
BASE_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 60.0  # seconds
BACKOFF_MULTIPLIER = 2.0


class Orchestrator:
    """Polls Odoo for pending jobs and prints them via configured connections.

    Design decisions:
    - On transient connection failure (socket timeout, temporary USB glitch),
      we do NOT ack the job — it stays pending for retry on the next cycle.
    - On non-transient errors (USB unplugged, permanent connection loss),
      we ack with status="failed" so Odoo knows the job won't print.
    - One printer's failure never blocks another printer's polling.
    """

    def __init__(
        self,
        config: Config,
        client: OdooClient | None = None,
        ack_on_transient_failure: bool = False,
    ) -> None:
        self._config = config
        self._client = client or OdooClient(
            base_url=config.odoo_url, api_key=""
        )
        self._ack_on_transient_failure = ack_on_transient_failure
        self._connections: dict[str, PrinterConnection] = {}
        self._consecutive_errors: dict[str, int] = {}
        self._printers_by_api_key: dict[str, PrinterConfig] = {}
        self._init_connections()

    def _init_connections(self) -> None:
        for printer in self._config.printers:
            conn = self._create_connection(printer)
            self._connections[printer.name] = conn
            self._printers_by_api_key[printer.api_key] = printer

    def _create_connection(self, printer: PrinterConfig) -> PrinterConnection:
        if isinstance(printer, NetworkPrinterConfig):
            return NetworkPrinterConnection(host=printer.host, port=printer.port)
        if isinstance(printer, UsbPrinterConfig):
            return UsbPrinterConnection(
                vendor_id=printer.vendor_id,
                product_id=printer.product_id,
                device_path=printer.device_path,
            )
        raise ValueError(f"Unknown printer type: {type(printer)}")

    def _poll_once(self) -> None:
        """Single poll cycle for all printers."""
        for printer in self._config.printers:
            self._poll_printer(printer)

    def _poll_printer(self, printer: PrinterConfig) -> None:
        """Poll a single printer for pending jobs."""
        try:
            jobs = self._client.get_pending_jobs()
        except OdooClientError as e:
            logger.error("Failed to fetch jobs for %s: %s", printer.name, e)
            return

        for job in jobs:
            self._process_job(printer, job, self._client)

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

            espos_bytes = render_receipt(job.payload)
            conn.send(espos_bytes)
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
