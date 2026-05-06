"""Notification worker — routes alerts to users via Telegram, email, webhook."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("nami_workers.notification")

# In-memory subscriber list (could be persisted to DB)
_subscribers: dict[str, list[dict[str, str]]] = {}


def notification_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Notification worker: send, subscribe, unsubscribe."""
    action = payload.get("action", "send")

    if action == "send":
        return _send(payload)
    elif action == "subscribe":
        return _subscribe(payload)
    elif action == "unsubscribe":
        return _unsubscribe(payload)
    elif action == "list":
        return {"subscribers": {k: v for k, v in _subscribers.items()}}
    else:
        return {"error": f"unknown action: {action}"}


def _send(payload: dict[str, Any]) -> dict[str, Any]:
    """Send notification to all subscribers of an event type."""
    event = payload.get("event", "alert")
    message = payload.get("message", "")
    channel = payload.get("channel", "all")

    targets = _subscribers.get(event, []) + _subscribers.get("all", [])
    sent = 0

    for sub in targets:
        t = sub.get("type", "telegram")
        if t == "telegram":
            try:
                from nami_workers.utils import telegram_send
                telegram_send(sub["chat_id"], message)
                sent += 1
            except Exception as e:
                logger.warning("Telegram send failed: %s", e)
        elif t == "webhook":
            try:
                from urllib.request import Request, urlopen
                data = json.dumps({"text": message}).encode("utf-8")
                req = Request(sub["url"], data=data, headers={"Content-Type": "application/json"})
                urlopen(req, timeout=10)
                sent += 1
            except Exception as e:
                logger.warning("Webhook send failed: %s", e)

    return {"sent": sent, "event": event, "message_length": len(message)}


def _subscribe(payload: dict[str, Any]) -> dict[str, Any]:
    """Subscribe to notifications."""
    event = payload.get("event", "all")
    sub_type = payload.get("type", "telegram")
    chat_id = payload.get("chat_id", "")
    url = payload.get("url", "")

    entry = {"type": sub_type}
    if sub_type == "telegram":
        entry["chat_id"] = chat_id
    elif sub_type == "webhook":
        entry["url"] = url

    if event not in _subscribers:
        _subscribers[event] = []
    _subscribers[event].append(entry)
    return {"ok": True, "event": event, "type": sub_type}


def _unsubscribe(payload: dict[str, Any]) -> dict[str, Any]:
    """Unsubscribe from notifications."""
    event = payload.get("event", "all")
    chat_id = payload.get("chat_id", "")
    url = payload.get("url", "")

    if event in _subscribers:
        before = len(_subscribers[event])
        _subscribers[event] = [
            s for s in _subscribers[event]
            if not (s.get("chat_id") == chat_id or s.get("url") == url)
        ]
        removed = before - len(_subscribers[event])
        return {"ok": True, "removed": removed}
    return {"ok": True, "removed": 0}
