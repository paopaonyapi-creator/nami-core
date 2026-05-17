"""Redis Streams wrapper for async job queue."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from nami_core.runtime.queue.types import JobMessage

logger = logging.getLogger("nami_core.runtime.queue")

JOB_STREAM = os.environ.get("NAMI_JOB_STREAM", "nami:jobs")
DEAD_STREAM = os.environ.get("NAMI_JOB_DEAD_STREAM", "nami:jobs:dead")
EVENT_STREAM = os.environ.get("NAMI_EVENT_STREAM", "nami:events")

CLAIM_TIMEOUT_MS = int(os.environ.get("NAMI_JOB_CLAIM_TIMEOUT_MS", "120000"))
BLOCK_MS = int(os.environ.get("NAMI_JOB_BLOCK_MS", "5000"))


class RedisStream:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ.get("NAMI_REDIS_URL", "")
        self._client = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.url:
            raise RuntimeError("NAMI_REDIS_URL not configured")
        try:
            import redis

            client = redis.Redis.from_url(
                self.url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            client.ping()
            self._client = client
            return client
        except Exception as exc:
            logger.warning("Redis connection failed: %s", exc)
            self._client = None
            raise

    def ensure_group(self, group: str, *, stream: str = JOB_STREAM) -> None:
        client = self._get_client()
        try:
            client.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def enqueue(self, message: JobMessage) -> str:
        client = self._get_client()
        msg_id = client.xadd(JOB_STREAM, message.to_stream_fields())
        return msg_id

    def enqueue_dead(self, message: JobMessage, error: dict[str, Any]) -> str:
        client = self._get_client()
        payload = message.to_stream_fields()
        payload["error"] = json.dumps(error, ensure_ascii=False, default=str)
        msg_id = client.xadd(DEAD_STREAM, payload)
        return msg_id

    def publish_event(self, event: str, data: dict[str, Any]) -> None:
        client = self._get_client()
        payload = {
            "event": event,
            "data": json.dumps(data, ensure_ascii=False, default=str),
            "timestamp": time.time(),
        }
        client.xadd(EVENT_STREAM, payload)

    def read_group(
        self,
        group: str,
        consumer: str,
        count: int = 1,
        *,
        stream: str = JOB_STREAM,
    ) -> list[tuple[str, dict[str, str]]]:
        client = self._get_client()
        response = client.xreadgroup(group, consumer, {stream: ">"}, count=count, block=BLOCK_MS)
        messages: list[tuple[str, dict[str, str]]] = []
        for _, entries in response:
            for msg_id, fields in entries:
                messages.append((msg_id, fields))
        return messages

    def autoclaim(self, group: str, consumer: str, *, stream: str = JOB_STREAM) -> list[tuple[str, dict[str, str]]]:
        client = self._get_client()
        try:
            # redis-py 4.x returned (cursor, messages); 5.0+ returns
            # (cursor, messages, deleted). Index slice handles both.
            result = client.xautoclaim(stream, group, consumer, CLAIM_TIMEOUT_MS, "0-0")
            messages = result[1] if isinstance(result, (list, tuple)) and len(result) >= 2 else []
        except AttributeError:
            return self._claim_pending_fallback(client, group, consumer, stream)
        return [(msg_id, fields) for msg_id, fields in messages]

    def _claim_pending_fallback(self, client, group: str, consumer: str, stream: str) -> list[tuple[str, dict[str, str]]]:
        pending = client.xpending_range(stream, group, min="-", max="+", count=10)
        ids = [item[0] for item in pending if item[3] >= CLAIM_TIMEOUT_MS]
        if not ids:
            return []
        claimed = client.xclaim(stream, group, consumer, min_idle_time=CLAIM_TIMEOUT_MS, message_ids=ids)
        return [(msg_id, fields) for msg_id, fields in claimed]

    def ack(self, group: str, msg_id: str, *, stream: str = JOB_STREAM) -> None:
        client = self._get_client()
        client.xack(stream, group, msg_id)


__all__ = ["RedisStream", "JOB_STREAM", "DEAD_STREAM", "EVENT_STREAM", "CLAIM_TIMEOUT_MS"]
