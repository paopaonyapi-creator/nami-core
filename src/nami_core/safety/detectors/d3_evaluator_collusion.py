"""D3 — Evaluator collusion: rolling acceptance rate > 99% over 100 steps."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    rate = ctx.evaluator_acceptance_rate
    if rate is None:
        return None
    if ctx.evaluator_window_size < 100:
        return None
    if rate <= 0.99:
        return None
    return Detection(
        pattern="D3",
        action="alert",
        reason=f"evaluator acceptance rate {rate:.2%} over {ctx.evaluator_window_size} steps — sample 5% for human review",
        severity="medium",
        metadata={"acceptance_rate": rate, "window_size": ctx.evaluator_window_size},
    )
