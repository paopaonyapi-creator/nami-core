"""Cron worker — one-off delayed execution via SQLite."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("nami_workers.cron")

CRON_DB = os.environ.get("NAMI_CRON_DB", "/tmp/nami_cron.db")

# Reference to Hermes (set at startup)
_hermes_ref = None


def set_hermes_ref(ref) -> None:
    global _hermes_ref
    _hermes_ref = ref


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(CRON_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker TEXT NOT NULL,
            action TEXT NOT NULL,
            payload TEXT NOT NULL,
            run_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            result TEXT
        )
    """)
    conn.commit()
    return conn


def cron_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Cron worker: schedule, cancel, list."""
    action = payload.get("action", "list")

    if action == "schedule":
        return _schedule(payload)
    elif action == "cancel":
        return _cancel(payload)
    elif action == "list":
        return _list(payload)
    else:
        return {"error": f"unknown action: {action}"}


def _schedule(payload: dict[str, Any]) -> dict[str, Any]:
    """Schedule a one-off job."""
    worker = payload.get("worker", "")
    action = payload.get("cron_action", "")
    job_payload = payload.get("job_payload", {})
    run_at = payload.get("run_at", "")  # ISO format datetime

    if not worker or not action:
        return {"error": "worker and cron_action required"}
    if not run_at:
        return {"error": "run_at required (ISO format, e.g. 2026-05-06T18:00:00Z)"}

    conn = _get_db()
    cur = conn.execute(
        "INSERT INTO cron_jobs (worker, action, payload, run_at, status, created_at) VALUES (?,?,?,?,?,?)",
        (worker, action, json.dumps(job_payload), run_at, "pending", datetime.now(timezone.utc).isoformat()),
    )
    job_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "job_id": job_id, "run_at": run_at}


def _cancel(payload: dict[str, Any]) -> dict[str, Any]:
    """Cancel a pending cron job."""
    job_id = payload.get("job_id", 0)
    conn = _get_db()
    conn.execute("UPDATE cron_jobs SET status='cancelled' WHERE id=? AND status='pending'", (job_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "job_id": job_id}


def _list(payload: dict[str, Any]) -> dict[str, Any]:
    """List pending cron jobs."""
    status = payload.get("status", "pending")
    conn = _get_db()
    cur = conn.execute(
        "SELECT id, worker, action, payload, run_at, status FROM cron_jobs WHERE status=? ORDER BY run_at",
        (status,),
    )
    rows = [{"id": r[0], "worker": r[1], "action": r[2], "payload": json.loads(r[3]), "run_at": r[4], "status": r[5]} for r in cur.fetchall()]
    conn.close()
    return {"jobs": rows}


def start_cron_checker() -> None:
    """Start background thread to check and execute pending cron jobs."""
    def _check_loop():
        while True:
            try:
                _execute_due_jobs()
            except Exception as exc:
                logger.warning("Cron check error: %s", exc)
            time.sleep(30)

    thread = threading.Thread(target=_check_loop, daemon=True)
    thread.start()
    logger.info("Cron checker started")


def _execute_due_jobs() -> None:
    """Execute any pending jobs that are due."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_db()
    cur = conn.execute(
        "SELECT id, worker, action, payload FROM cron_jobs WHERE status='pending' AND run_at<=?",
        (now,),
    )
    due = cur.fetchall()

    for job_id, worker, action, payload_str in due:
        if not _hermes_ref:
            continue
        try:
            result = _hermes_ref.dispatch(worker, action, json.loads(payload_str))
            conn.execute("UPDATE cron_jobs SET status='done', result=? WHERE id=?", (json.dumps(result.output), job_id))
            logger.info("Cron job %d executed: %s:%s", job_id, worker, action)
        except Exception as exc:
            conn.execute("UPDATE cron_jobs SET status='error', result=? WHERE id=?", (str(exc), job_id))
            logger.warning("Cron job %d failed: %s", job_id, exc)

    conn.commit()
    conn.close()
