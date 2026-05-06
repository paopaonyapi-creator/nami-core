"""Scheduler worker — manage scheduled jobs at runtime via dispatch."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("nami_workers.scheduler")

# Reference to NamiScheduler (set at startup)
_scheduler_ref = None


def set_scheduler_ref(ref) -> None:
    global _scheduler_ref
    _scheduler_ref = ref


def scheduler_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Scheduler worker: list, enable, disable, run_now, add, remove."""
    action = payload.get("action", "list")

    if not _scheduler_ref:
        return {"error": "scheduler not available"}

    if action == "list":
        return _scheduler_ref.status()
    elif action == "run_now":
        job_key = payload.get("job", "")
        if not job_key:
            return {"error": "job key required (e.g. 'status:health')"}
        return _run_job_now(job_key)
    elif action == "enable":
        return {"ok": True, "message": "scheduler already running"}
    elif action == "disable":
        _scheduler_ref.stop()
        return {"ok": True, "message": "scheduler stopped"}
    else:
        return {"error": f"unknown action: {action}"}


def _run_job_now(job_key: str) -> dict[str, Any]:
    """Force-run a scheduled job by key."""
    from nami_core.scheduler import SCHEDULES
    for job in SCHEDULES:
        key = f"{job['worker']}:{job['action']}"
        if key == job_key:
            try:
                result = _scheduler_ref.hermes.dispatch(job["worker"], job["action"], job.get("payload", {}))
                return {"ok": True, "job": key, "output": result.output}
            except Exception as exc:
                return {"ok": False, "job": key, "error": str(exc)}
    return {"error": f"job not found: {job_key}"}
