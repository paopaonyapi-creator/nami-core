"""Analytics worker — tracks dispatch history and provides aggregated stats."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("nami_workers.analytics")

DB_PATH = os.environ.get("NAMI_ANALYTICS_DB", "/tmp/nami_analytics.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dispatch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker TEXT NOT NULL,
            action TEXT NOT NULL,
            latency_ms REAL,
            ok BOOLEAN,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def analytics_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Analytics worker: dispatch_log, summary, leaderboard."""
    action = payload.get("action", "summary")

    if action == "dispatch_log":
        return _log_dispatch(payload)
    elif action == "summary":
        return _summary(payload)
    elif action == "leaderboard":
        return _leaderboard(payload)
    elif action == "recent":
        return _recent(payload)
    else:
        return {"error": f"unknown action: {action}"}


def _log_dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a dispatch event."""
    conn = _get_db()
    conn.execute(
        "INSERT INTO dispatch_log (worker, action, latency_ms, ok, timestamp) VALUES (?, ?, ?, ?, ?)",
        (
            payload.get("worker", ""),
            payload.get("action", ""),
            payload.get("latency_ms", 0),
            payload.get("ok", True),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return {"logged": True}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Get aggregated summary stats."""
    conn = _get_db()
    cur = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN ok THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN NOT ok THEN 1 ELSE 0 END) as errors,
            AVG(latency_ms) as avg_latency,
            MAX(latency_ms) as max_latency
        FROM dispatch_log
    """)
    row = cur.fetchone()
    conn.close()
    return {
        "total": row[0] or 0,
        "success": row[1] or 0,
        "errors": row[2] or 0,
        "avg_latency_ms": round(row[3] or 0, 1),
        "max_latency_ms": round(row[4] or 0, 1),
    }


def _leaderboard(payload: dict[str, Any]) -> dict[str, Any]:
    """Get top workers by dispatch count."""
    limit = payload.get("limit", 10)
    conn = _get_db()
    cur = conn.execute(
        "SELECT worker, COUNT(*) as cnt, AVG(latency_ms) as avg_lat FROM dispatch_log GROUP BY worker ORDER BY cnt DESC LIMIT ?",
        (limit,),
    )
    rows = [{"worker": r[0], "count": r[1], "avg_latency_ms": round(r[2] or 0, 1)} for r in cur.fetchall()]
    conn.close()
    return {"leaderboard": rows}


def _recent(payload: dict[str, Any]) -> dict[str, Any]:
    """Get recent dispatches."""
    limit = payload.get("limit", 20)
    conn = _get_db()
    cur = conn.execute(
        "SELECT worker, action, latency_ms, ok, timestamp FROM dispatch_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = [{"worker": r[0], "action": r[1], "latency_ms": r[2], "ok": bool(r[3]), "timestamp": r[4]} for r in cur.fetchall()]
    conn.close()
    return {"recent": rows}
