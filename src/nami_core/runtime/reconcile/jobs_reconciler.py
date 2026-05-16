"""Stuck-job reconciler — Phase 30.

Finds jobs in `running` state for longer than the stuck-window and
marks them dead. Runs from a systemd timer every 10 minutes per
NAMI_OS_OPERATIONS.md §7.

Stuck-window default: 2h (configurable via NAMI_RECONCILE_STUCK_HOURS).
This must be > the longest legitimate job runtime — if a real job
takes longer, the reconciler will kill it spuriously. Tune with
production data; current backtest_v6 runs <30m so 2h has headroom.

Validation #2 (Phase 30):
    Stuck job injected → reconciler marks failed within 10 min.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

logger = logging.getLogger("nami_core.runtime.reconcile.jobs")


@dataclass(frozen=True)
class StuckJob:
    job_id: str
    action: str
    started_at: datetime
    age_seconds: int
    worker_id: str | None


@dataclass
class ReconcileReport:
    inspected: int = 0
    stuck: list[StuckJob] = field(default_factory=list)
    marked_dead: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class _DAOLike(Protocol):
    """Subset of `JobsDAO` the reconciler needs.

    Real prod uses `nami_core.runtime.queue.jobs_dao.JobsDAO`; tests
    inject a fake implementing the same shape.
    """

    def list_running(self) -> list[dict[str, Any]]: ...
    def mark_dead(self, job_id: str, error: dict[str, Any]) -> None: ...


class JobsReconciler:
    def __init__(
        self,
        dao: _DAOLike,
        stuck_after_seconds: int | None = None,
        now: callable | None = None,  # type: ignore[type-arg]
    ) -> None:
        self.dao = dao
        env_hours = float(os.environ.get("NAMI_RECONCILE_STUCK_HOURS", "2"))
        self.stuck_after_seconds = (
            stuck_after_seconds if stuck_after_seconds is not None else int(env_hours * 3600)
        )
        self._now = now or (lambda: datetime.now(timezone.utc))

    def run(self) -> ReconcileReport:
        report = ReconcileReport()
        now = self._now()
        threshold = now - timedelta(seconds=self.stuck_after_seconds)
        try:
            rows = self.dao.list_running()
        except Exception as exc:  # noqa: BLE001 — best-effort daemon
            report.errors.append(f"list_running: {exc}")
            return report

        report.inspected = len(rows)
        for row in rows:
            started_at = row.get("started_at")
            if not isinstance(started_at, datetime):
                continue
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if started_at >= threshold:
                continue
            stuck = StuckJob(
                job_id=str(row["id"]),
                action=str(row.get("action") or ""),
                started_at=started_at,
                age_seconds=int((now - started_at).total_seconds()),
                worker_id=row.get("worker_id"),
            )
            report.stuck.append(stuck)
            try:
                self.dao.mark_dead(
                    stuck.job_id,
                    {
                        "error": "stuck-reconciler",
                        "age_seconds": stuck.age_seconds,
                        "stuck_after_seconds": self.stuck_after_seconds,
                        "worker_id": stuck.worker_id,
                    },
                )
                report.marked_dead.append(stuck.job_id)
                logger.warning(
                    "marked stuck job dead: id=%s action=%s age_s=%s worker=%s",
                    stuck.job_id,
                    stuck.action,
                    stuck.age_seconds,
                    stuck.worker_id,
                )
            except Exception as exc:  # noqa: BLE001 — keep going on per-job failure
                report.errors.append(f"{stuck.job_id}: {exc}")
        return report


def reconcile_stuck_jobs(dao: _DAOLike, stuck_after_seconds: int | None = None) -> ReconcileReport:
    return JobsReconciler(dao, stuck_after_seconds=stuck_after_seconds).run()


__all__ = ["JobsReconciler", "ReconcileReport", "StuckJob", "reconcile_stuck_jobs"]
