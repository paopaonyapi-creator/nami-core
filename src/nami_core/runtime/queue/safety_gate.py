"""Safety gate for the job enqueue boundary.

Wires SAFETY §7 detectors D7 (recursive deadlock) and D20 (self-replication)
into the enqueue path without modifying `RedisStream.enqueue`. Opt-in:
callers that want safety enforcement at enqueue route through
`safe_enqueue(...)`; legacy callers using `stream.enqueue(message)` directly
keep their behaviour unchanged.

Raises `SafetyRejection` on terminal detection (action=reject) so the
caller surfaces a 409 Conflict to its upstream.
"""

from __future__ import annotations

from typing import Iterable

from nami_core.runtime.queue.redis_stream import RedisStream
from nami_core.runtime.queue.types import JobMessage
from nami_core.safety.detectors import d7, d20
from nami_core.safety.runner import DetectorRunner
from nami_core.safety.types import Detection, DetectorContext, DetectorOutcome


class SafetyRejection(RuntimeError):
    """Raised when the enqueue gate rejects a job per a SAFETY §7 detection."""

    def __init__(self, detection: Detection) -> None:
        super().__init__(f"{detection.pattern}:{detection.action}: {detection.reason}")
        self.detection = detection


_ENQUEUE_DETECTORS = [d7, d20]


def evaluate_enqueue(
    message: JobMessage,
    *,
    parent_chain: Iterable[str] = (),
    parent_payload: dict | None = None,
    detectors: Iterable = _ENQUEUE_DETECTORS,
) -> DetectorOutcome:
    """Pure: run the enqueue-time detectors, return the outcome (no side effects)."""
    ctx = DetectorContext(
        job_id=message.id,
        role="enqueue",
        iteration=0,
        parent_chain=list(parent_chain),
        parent_payload=parent_payload,
        child_payload=dict(message.payload or {}),
    )
    return DetectorRunner(list(detectors)).run(ctx)


def safe_enqueue(
    stream: RedisStream,
    message: JobMessage,
    *,
    parent_chain: Iterable[str] = (),
    parent_payload: dict | None = None,
) -> str:
    """Run enqueue-time safety gate, then enqueue via the given stream.

    Returns the Redis Stream message id on success. Raises `SafetyRejection`
    if any detector returns a `reject` action.
    """
    outcome = evaluate_enqueue(
        message,
        parent_chain=parent_chain,
        parent_payload=parent_payload,
    )
    for det in outcome.detections:
        if det.action == "reject":
            raise SafetyRejection(det)
    return stream.enqueue(message)


__all__ = ["SafetyRejection", "evaluate_enqueue", "safe_enqueue"]
