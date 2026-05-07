"""Hanoi Stats Worker — wraps hanoi-stats-analyzer systemd service.

Hanoi lottery stats analyzer — Next.js app on port 3002

Actions:
  - status: HTTP health probe + systemctl is-active
  - ping:   lightweight HTTP probe only
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

PORT = 3002
SERVICE = "hanoi-stats-analyzer"
HEALTH_PATH = "/api/health"


def _http_probe(path: str, timeout: float = 3.0) -> dict[str, Any]:
    url = f"http://127.0.0.1:{PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(2048).decode("utf-8", errors="replace")
            return {"ok": resp.status < 400, "status_code": resp.status, "body": body[:1024]}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "body": str(exc)[:200]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status_code": 0, "body": f"unreachable: {exc}"}


def _systemctl_is_active() -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def status(payload: dict[str, Any]) -> dict[str, Any]:
    sysd = _systemctl_is_active()
    probe = _http_probe(HEALTH_PATH)
    healthy = sysd == "active" and probe["ok"]
    return {
        "service": SERVICE,
        "port": PORT,
        "systemd": sysd,
        "http_status": probe["status_code"],
        "http_ok": probe["ok"],
        "healthy": healthy,
        "probe_path": HEALTH_PATH,
    }


def ping(payload: dict[str, Any]) -> dict[str, Any]:
    probe = _http_probe(HEALTH_PATH)
    return {
        "service": SERVICE,
        "port": PORT,
        "ok": probe["ok"],
        "status_code": probe["status_code"],
    }


ACTIONS: dict[str, callable] = {
    "status": status,
    "ping": ping,
}


def hanoi_stats_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "status")
    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}
    return handler(payload)
