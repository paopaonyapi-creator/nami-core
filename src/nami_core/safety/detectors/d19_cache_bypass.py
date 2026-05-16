"""D19 — Cache-bypass coordinated attack: temperature varied to inflate cost.

Heuristic: temperature > 0.0 paired with planner-echo (same plan hash twice)
suggests deliberate cache invalidation. Standalone temperature > 0 is normal
sampling, so this only fires when echo is also present.
"""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    if ctx.temperature <= 0.0:
        return None
    hist = ctx.plan_hash_history
    if len(hist) < 2:
        return None
    # Same plan repeated under non-zero temperature ⇒ caller is rolling
    # the same prompt with new sampling — pure cache-bypass shape.
    if hist[-1] == hist[-2]:
        return Detection(
            pattern="D19",
            action="alert",
            reason=f"non-zero temperature ({ctx.temperature:.2f}) with repeated plan — cache-bypass shape",
            severity="medium",
            metadata={"temperature": ctx.temperature, "plan_hash": hist[-1]},
        )
    return None
