"""D17 — Agent role mixing: same loop instance emits >1 role (forbidden F8)."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    roles = set(ctx.role_history)
    if len(roles) <= 1:
        return None
    return Detection(
        pattern="D17",
        action="halt_branch",
        reason=f"role mixing detected: {sorted(roles)}",
        severity="high",
        metadata={"roles": sorted(roles), "role_history": list(ctx.role_history)},
    )
