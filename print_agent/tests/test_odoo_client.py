"""Tests for Odoo HTTP client."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from print_agent.odoo_client import (
    Job,
    OdooClient,
    OdooClientError,
    OdooConnectionError,
    OdooResponseError,
)


@dataclass
class MockResponse:
    status_code: int
    _json: dict | None = None
    text: str = ""

    def json(self):
        if self._json is None:
            raise ValueError("No JSON")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OdooResponseError(f"HTTP {self.status_code}")


class TestJob:
    def test_job_fields(self):
        job = Job(id=1, payload={"text": "hello"})
        assert job.id == 1
        assert job.payload == {"text": "hello"}


class TestOdooClientPendingJobs:
    def test_successful_fetch(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(
            status_code=200,
            _json={"jobs": [{"id": 10, "payload": {"text": "receipt"}}]},
        )
        with patch("requests.get", return_value=mock_resp) as mock_get:
            jobs = client.get_pending_jobs()

        assert len(jobs) == 1
        assert jobs[0].id == 10
        assert jobs[0].payload == {"text": "receipt"}

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "/receipt_printer/pending_jobs" in call_args[0][0]
        assert call_args[1]["headers"]["X-Api-Key"] == "k1"

    def test_empty_jobs(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=200, _json={"jobs": []})
        with patch("requests.get", return_value=mock_resp):
            jobs = client.get_pending_jobs()
        assert jobs == []

    def test_no_jobs_key_treated_as_empty(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=200, _json={})
        with patch("requests.get", return_value=mock_resp):
            jobs = client.get_pending_jobs()
        assert jobs == []

    def test_401_raises_auth_error(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="bad")
        mock_resp = MockResponse(status_code=401, text="Unauthorized")
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(OdooClientError, match="401|Unauthorized|auth"):
                client.get_pending_jobs()

    def test_404_raises_error(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=404)
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(OdooClientError):
                client.get_pending_jobs()

    def test_500_raises_error(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=500)
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(OdooClientError):
                client.get_pending_jobs()

    def test_timeout_raises_error(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        with patch("requests.get", side_effect=TimeoutError("timeout")):
            with pytest.raises(OdooClientError, match="timeout|Timeout"):
                client.get_pending_jobs()

    def test_connection_error_raises_error(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        import requests as _requests

        with patch(
            "requests.get",
            side_effect=_requests.ConnectionError("refused"),
        ):
            with pytest.raises(OdooClientError, match="refused|connection|Connection"):
                client.get_pending_jobs()

    def test_malformed_json_raises_error(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=200)
        mock_resp.json = MagicMock(side_effect=ValueError("no json"))
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(OdooClientError, match="malformed|invalid|JSON"):
                client.get_pending_jobs()

    def test_unexpected_shape_without_jobs_treated_as_empty(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=200, _json={"unexpected": "shape"})
        with patch("requests.get", return_value=mock_resp):
            jobs = client.get_pending_jobs()
        assert jobs == []

    def test_non_dict_response_raises(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=200, _json="just a string")
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(OdooClientError):
                client.get_pending_jobs()

    def test_jobs_not_a_list_raises(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=200, _json={"jobs": "not a list"})
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(OdooClientError):
                client.get_pending_jobs()

    def test_url_trailing_slash_handled(self):
        client = OdooClient(base_url="http://odoo:8069/", api_key="k1")
        mock_resp = MockResponse(status_code=200, _json={"jobs": []})
        with patch("requests.get", return_value=mock_resp) as mock_get:
            client.get_pending_jobs()
        url = mock_get.call_args[0][0]
        assert "//" not in url.split("://", 1)[1]


class TestOdooClientAck:
    def test_ack_success(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=200, _json={"ok": True})
        with patch("requests.post", return_value=mock_resp) as mock_post:
            client.ack_job(job_id=10, status="printed")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "/receipt_printer/ack" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["job_id"] == 10
        assert body["status"] == "printed"
        assert "error_message" not in body

    def test_ack_failure_with_message(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=200, _json={"ok": True})
        with patch("requests.post", return_value=mock_resp) as mock_post:
            client.ack_job(job_id=5, status="failed", error_message="paper jam")

        body = mock_post.call_args[1]["json"]
        assert body["job_id"] == 5
        assert body["status"] == "failed"
        assert body["error_message"] == "paper jam"

    def test_ack_http_error_raises(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        mock_resp = MockResponse(status_code=404)
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(OdooClientError):
                client.ack_job(job_id=99, status="printed")

    def test_ack_timeout_raises(self):
        client = OdooClient(base_url="http://odoo:8069", api_key="k1")
        with patch("requests.post", side_effect=TimeoutError("timeout")):
            with pytest.raises(OdooClientError, match="timeout|Timeout"):
                client.ack_job(job_id=1, status="printed")
