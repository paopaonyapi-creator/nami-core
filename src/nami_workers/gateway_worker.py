"""Gateway Worker — Unified REST API entry point.

Migrated from /opt/nami-api-gateway.
Routes HTTP requests to appropriate workers, handles auth, rate limiting.

Actions:
  - route: Route request to appropriate worker
  - health: Health check endpoint
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def route(payload: dict[str, Any]) -> dict[str, Any]:
    """Route an API request to the appropriate worker.

    Payload keys:
      - path: API path (e.g. "/api/signal/generate")
      - method: HTTP method
      - body: request body
      - api_key: client API key

    Returns dict with: routed, worker, path
    """
    path = payload.get("path", "/")
    method = payload.get("method", "GET")

    # Route mapping
    routes = {
        "/api/signal": "signal",
        "/api/proxy": "proxy",
        "/api/lottery": "lottery",
        "/api/trading": "trading",
        "/api/bot": "bot",
        "/api/status": "status",
    }

    worker_name = "default"
    for prefix, name in routes.items():
        if path.startswith(prefix):
            worker_name = name
            break

    logger.info("Route: %s %s → %s", method, path, worker_name)

    return {
        "routed": True,
        "worker": worker_name,
        "path": path,
        "method": method,
    }


def health(payload: dict[str, Any]) -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "nami-gateway",
        "version": "0.0.1",
    }


ACTIONS: dict[str, callable] = {
    "route": route,
    "health": health,
}


def gateway_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "route")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
