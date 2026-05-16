"""D8 — Orphaned child: parent already terminal but child still running.

Detection: `parent_status` is one of {failed, cancelled} but this child has
not yet been cancelled. SAFETY §7 says: cancel child via `nami:cancel:{root}`.
Detector surfaces a halt_branch so the loop tears itself down.
"""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


_TERMINAL_PARENT_STATES = {"failed", "cancelled"}


def detect(ctx: DetectorContext) -> Detection | None:
    status = ctx.parent_status
    if status is None:
        return None
    if status not in _TERMINAL_PARENT_STATES:
        return None
    return Detection(
        pattern="D8",
        action="halt_branch",
        reason=f"parent in terminal state {status!r}; cancelling orphaned child",
        severity="high",
        metadata={"parent_status": status},
    )
