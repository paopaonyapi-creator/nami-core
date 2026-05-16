"""D5 — Budget burn front-loaded: 80% of cost consumed in first 20% of iterations.

Heuristic: an agent that spends most of its budget early is likely stuck in
expensive planning + producing little useful work. Linearly reduce remaining
iteration cap (caller decides how — detector just surfaces the signal).
"""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    history = ctx.iter_cost_history
    total_budget = ctx.iter_budget_total
    if not history or total_budget <= 0:
        return None
    n = len(history)
    if n < 5:
        return None
    cutoff = max(1, n // 5)  # first 20%
    early_cost = sum(history[:cutoff])
    total_cost = sum(history)
    if total_cost <= 0:
        return None
    early_share = early_cost / total_cost
    if early_share < 0.80:
        return None
    return Detection(
        pattern="D5",
        action="alert",
        reason=(
            f"front-loaded burn: {early_share:.0%} of spend in first {cutoff}/{n} iters "
            f"(${early_cost:.4f}/${total_cost:.4f})"
        ),
        severity="medium",
        metadata={
            "early_share": early_share,
            "early_cost": early_cost,
            "total_cost": total_cost,
            "iters": n,
            "cutoff": cutoff,
        },
    )
