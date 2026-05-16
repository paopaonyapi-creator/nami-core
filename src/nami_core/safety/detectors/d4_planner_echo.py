"""D4 — Planner echo: plan hash identical to a prior iteration."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    hist = ctx.plan_hash_history
    if len(hist) < 2:
        return None
    current = hist[-1]
    prior = hist[:-1]
    if current in prior:
        return Detection(
            pattern="D4",
            action="force_reroll",
            reason="planner output identical to a prior iteration",
            severity="medium",
            metadata={"plan_hash": current, "first_seen_at": prior.index(current)},
        )
    return None
