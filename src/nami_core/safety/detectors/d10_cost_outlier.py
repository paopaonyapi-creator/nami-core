"""D10 — Cost outlier: single call cost > 5× rolling p95 for that role."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    p95 = ctx.rolling_p95_cost_usd
    if p95 is None or p95 <= 0:
        return None
    if ctx.call_cost_usd <= 0:
        return None
    if ctx.call_cost_usd < 5 * p95:
        return None
    return Detection(
        pattern="D10",
        action="alert",
        reason=f"cost outlier: ${ctx.call_cost_usd:.4f} > 5× p95 ${p95:.4f}",
        severity="medium",
        metadata={
            "call_cost_usd": ctx.call_cost_usd,
            "p95_cost_usd": p95,
            "ratio": ctx.call_cost_usd / p95,
        },
    )
