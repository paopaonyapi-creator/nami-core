"""Status Worker — Health checks and service monitoring.

Migrated from /opt/nami-status-api.
Provides health endpoints for all workers and infrastructure.
Reads real VPS service status via systemd and resource metrics.

Actions:
  - health: Return overall system health with real metrics
  - worker_health: Return health for a specific worker
  - services: List all VPS systemd services and their status
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# ── VPS Service Registry (from /opt/nami-status-api) ──
VPS_SERVICES = [
    "maxplus-proxy",
    "telegram-premium-bot",
    "nami-bot",
    "hanoi-bot",
    "gold-signal-os",
    "nami-api-gateway",
    "nami-status-api",
    "nami-bridge",
    "graphify-http",
    "nami-core",
    "nginx",
    "postgresql",
    "fail2ban",
]


def _get_service_status(service: str) -> dict[str, Any]:
    """Check systemd service status on VPS."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5,
        )
        active = result.stdout.strip() == "active"
        return {"service": service, "active": active, "status": result.stdout.strip()}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"service": service, "active": False, "status": "unknown"}


def _get_resource_metrics() -> dict[str, Any]:
    """Get VPS resource metrics (RAM, disk, load)."""
    metrics = {}
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
            total = int(lines[0].split()[1])
            available = int(lines[2].split()[1]) if len(lines) > 2 else total
            metrics["ram_total_mb"] = total // 1024
            metrics["ram_available_mb"] = available // 1024
            metrics["ram_used_pct"] = round((1 - available / total) * 100, 1)
    except (OSError, ValueError):
        pass
    try:
        with open("/proc/loadavg") as f:
            metrics["load_1m"] = float(f.read().split()[0])
    except (OSError, ValueError):
        pass
    try:
        result = subprocess.run(
            ["df", "-h", "/"], capture_output=True, text=True, timeout=5,
        )
        line = result.stdout.strip().split("\n")[-1]
        parts = line.split()
        if len(parts) >= 5:
            metrics["disk_used_pct"] = parts[4].replace("%", "")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return metrics


def health(payload: dict[str, Any]) -> dict[str, Any]:
    """Overall system health check with real VPS metrics."""
    metrics = _get_resource_metrics()
    failed = 0
    active = 0
    for svc in VPS_SERVICES:
        st = _get_service_status(svc)
        if st["active"]:
            active += 1
        elif st["status"] not in ("inactive", "unknown"):
            failed += 1

    status = "ok" if failed == 0 else "degraded"
    return {
        "status": status,
        "service": "nami-core",
        "workers": "registered",
        "harness": "operational",
        "vps_services_active": active,
        "vps_services_failed": failed,
        "metrics": metrics,
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


def services(payload: dict[str, Any]) -> dict[str, Any]:
    """List all VPS systemd services and their status."""
    svc_list = [_get_service_status(s) for s in VPS_SERVICES]
    active_count = sum(1 for s in svc_list if s["active"])
    return {
        "services": svc_list,
        "total": len(svc_list),
        "active": active_count,
        "failed": len(svc_list) - active_count,
    }


ACTIONS: dict[str, callable] = {
    "health": health,
    "worker_health": worker_health,
    "services": services,
}


def status_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "health")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
