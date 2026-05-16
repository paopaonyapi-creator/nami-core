"""D7 — Recursive deadlock: child job ancestry forms a cycle.

Detection: current `job_id` already appears in `parent_chain` (the list of
ancestors from root to immediate parent). That means enqueuing this job
would create a cycle in the parent DAG.
Response: reject at enqueue (caller surfaces 409 Conflict).
"""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    if not ctx.parent_chain:
        return None
    if ctx.job_id in ctx.parent_chain:
        idx = ctx.parent_chain.index(ctx.job_id)
        return Detection(
            pattern="D7",
            action="reject",
            reason=f"recursive deadlock: job_id {ctx.job_id!r} appears at depth {idx} in parent chain",
            severity="high",
            metadata={
                "job_id": ctx.job_id,
                "cycle_depth": idx,
                "parent_chain_length": len(ctx.parent_chain),
            },
        )
    return None
