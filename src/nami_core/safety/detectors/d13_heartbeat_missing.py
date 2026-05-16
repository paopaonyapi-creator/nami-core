"""D13 — Worker heartbeat missing: job 'running' > 60s but no Redis heartbeat key."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    if ctx.job_running_seconds <= 60:
        return None
    if ctx.heartbeat_present:
        return None
    return Detection(
        pattern="D13",
        action="halt_branch",
        reason=f"worker heartbeat missing for {ctx.job_running_seconds:.0f}s — XCLAIM to another worker",
        severity="high",
        metadata={"running_seconds": ctx.job_running_seconds},
    )
