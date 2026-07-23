"""Tests for orchestrator / poll loop logic."""

from unittest.mock import MagicMock, call, patch

import pytest

from print_agent.config import Config, NetworkPrinterConfig
from print_agent.connections.base import PrinterConnectionError
from print_agent.odoo_client import Job, OdooClient, OdooClientError
from print_agent.orchestrator import Orchestrator


def _make_printer_config(name="p1", api_key="k1"):
    return NetworkPrinterConfig(name=name, api_key=api_key, host="10.0.0.1", port=9100)


def _make_config(printers=None):
    if printers is None:
        printers = [_make_printer_config()]
    return Config(odoo_url="http://odoo:8069", printers=printers)


class TestOrchestratorSinglePrinter:
    def test_successful_job_is_printed_and_acked(self):
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_conn.is_available.return_value = True

        mock_client.get_pending_jobs.return_value = [
            Job(id=1, payload={"type": "text", "content": "hello"}),
        ]

        orch = Orchestrator(config, client=mock_client)
        orch._connections = {"p1": mock_conn}

        orch._poll_once()

        mock_conn.send.assert_called_once()
        sent_bytes = mock_conn.send.call_args[0][0]
        assert b"hello" in sent_bytes

        mock_client.ack_job.assert_called_once_with(
            job_id=1, status="printed"
        )

    def test_multiple_jobs_all_processed(self):
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_conn.is_available.return_value = True

        mock_client.get_pending_jobs.return_value = [
            Job(id=1, payload={"type": "text", "content": "a"}),
            Job(id=2, payload={"type": "text", "content": "b"}),
        ]

        orch = Orchestrator(config, client=mock_client)
        orch._connections = {"p1": mock_conn}

        orch._poll_once()

        assert mock_conn.send.call_count == 2
        assert mock_client.ack_job.call_count == 2

    def test_empty_jobs_does_nothing(self):
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_client.get_pending_jobs.return_value = []

        orch = Orchestrator(config, client=mock_client)
        orch._connections = {"p1": mock_conn}

        orch._poll_once()

        mock_conn.send.assert_not_called()
        mock_client.ack_job.assert_not_called()


class TestOrchestratorConnectionFailure:
    def test_connection_error_acks_with_failed(self):
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_conn.is_available.return_value = True
        mock_conn.send.side_effect = PrinterConnectionError("USB unplugged")

        mock_client.get_pending_jobs.return_value = [
            Job(id=10, payload={"type": "text", "content": "x"}),
        ]

        orch = Orchestrator(config, client=mock_client)
        orch._connections = {"p1": mock_conn}

        orch._poll_once()

        mock_client.ack_job.assert_called_once_with(
            job_id=10,
            status="failed",
            error_message="USB unplugged",
        )

    def test_odoo_fetch_error_does_not_crash(self):
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_client.get_pending_jobs.side_effect = OdooClientError("Odoo down")

        orch = Orchestrator(config, client=mock_client)
        orch._connections = {"p1": mock_conn}

        # Should not raise
        orch._poll_once()

        mock_conn.send.assert_not_called()


class TestOrchestratorMultiPrinter:
    def test_one_printer_failure_does_not_block_others(self):
        p1 = _make_printer_config(name="p1", api_key="k1")
        p2 = _make_printer_config(name="p2", api_key="k2")
        config = _make_config(printers=[p1, p2])

        mock_client = MagicMock(spec=OdooClient)

        # Return different jobs on successive calls (one per printer)
        mock_client.get_pending_jobs.side_effect = [
            [Job(id=1, payload={"type": "text", "content": "fail"})],
            [Job(id=2, payload={"type": "text", "content": "ok"})],
        ]

        mock_conn1 = MagicMock()
        mock_conn1.is_available.return_value = True
        mock_conn1.send.side_effect = PrinterConnectionError("broken")

        mock_conn2 = MagicMock()
        mock_conn2.is_available.return_value = True

        orch = Orchestrator(config, client=mock_client)
        orch._connections = {"p1": mock_conn1, "p2": mock_conn2}

        orch._poll_once()

        # p2's job should still be processed
        mock_conn2.send.assert_called_once()
        # p1 fails (acked with failed), p2 succeeds (acked with printed)
        assert mock_client.ack_job.call_count == 2
        # Verify p1 was acked with failed
        calls = mock_client.ack_job.call_args_list
        assert any(
            call.kwargs.get("status") == "failed" for call in calls
        )


class TestOrchestratorBackoff:
    def test_consecutive_failures_increase_backoff(self):
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_conn.is_available.return_value = True
        mock_conn.send.side_effect = PrinterConnectionError("fail")

        mock_client.get_pending_jobs.return_value = [
            Job(id=1, payload={"type": "text", "content": "x"}),
        ]

        orch = Orchestrator(config, client=mock_client)
        orch._connections = {"p1": mock_conn}

        # Simulate multiple failed cycles
        for _ in range(5):
            orch._poll_once()

        # The connection error count should have increased
        assert orch._consecutive_errors.get("p1", 0) >= 5

    def test_success_resets_backoff(self):
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_conn.is_available.return_value = True

        mock_client.get_pending_jobs.return_value = [
            Job(id=1, payload={"type": "text", "content": "x"}),
        ]

        orch = Orchestrator(config, client=mock_client)
        orch._connections = {"p1": mock_conn}

        # Simulate failures then success
        mock_conn.send.side_effect = PrinterConnectionError("fail")
        orch._poll_once()
        assert orch._consecutive_errors.get("p1", 0) > 0

        mock_conn.send.side_effect = None
        mock_conn.send.reset_mock()
        orch._poll_once()
        assert orch._consecutive_errors.get("p1", 0) == 0


class TestOrchestratorTransientFailure:
    def test_transient_failure_acks_with_failed(self):
        """Connection errors always ack with failed status."""
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_conn.is_available.return_value = True
        mock_conn.send.side_effect = PrinterConnectionError("temporary")

        mock_client.get_pending_jobs.return_value = [
            Job(id=1, payload={"type": "text", "content": "retry me"}),
        ]

        orch = Orchestrator(
            config, client=mock_client, ack_on_transient_failure=False
        )
        orch._connections = {"p1": mock_conn}

        orch._poll_once()

        # Should ack with failed
        mock_client.ack_job.assert_called_once_with(
            job_id=1,
            status="failed",
            error_message="temporary",
        )

    def test_non_transient_failure_acks_failed(self):
        """Non-transient errors ack with failed status."""
        config = _make_config()
        mock_client = MagicMock(spec=OdooClient)
        mock_conn = MagicMock()
        mock_conn.is_available.return_value = True
        mock_conn.send.side_effect = PrinterConnectionError("USB unplugged")

        mock_client.get_pending_jobs.return_value = [
            Job(id=1, payload={"type": "text", "content": "dead"}),
        ]

        orch = Orchestrator(
            config, client=mock_client, ack_on_transient_failure=False
        )
        orch._connections = {"p1": mock_conn}

        orch._poll_once()

        # Should ack with failed for hardware errors
        mock_client.ack_job.assert_called_once_with(
            job_id=1,
            status="failed",
            error_message="USB unplugged",
        )
