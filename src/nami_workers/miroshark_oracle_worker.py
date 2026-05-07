"""Miroshark Oracle Worker — wraps miroshark-oracle FastAPI service.

AI-powered gold market intelligence API on 127.0.0.1:8003.
Available oracle endpoints (proxied):
  - /health
  - /oracle/analyze
  - /oracle/ai_analyze
  - /oracle/ai_health
  - /oracle/ai_test
  - /oracle/usage

Actions:
  - status:       systemctl + /health probe
  - analyze:      POST /oracle/analyze with payload data
  - ai_analyze:   POST /oracle/ai_analyze with payload data
  - ai_health:    GET /oracle/ai_health
  - ai_test:      GET /oracle/ai_test
  - usage:        GET /oracle/usage
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

PORT = 8003
SERVICE = "miroshark-oracle"
BASE = f"http://127.0.0.1:{PORT}"


def _http_get(path: str, timeout: float = 5.0) -> dict[str, Any]:
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"raw": body[:1024]}
            return {"ok": resp.status < 400, "status_code": resp.status, "data": data}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": str(exc)[:200]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status_code": 0, "error": f"unreachable: {exc}"}


def _http_post(path: str, body: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = {"raw": text[:1024]}
            return {"ok": resp.status < 400, "status_code": resp.status, "data": parsed}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": str(exc)[:200]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status_code": 0, "error": f"unreachable: {exc}"}


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
    probe = _http_get("/health", timeout=3.0)
    return {
        "service": SERVICE,
        "port": PORT,
        "systemd": sysd,
        "http_ok": probe["ok"],
        "http_status": probe["status_code"],
        "healthy": sysd == "active" and probe["ok"],
        "endpoints": ["/health", "/oracle/analyze", "/oracle/ai_analyze", "/oracle/ai_health", "/oracle/ai_test", "/oracle/usage"],
    }


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("body") or payload.get("data") or {}
    return _http_post("/oracle/analyze", body)


def ai_analyze(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("body") or payload.get("data") or {}
    return _http_post("/oracle/ai_analyze", body)


def ai_health(payload: dict[str, Any]) -> dict[str, Any]:
    return _http_get("/oracle/ai_health")


def ai_test(payload: dict[str, Any]) -> dict[str, Any]:
    return _http_get("/oracle/ai_test")


def usage(payload: dict[str, Any]) -> dict[str, Any]:
    return _http_get("/oracle/usage")


ACTIONS: dict[str, callable] = {
    "status": status,
    "analyze": analyze,
    "ai_analyze": ai_analyze,
    "ai_health": ai_health,
    "ai_test": ai_test,
    "usage": usage,
}


def miroshark_oracle_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "status")
    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}
    return handler(payload)
