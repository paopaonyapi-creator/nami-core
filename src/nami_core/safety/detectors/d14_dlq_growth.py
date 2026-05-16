"""D14 — Stuck DLQ growth: XLEN nami:jobs:dead > 50 in 1h."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


_DLQ_THRESHOLD = 50


def detect(ctx: DetectorContext) -> Detection | None:
    if ctx.dlq_length <= _DLQ_THRESHOLD:
        return None
    return Detection(
        pattern="D14",
        action="halt_action",
        reason=f"DLQ length {ctx.dlq_length} > {_DLQ_THRESHOLD} — auto-pause action with most failures",
        severity="high",
        metadata={"dlq_length": ctx.dlq_length, "threshold": _DLQ_THRESHOLD},
    )
