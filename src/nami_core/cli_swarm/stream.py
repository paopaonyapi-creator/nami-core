"""Phase 32 — Redis stream publisher for CLI pane output (L8.5).

Publishes to `nami:cli:{session_id}` so nami-os `/runtime/terminal/{session}`
SSE endpoint can consume. Best-effort: Redis unavailable → log + drop.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

logger = logging.getLogger("nami_core.cli_swarm.stream")


class StreamPublisher(Protocol):
    def publish(self, stream: str, payload: dict) -> bool: ...
    def trim(self, stream: str, maxlen: int) -> bool: ...


class RedisStreamPublisher:
    """Real backend — wraps `redis.Redis` from RUNTIME §3 queue lib.

    Defers import so tests don't require redis installed.
    """

    def __init__(self, url: str | None = None) -> None:
        import os

        import redis  # noqa: F401 — present in main runtime

        self._url = url or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        self._client = __import__("redis").Redis.from_url(self._url)

    def publish(self, stream: str, payload: dict) -> bool:
        try:
            self._client.xadd(stream, {k: str(v) for k, v in payload.items()})
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("cli stream publish failed: %s", exc)
            return False

    def trim(self, stream: str, maxlen: int) -> bool:
        try:
            self._client.xtrim(stream, maxlen=maxlen, approximate=True)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("cli stream trim failed: %s", exc)
            return False


class InMemoryPublisher:
    """Test backend. Stores published entries in a dict-of-list."""

    def __init__(self) -> None:
        self.streams: dict[str, list[dict]] = {}

    def publish(self, stream: str, payload: dict) -> bool:
        self.streams.setdefault(stream, []).append(payload)
        return True

    def trim(self, stream: str, maxlen: int) -> bool:
        if stream in self.streams and len(self.streams[stream]) > maxlen:
            self.streams[stream] = self.streams[stream][-maxlen:]
        return True


def make_event(
    session_id: str,
    kind: str,
    body: str,
    *,
    timestamp: float | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "kind": kind,  # one of: stdout, stderr, status, lifecycle
        "body": body,
        "ts": timestamp if timestamp is not None else time.time(),
    }


__all__ = ["StreamPublisher", "RedisStreamPublisher", "InMemoryPublisher", "make_event"]
