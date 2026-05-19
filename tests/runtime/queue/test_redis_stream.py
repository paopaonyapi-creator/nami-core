"""Redis Streams queue integration tests."""

from __future__ import annotations

from datetime import datetime, timezone

from testcontainers.redis import RedisContainer

from nami_core.runtime.queue.redis_stream import EVENT_STREAM, RedisStream
from nami_core.runtime.queue.types import JobBudget, JobMessage


def _redis_url(container) -> str:
    """Compat shim: testcontainers>=4.10 dropped get_connection_url()."""
    legacy = getattr(container, "get_connection_url", None)
    if callable(legacy):
        return legacy()
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


def _sample_message() -> JobMessage:
    return JobMessage(
        id="01HZZZFAKEJOB000000000000",
        action="lottery.backtest_v6",
        payload={"region": "lao"},
        idempotency_key="abc123",
        trace_id="00-" + "a" * 32 + "-" + "b" * 16 + "-01",
        parent_id=None,
        budget=JobBudget(),
        enqueued_at=datetime.now(timezone.utc).isoformat(),
        attempt=1,
    )


def test_enqueue_and_read_group():
    with RedisContainer("redis:7-alpine") as redis:
        stream = RedisStream(_redis_url(redis))
        stream.ensure_group("workers")
        message = _sample_message()
        stream.enqueue(message)

        messages = stream.read_group("workers", "consumer-1", count=1)
        assert messages
        msg_id, fields = messages[0]
        parsed = JobMessage.from_stream_fields(fields)
        assert parsed.id == message.id
        stream.ack("workers", msg_id)


def test_publish_event_stream():
    with RedisContainer("redis:7-alpine") as redis:
        stream = RedisStream(_redis_url(redis))
        stream.ensure_group("sse-bridge", stream=EVENT_STREAM)
        stream.publish_event("job.queued", {"job_id": "job-1"})

        events = stream.read_group("sse-bridge", "consumer-1", count=1, stream=EVENT_STREAM)
        assert events
        msg_id, fields = events[0]
        assert fields.get("event") == "job.queued"
        stream.ack("sse-bridge", msg_id, stream=EVENT_STREAM)
