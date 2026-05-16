"""D11 — Latency outlier: single call latency > 5× rolling p95."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    p95 = ctx.rolling_p95_latency_ms
    if p95 is None or p95 <= 0:
        return None
    if ctx.call_latency_ms <= 0:
        return None
    if ctx.call_latency_ms < 5 * p95:
        return None
    return Detection(
        pattern="D11",
        action="alert",
        reason=f"latency outlier: {ctx.call_latency_ms:.0f}ms > 5× p95 {p95:.0f}ms",
        severity="medium",
        metadata={
            "call_latency_ms": ctx.call_latency_ms,
            "p95_latency_ms": p95,
            "ratio": ctx.call_latency_ms / p95,
        },
    )
