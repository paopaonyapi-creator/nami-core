"""Nami Core — Redis Pub/Sub for real-time event distribution.

Publishes dispatch, webhook, scheduler events to Redis channel.
Subscribers (WS handler, SSE handler) receive events in real-time.
Falls back to in-process broadcast if Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable

logger = logging.getLogger("nami_core.pubsub")

CHANNEL = "nami:events"

# ── Publisher ──

_redis_client = None


def _get_redis():
    """Lazy Redis client init."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        url = os.environ.get("NAMI_REDIS_URL", "")
        if not url:
            return None
        _redis_client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        _redis_client.ping()  # verify connection
        logger.info("Pub/Sub: Redis connected (%s)", url)
        return _redis_client
    except Exception as exc:
        logger.warning("Pub/Sub: Redis unavailable, using in-process fallback: %s", exc)
        _redis_client = None  # will retry on next call
        return None


def publish(event: str, data: dict[str, Any]) -> None:
    """Publish an event to Redis pub/sub channel."""
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
    client = _get_redis()
    if client:
        try:
            client.publish(CHANNEL, payload)
            return
        except Exception as exc:
            logger.warning("Pub/Sub: Redis publish failed: %s", exc)
    # Fallback: no-op (WSManager handles in-process broadcast)


# ── Subscriber ──

_subscriber_thread = None
_subscriber_stop = threading.Event()


def start_subscriber(callback: Callable[[str, dict[str, Any]], None]) -> None:
    """Start a background thread that subscribes to Redis events.

    Args:
        callback: async or sync function(event_name, data_dict)
    """
    global _subscriber_thread
    if _subscriber_thread is not None and _subscriber_thread.is_alive():
        return

    def _run():
        while not _subscriber_stop.is_set():
            client = _get_redis()
            if not client:
                _subscriber_stop.wait(5)
                continue
            try:
                pubsub = client.pubsub()
                pubsub.subscribe(CHANNEL)
                logger.info("Pub/Sub: subscribed to %s", CHANNEL)
                while not _subscriber_stop.is_set():
                    msg = pubsub.get_message(timeout=1)
                    if msg and msg["type"] == "message":
                        try:
                            payload = json.loads(msg["data"])
                            callback(payload.get("event", "unknown"), payload.get("data", {}))
                        except (json.JSONDecodeError, KeyError) as exc:
                            logger.warning("Pub/Sub: bad message: %s", exc)
            except Exception as exc:
                logger.warning("Pub/Sub: subscriber error: %s", exc)
                _subscriber_stop.wait(5)

    _subscriber_stop.clear()
    _subscriber_thread = threading.Thread(target=_run, daemon=True, name="nami-pubsub")
    _subscriber_thread.start()
    logger.info("Pub/Sub: subscriber thread started")


def stop_subscriber() -> None:
    """Stop the background subscriber thread."""
    _subscriber_stop.set()
    logger.info("Pub/Sub: subscriber stopped")
