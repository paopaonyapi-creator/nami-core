"""DLQ growth scan helper (SAFETY §7 D14 wiring).

Pure: takes a DLQ length + a per-action failure-count mapping, runs D14,
and reports the top-failing action so the caller can issue a K2 halt for
that action. The actual Redis read (`XLEN nami:jobs:dead` and
`XRANGE`-style sampling) belongs to the caller — this module stays
infrastructure-free for unit testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from nami_core.safety.detectors import d14
from nami_core.safety.types import Detection, DetectorContext


@dataclass(frozen=True)
class DLQScanResult:
    """Result of a single DLQ scan pass."""

    dlq_length: int
    detection: Detection | None
    top_action: str | None
    top_action_count: int


def scan_dlq(
    *,
    dlq_length: int,
    action_failure_counts: Mapping[str, int] | None = None,
) -> DLQScanResult:
    """Run D14 + identify the action with the most DLQ entries (if any).

    `action_failure_counts` is a mapping of `action_name -> count` taken
    from a recent DLQ sample. Caller decides the sample size. If empty,
    the scan still runs D14 (length-only) and returns `top_action=None`.
    """
    ctx = DetectorContext(
        job_id="",
        role="dlq-scanner",
        iteration=0,
        dlq_length=max(0, int(dlq_length)),
    )
    detection = d14(ctx)
    top_action: str | None = None
    top_count = 0
    if action_failure_counts:
        top_action, top_count = max(
            action_failure_counts.items(), key=lambda kv: (kv[1], kv[0])
        )
        if detection is not None:
            detection.metadata.setdefault("top_action", top_action)
            detection.metadata.setdefault("top_action_count", top_count)
    return DLQScanResult(
        dlq_length=dlq_length,
        detection=detection,
        top_action=top_action,
        top_action_count=top_count,
    )


__all__ = ["DLQScanResult", "scan_dlq"]
