"""D20 — Self-replication: child enqueue would re-spawn self with identical params.

Detection: child payload (the job about to be enqueued) deep-equals the
parent's own payload. Idempotency-key checks catch this in the queue layer
already; this detector surfaces the *attempt* as a metric/alert so we can
spot agents trying to self-replicate before the queue silently drops them.
"""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    parent = ctx.parent_payload
    child = ctx.child_payload
    if parent is None or child is None:
        return None
    if parent == child:
        return Detection(
            pattern="D20",
            action="reject",
            reason="agent attempted to enqueue a child job with payload identical to its own",
            severity="high",
            metadata={"payload_keys": sorted(parent.keys())},
        )
    return None
