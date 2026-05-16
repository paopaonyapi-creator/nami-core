"""D13 heartbeat health check (SAFETY §7 wiring helper).

Pure: takes a list of running jobs + a heartbeat reader callable and
returns the D13 detections for any job that has been running > 60s
without a live heartbeat. Caller (typically the reconciler loop or
the worker auto-claim path) decides whether to XCLAIM, mark stuck,
or just alert.

The detector itself lives in `nami_core.safety.detectors.d13_heartbeat_missing`;
this module is the integration glue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from nami_core.safety.detectors import d13
from nami_core.safety.types import Detection, DetectorContext


@dataclass(frozen=True)
class HeartbeatProbe:
    """One running job + its observed heartbeat presence."""

    job_id: str
    worker_id: str | None
    started_at: datetime
    heartbeat_present: bool


HeartbeatReader = Callable[[str], bool]


def _ensure_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def probes_from_running(
    running_jobs: Iterable[dict],
    heartbeat_reader: HeartbeatReader,
) -> list[HeartbeatProbe]:
    """Build probes from `JobsDAO.list_running()` rows + a heartbeat reader.

    `heartbeat_reader(worker_id) -> bool` should return True iff the
    Redis key `nami:worker:{worker_id}` exists. Caller injects the
    reader so this module stays Redis-free for tests.
    """
    out: list[HeartbeatProbe] = []
    for row in running_jobs:
        started = row.get("started_at")
        if started is None:
            continue
        worker_id = row.get("worker_id")
        heartbeat = bool(heartbeat_reader(worker_id)) if worker_id else False
        out.append(
            HeartbeatProbe(
                job_id=str(row.get("id") or row.get("job_id") or ""),
                worker_id=worker_id,
                started_at=_ensure_utc(started),
                heartbeat_present=heartbeat,
            )
        )
    return out


def check_heartbeat_health(
    probes: Iterable[HeartbeatProbe],
    *,
    now: datetime | None = None,
) -> list[Detection]:
    """Run D13 against each probe; return all firings."""
    now_dt = (now or datetime.now(timezone.utc))
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    detections: list[Detection] = []
    for probe in probes:
        running_seconds = (now_dt - probe.started_at).total_seconds()
        ctx = DetectorContext(
            job_id=probe.job_id,
            role="reconciler",
            iteration=0,
            job_running_seconds=max(0.0, running_seconds),
            heartbeat_present=probe.heartbeat_present,
        )
        det = d13(ctx)
        if det is not None:
            det.metadata.setdefault("job_id", probe.job_id)
            det.metadata.setdefault("worker_id", probe.worker_id)
            detections.append(det)
    return detections


__all__ = [
    "HeartbeatProbe",
    "HeartbeatReader",
    "check_heartbeat_health",
    "probes_from_running",
]
