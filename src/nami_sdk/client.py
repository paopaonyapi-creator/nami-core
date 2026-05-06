"""Nami Core Python SDK — client library for the Nami API."""

from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class NamiClient:
    """Synchronous client for the nami-core API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8092", api_key: str = "", timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            h.update(extra)
        return h

    def _get(self, path: str) -> dict[str, Any]:
        req = Request(f"{self.base_url}{path}", headers=self._headers())
        with urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(data).encode("utf-8")
        req = Request(f"{self.base_url}{path}", data=body, headers=self._headers(), method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                return {"error": err_json.get("detail", err_json), "status": e.code}
            except json.JSONDecodeError:
                return {"error": err_body, "status": e.code}

    def health(self) -> dict[str, Any]:
        """Check nami-core health."""
        return self._get("/health")

    def workers(self) -> list[dict[str, Any]]:
        """List registered workers and their actions."""
        return self._get("/workers").get("workers", [])

    def scheduler(self) -> dict[str, Any]:
        """Get scheduler status."""
        return self._get("/scheduler")

    def metrics(self) -> dict[str, Any]:
        """Get JSON metrics snapshot."""
        return self._get("/metrics")

    def prometheus_metrics(self) -> str:
        """Get Prometheus text format metrics."""
        req = Request(f"{self.base_url}/metrics/prometheus", headers=self._headers())
        with urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8")

    def dispatch(self, worker: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch a worker action."""
        return self._post("/dispatch", {
            "worker": worker,
            "action": action,
            "payload": payload or {},
        })

    def webhook(self, source: str, event: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a webhook event."""
        return self._post("/webhook", {
            "source": source,
            "event": event,
            "data": data or {},
        })

    def audit(self, limit: int = 50) -> dict[str, Any]:
        """Get recent audit log entries."""
        return self._get(f"/audit?limit={limit}")

    def rotate_key(self, new_key: str) -> dict[str, Any]:
        """Rotate the API key. Requires current key auth."""
        return self._post("/rotate-key", {"new_key": new_key})

    def scheduler_run_now(self, job: str) -> dict[str, Any]:
        """Force-run a scheduled job by key (e.g. 'status:health')."""
        return self.dispatch("scheduler", "run_now", {"job": job})

    def cron_schedule(self, worker: str, action: str, run_at: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Schedule a one-off cron job. run_at is ISO format datetime."""
        return self.dispatch("cron", "schedule", {
            "worker": worker,
            "cron_action": action,
            "run_at": run_at,
            "job_payload": payload or {},
        })

    def cron_list(self, status: str = "pending") -> dict[str, Any]:
        """List cron jobs by status."""
        return self.dispatch("cron", "list", {"status": status})

    def cron_cancel(self, job_id: int) -> dict[str, Any]:
        """Cancel a pending cron job."""
        return self.dispatch("cron", "cancel", {"job_id": job_id})
