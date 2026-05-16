"""D2 — Executor loop: same (action, payload) repeats 3× consecutively."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    history = ctx.action_payload_history
    if len(history) < 3:
        return None
    last3 = history[-3:]
    if last3[0] == last3[1] == last3[2]:
        action, payload_hash = last3[0]
        return Detection(
            pattern="D2",
            action="halt_branch",
            reason=f"executor loop: ({action!r}, {payload_hash[:8]}…) ×3 consecutive",
            severity="high",
            metadata={"action": action, "payload_hash": payload_hash},
        )
    return None
