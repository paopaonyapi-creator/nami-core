"""Queue worker lifecycle tests (pending reclaim)."""

from __future__ import annotations

import importlib
import time
from datetime import datetime, timezone

from testcontainers.redis import RedisContainer

from nami_core.runtime.queue.types import JobBudget, JobMessage


def test_autoclaim_reclaims_pending(monkeypatch):
    monkeypatch.setenv("NAMI_JOB_CLAIM_TIMEOUT_MS", "100")
    import nami_core.runtime.queue.redis_stream as redis_stream

    importlib.reload(redis_stream)

    with RedisContainer("redis:7-alpine") as redis:
        stream = redis_stream.RedisStream(redis.get_connection_url())
        stream.ensure_group("workers")
        message = JobMessage(
            id="01HZZZFAKEJOB000000000001",
            action="lottery.backtest_v6",
            payload={"region": "lao"},
            idempotency_key="claim-key",
            trace_id="00-" + "c" * 32 + "-" + "d" * 16 + "-01",
            parent_id=None,
            budget=JobBudget(),
            enqueued_at=datetime.now(timezone.utc).isoformat(),
            attempt=1,
        )
        stream.enqueue(message)

        pending = stream.read_group("workers", "consumer-1", count=1)
        assert pending
        msg_id, _ = pending[0]

        time.sleep(0.2)
        reclaimed = stream.autoclaim("workers", "consumer-2")
        assert any(entry_id == msg_id for entry_id, _ in reclaimed)
