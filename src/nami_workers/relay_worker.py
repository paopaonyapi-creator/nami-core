"""Webhook relay worker — forward dispatch results to external URLs."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("nami_workers.relay")

RELAY_DB = os.environ.get("NAMI_RELAY_DB", "/tmp/nami_relay.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(RELAY_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relay_hooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            event TEXT NOT NULL DEFAULT 'dispatch',
            headers TEXT DEFAULT '{}',
            active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def relay_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Webhook relay worker: register, unregister, list, trigger."""
    action = payload.get("action", "list")

    if action == "register":
        return _register(payload)
    elif action == "unregister":
        return _unregister(payload)
    elif action == "list":
        return _list()
    elif action == "trigger":
        return _trigger(payload)
    else:
        return {"error": f"unknown action: {action}"}


def _register(payload: dict[str, Any]) -> dict[str, Any]:
    """Register a webhook relay endpoint."""
    url = payload.get("url", "")
    event = payload.get("event", "dispatch")
    headers = payload.get("headers", {})

    if not url:
        return {"error": "url required"}

    conn = _get_db()
    cur = conn.execute(
        "INSERT INTO relay_hooks (url, event, headers, active, created_at) VALUES (?,?,?,?,?)",
        (url, event, json.dumps(headers), 1, datetime.now(timezone.utc).isoformat()),
    )
    hook_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info("Relay hook registered: %d -> %s", hook_id, url)
    return {"ok": True, "hook_id": hook_id, "url": url, "event": event}


def _unregister(payload: dict[str, Any]) -> dict[str, Any]:
    """Deactivate a relay hook."""
    hook_id = payload.get("hook_id", 0)
    conn = _get_db()
    conn.execute("UPDATE relay_hooks SET active=0 WHERE id=?", (hook_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "hook_id": hook_id}


def _list() -> dict[str, Any]:
    """List active relay hooks."""
    conn = _get_db()
    cur = conn.execute("SELECT id, url, event, headers, created_at FROM relay_hooks WHERE active=1")
    hooks = [{"id": r[0], "url": r[1], "event": r[2], "headers": json.loads(r[3]), "created_at": r[4]} for r in cur.fetchall()]
    conn.close()
    return {"hooks": hooks}


def _trigger(payload: dict[str, Any]) -> dict[str, Any]:
    """Fire all matching relay hooks with the given data."""
    event = payload.get("event", "dispatch")
    data = payload.get("data", {})

    conn = _get_db()
    cur = conn.execute("SELECT id, url, headers FROM relay_hooks WHERE event=? AND active=1", (event,))
    hooks = cur.fetchall()
    conn.close()

    results = []
    for hook_id, url, headers_str in hooks:
        try:
            headers = json.loads(headers_str)
            body = json.dumps({"event": event, "data": data}).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json", **headers,
            }, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                results.append({"hook_id": hook_id, "status": resp.status})
                logger.info("Relay fired: %d -> %s (status %d)", hook_id, url, resp.status)
        except Exception as exc:
            results.append({"hook_id": hook_id, "error": str(exc)})
            logger.warning("Relay failed: %d -> %s: %s", hook_id, url, exc)

    return {"ok": True, "fired": len(results), "results": results}
