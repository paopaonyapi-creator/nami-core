"""Tests for the enqueue-time safety gate (D7 + D20 wiring)."""

from __future__ import annotations

import pytest

from nami_core.runtime.queue.safety_gate import (
    SafetyRejection,
    evaluate_enqueue,
    safe_enqueue,
)
from nami_core.runtime.queue.types import JobBudget, JobMessage


class FakeStream:
    def __init__(self) -> None:
        self.enqueued: list[JobMessage] = []

    def enqueue(self, message: JobMessage) -> str:
        self.enqueued.append(message)
        return f"stream-id-{len(self.enqueued)}"


def _msg(job_id: str = "j1", payload: dict | None = None) -> JobMessage:
    return JobMessage(
        id=job_id,
        action="agent.run",
        payload=payload if payload is not None else {"task": "do thing"},
        idempotency_key=f"ik-{job_id}",
        trace_id="t1",
        parent_id=None,
        budget=JobBudget(),
        enqueued_at="2026-05-16T12:00:00Z",
    )


# ── evaluate_enqueue (pure) ────────────────────────────────────────────


def test_evaluate_clean_job_no_detections() -> None:
    outcome = evaluate_enqueue(_msg())
    assert outcome.detections == []
    assert outcome.halt is False


def test_evaluate_d7_cycle_detected() -> None:
    outcome = evaluate_enqueue(_msg(job_id="j2"), parent_chain=["root", "j1", "j2"])
    patterns = {d.pattern for d in outcome.detections}
    assert "D7" in patterns


def test_evaluate_d20_self_replication_detected() -> None:
    payload = {"task": "do thing", "model": "x"}
    outcome = evaluate_enqueue(_msg(payload=payload), parent_payload=dict(payload))
    patterns = {d.pattern for d in outcome.detections}
    assert "D20" in patterns


# ── safe_enqueue (gate + delegate) ─────────────────────────────────────


def test_safe_enqueue_passes_clean_job_to_stream() -> None:
    stream = FakeStream()
    msg_id = safe_enqueue(stream, _msg())
    assert msg_id == "stream-id-1"
    assert len(stream.enqueued) == 1


def test_safe_enqueue_rejects_d7_cycle() -> None:
    stream = FakeStream()
    with pytest.raises(SafetyRejection) as exc:
        safe_enqueue(stream, _msg(job_id="j2"), parent_chain=["root", "j1", "j2"])
    assert exc.value.detection.pattern == "D7"
    assert exc.value.detection.action == "reject"
    assert stream.enqueued == []


def test_safe_enqueue_rejects_d20_self_replication() -> None:
    stream = FakeStream()
    payload = {"task": "loop", "args": {"x": 1}}
    with pytest.raises(SafetyRejection) as exc:
        safe_enqueue(stream, _msg(payload=payload), parent_payload=dict(payload))
    assert exc.value.detection.pattern == "D20"
    assert stream.enqueued == []


def test_safety_rejection_message_includes_pattern_and_reason() -> None:
    stream = FakeStream()
    try:
        safe_enqueue(stream, _msg(job_id="j2"), parent_chain=["j2"])
    except SafetyRejection as exc:
        text = str(exc)
        assert "D7" in text
        assert "reject" in text
        return
    pytest.fail("expected SafetyRejection")


def test_safe_enqueue_no_parent_chain_no_cycle_check() -> None:
    """If caller omits parent_chain, D7 has no input → no rejection."""
    stream = FakeStream()
    msg_id = safe_enqueue(stream, _msg())
    assert msg_id.startswith("stream-id-")
    assert len(stream.enqueued) == 1


def test_safe_enqueue_returns_underlying_stream_id() -> None:
    stream = FakeStream()
    a = safe_enqueue(stream, _msg(job_id="a"))
    b = safe_enqueue(stream, _msg(job_id="b"))
    assert a == "stream-id-1"
    assert b == "stream-id-2"
    assert [m.id for m in stream.enqueued] == ["a", "b"]
