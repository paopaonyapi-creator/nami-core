"""D1 — Planner hallucination: plan references a tool not in registry.

Detection: plan output mentions tool not in `ctx.tool_registry`.
Response: reject plan; caller should retry with shorter context.
"""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    plan = ctx.plan or {}
    tool = plan.get("tool") or plan.get("action")
    if not tool:
        return None
    if tool in ctx.tool_registry:
        return None
    return Detection(
        pattern="D1",
        action="reject",
        reason=f"planner referenced unknown tool {tool!r}",
        severity="high",
        metadata={"tool": tool, "registry_size": len(ctx.tool_registry)},
    )
