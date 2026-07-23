"""Thin HTTP client for the Odoo receipt_printer module routes."""

from __future__ import annotations

from dataclasses import dataclass

import requests


class OdooClientError(Exception):
    """Base error for Odoo client failures."""


class OdooConnectionError(OdooClientError):
    """Raised when Odoo is unreachable."""


class OdooResponseError(OdooClientError):
    """Raised when Odoo returns an unexpected response."""


@dataclass(frozen=True)
class Job:
    """A pending print job from Odoo."""

    id: int
    payload: dict


class OdooClient:
    """Client for the receipt_printer HTTP routes."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._api_key}

    def get_pending_jobs(self) -> list[Job]:
        """Fetch pending jobs for this printer."""
        url = f"{self._base_url}/receipt_printer/pending_jobs"
        try:
            resp = requests.get(
                url, headers=self._headers(), timeout=self._timeout
            )
        except TimeoutError as e:
            raise OdooClientError(f"Timeout fetching jobs: {e}") from e
        except requests.ConnectionError as e:
            raise OdooClientError(f"Connection error: {e}") from e

        self._check_status(resp, "GET", url)

        try:
            data = resp.json()
        except ValueError as e:
            raise OdooClientError(
                f"Malformed JSON response from {url}: {e}"
            ) from e

        if not isinstance(data, dict):
            raise OdooClientError(
                f"Unexpected response shape from {url}: expected object"
            )

        raw_jobs = data.get("jobs", [])
        if not isinstance(raw_jobs, list):
            raise OdooClientError(f"'jobs' is not a list in response from {url}")

        return [Job(id=j["id"], payload=j["payload"]) for j in raw_jobs]

    def ack_job(
        self,
        job_id: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Acknowledge a job's completion or failure."""
        url = f"{self._base_url}/receipt_printer/ack"
        body: dict = {"job_id": job_id, "status": status}
        if error_message is not None:
            body["error_message"] = error_message

        try:
            resp = requests.post(
                url, json=body, headers=self._headers(), timeout=self._timeout
            )
        except TimeoutError as e:
            raise OdooClientError(f"Timeout acking job {job_id}: {e}") from e
        except requests.ConnectionError as e:
            raise OdooClientError(
                f"Connection error acking job {job_id}: {e}"
            ) from e

        self._check_status(resp, "POST", url)

    def _check_status(self, resp: requests.Response, method: str, url: str) -> None:
        if resp.status_code == 401:
            raise OdooClientError(
                f"Authentication failed for {method} {url} (401 Unauthorized)"
            )
        if resp.status_code >= 400:
            raise OdooClientError(
                f"HTTP {resp.status_code} from {method} {url}"
            )
