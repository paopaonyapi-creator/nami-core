"""Reconciler CLI entry — invoked by nami-reconciler.service.

Runs:
  1. JobsReconciler — mark stuck `running` jobs dead.
  2. detect_orphan_workers — log advisory orphan consumers.

Exit code:
  0  no errors and no stuck jobs marked dead
  1  errors during reconciliation
  2  stuck jobs were marked dead (informational; useful for alerting)
"""

from __future__ import annotations

import json
import logging
import os
import sys

from nami_core.runtime.queue.jobs_dao import JobsDAO
from nami_core.runtime.queue.redis_stream import RedisStream
from nami_core.runtime.reconcile.jobs_reconciler import JobsReconciler
from nami_core.runtime.reconcile.orphan_processes import detect_orphan_workers


logging.basicConfig(level=os.environ.get("NAMI_LOG_LEVEL", "INFO"))


def main() -> int:
    dao = JobsDAO()
    reconciler = JobsReconciler(dao=_DAOAdapter(dao))
    job_report = reconciler.run()

    redis = RedisStream()
    orphan_report = detect_orphan_workers(_RedisAdapter(redis))

    print(
        json.dumps(
            {
                "jobs_inspected": job_report.inspected,
                "jobs_marked_dead": job_report.marked_dead,
                "jobs_errors": job_report.errors,
                "orphan_live": orphan_report.live,
                "orphan_consumers": [
                    {"consumer_id": o.consumer_id, "pending": o.pending_count}
                    for o in orphan_report.orphans
                ],
                "orphan_errors": orphan_report.errors,
            },
            ensure_ascii=False,
        )
    )

    if job_report.errors or orphan_report.errors:
        return 1
    if job_report.marked_dead:
        return 2
    return 0


class _DAOAdapter:
    """Adapts `JobsDAO` to the reconciler's `_DAOLike` Protocol.

    Real `JobsDAO` doesn't ship `list_running` yet — this adapter runs
    the SELECT directly and reuses the DAO's `mark_dead`. Keeping the
    adapter small avoids bloating JobsDAO with operational queries.
    """

    def __init__(self, dao: JobsDAO) -> None:
        self.dao = dao

    def list_running(self):
        with self.dao._connect() as conn:  # noqa: SLF001 — intentional, see docstring
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, action, started_at, worker_id
                    FROM jobs
                    WHERE status = 'running' AND started_at IS NOT NULL
                    """
                )
                rows = cur.fetchall()
        return [
            {"id": r[0], "action": r[1], "started_at": r[2], "worker_id": r[3]}
            for r in rows
        ]

    def mark_dead(self, job_id: str, error: dict) -> None:
        self.dao.mark_dead(job_id, error)


class _RedisAdapter:
    """Adapts `RedisStream` to the orphan detector's `_RedisLike`."""

    def __init__(self, redis: RedisStream) -> None:
        self.redis = redis

    def list_worker_heartbeats(self) -> list[str]:
        client = self.redis._get_client()  # noqa: SLF001
        return [k.decode() if isinstance(k, bytes) else str(k)
                for k in client.keys("nami:worker:*")]

    def list_consumers(self, group: str) -> list:
        client = self.redis._get_client()  # noqa: SLF001
        try:
            entries = client.xinfo_consumers("nami:jobs", group)
        except Exception:  # noqa: BLE001 — group may not exist yet
            return []
        out = []
        for entry in entries or []:
            if isinstance(entry, dict):
                out.append({
                    "name": entry.get(b"name") or entry.get("name"),
                    "pending": entry.get(b"pending") or entry.get("pending") or 0,
                })
        # Normalise bytes -> str
        for o in out:
            if isinstance(o["name"], bytes):
                o["name"] = o["name"].decode()
        return out


if __name__ == "__main__":
    sys.exit(main())
