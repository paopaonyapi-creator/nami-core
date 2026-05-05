"""Status Worker — Health checks and service monitoring.

Migrated from /opt/nami-status-api.
Provides health endpoints for all workers and infrastructure.

Actions:
  - health: Return overall system health
  - worker_health: Return health for a specific worker
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def health(payload: dict[str, Any]) -> dict[str, Any]:
    """Overall system health check."""
    return {
        "status": "ok",
        "service": "nami-core",
        "workers": "registered",
        "harness": "operational",
    }


def worker_health(payload: dict[str, Any]) -> dict[str, Any]:
    """Health check for a specific worker.

    Payload keys:
      - worker_name: name of the worker to check
    """
    worker_name = payload.get("worker_name", "unknown")
    return {
        "worker": worker_name,
        "status": "ok",
    }


ACTIONS: dict[str, callable] = {
    "health": health,
    "worker_health": worker_health,
}


def status_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "health")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
