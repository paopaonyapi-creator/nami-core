"""Phase 30 — stuck-job reconciler tests.

Validates Phase 30 §validation #2: stuck job → reconciler marks
failed within the configured window. Tests use a FakeDAO; no
Postgres connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from nami_core.runtime.reconcile import (
    JobsReconciler,
    OrphanReport,
    OrphanWorker,
    ReconcileReport,
    StuckJob,
    detect_orphan_workers,
    reconcile_stuck_jobs,
)


@dataclass
class FakeJobsDAO:
    rows: list[dict[str, Any]] = field(default_factory=list)
    dead: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    raise_on_list: Exception | None = None
    raise_on_mark: Exception | None = None

    def list_running(self) -> list[dict[str, Any]]:
        if self.raise_on_list is not None:
            raise self.raise_on_list
        return list(self.rows)

    def mark_dead(self, job_id: str, error: dict[str, Any]) -> None:
        if self.raise_on_mark is not None:
            raise self.raise_on_mark
        self.dead.append((job_id, error))


def _now() -> datetime:
    return datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)


def _row(job_id: str, age_seconds: int, **extra: Any) -> dict[str, Any]:
    started = _now() - timedelta(seconds=age_seconds)
    base = {
        "id": job_id,
        "action": "lottery.backtest_v6",
        "started_at": started,
        "worker_id": "nami-worker-lottery-12345",
    }
    base.update(extra)
    return base


# ── stuck detection ────────────────────────────────────────────────────


def test_no_running_jobs_yields_empty_report() -> None:
    dao = FakeJobsDAO()
    report = JobsReconciler(dao=dao, now=_now).run()
    assert report.inspected == 0
    assert report.stuck == []
    assert report.marked_dead == []


def test_fresh_job_within_window_not_marked() -> None:
    dao = FakeJobsDAO(rows=[_row("j1", age_seconds=60)])
    report = JobsReconciler(dao=dao, stuck_after_seconds=7200, now=_now).run()
    assert report.inspected == 1
    assert report.stuck == []
    assert dao.dead == []


def test_stuck_job_marked_dead() -> None:
    """Phase 30 §validation #2: stuck job (>2h) → reconciler marks failed."""
    dao = FakeJobsDAO(rows=[_row("j-stuck", age_seconds=3 * 3600)])
    report = JobsReconciler(dao=dao, stuck_after_seconds=7200, now=_now).run()
    assert report.inspected == 1
    assert len(report.stuck) == 1
    stuck = report.stuck[0]
    assert stuck.job_id == "j-stuck"
    assert stuck.age_seconds == 3 * 3600
    assert report.marked_dead == ["j-stuck"]
    assert dao.dead[0][0] == "j-stuck"
    assert dao.dead[0][1]["error"] == "stuck-reconciler"
    assert dao.dead[0][1]["age_seconds"] == 3 * 3600


def test_mixed_fresh_and_stuck() -> None:
    dao = FakeJobsDAO(
        rows=[
            _row("fresh", age_seconds=60),
            _row("stuck1", age_seconds=10 * 3600),
            _row("stuck2", age_seconds=4 * 3600),
        ]
    )
    report = JobsReconciler(dao=dao, stuck_after_seconds=7200, now=_now).run()
    assert report.inspected == 3
    assert sorted(report.marked_dead) == ["stuck1", "stuck2"]


def test_naive_started_at_treated_as_utc() -> None:
    """Some Postgres drivers return naive datetimes; reconciler must coerce to UTC."""
    naive_started = (_now() - timedelta(hours=5)).replace(tzinfo=None)
    dao = FakeJobsDAO(
        rows=[{"id": "j-naive", "action": "x", "started_at": naive_started, "worker_id": None}]
    )
    report = JobsReconciler(dao=dao, stuck_after_seconds=7200, now=_now).run()
    assert report.marked_dead == ["j-naive"]


def test_missing_started_at_skipped() -> None:
    dao = FakeJobsDAO(
        rows=[{"id": "j-no-start", "action": "x", "started_at": None, "worker_id": None}]
    )
    report = JobsReconciler(dao=dao, stuck_after_seconds=7200, now=_now).run()
    assert report.inspected == 1
    assert report.stuck == []
    assert dao.dead == []


def test_list_failure_returns_error_no_crash() -> None:
    dao = FakeJobsDAO(raise_on_list=RuntimeError("db down"))
    report = JobsReconciler(dao=dao, now=_now).run()
    assert report.inspected == 0
    assert any("db down" in e for e in report.errors)


def test_mark_failure_keeps_iterating() -> None:
    """One per-job failure must not stop the rest of the batch."""
    dao = FakeJobsDAO(
        rows=[_row("a", age_seconds=10 * 3600), _row("b", age_seconds=10 * 3600)],
        raise_on_mark=RuntimeError("constraint conflict"),
    )
    report = JobsReconciler(dao=dao, stuck_after_seconds=7200, now=_now).run()
    assert report.inspected == 2
    assert len(report.stuck) == 2
    assert report.marked_dead == []  # both failed
    assert len(report.errors) == 2


def test_helper_function_alias() -> None:
    dao = FakeJobsDAO(rows=[_row("j1", age_seconds=10 * 3600)])
    report = reconcile_stuck_jobs(dao, stuck_after_seconds=3600)
    assert report.marked_dead == ["j1"]


def test_env_var_default_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAMI_RECONCILE_STUCK_HOURS", "0.5")
    dao = FakeJobsDAO(rows=[_row("j", age_seconds=2000)])
    report = JobsReconciler(dao=dao, now=_now).run()
    # 0.5h = 1800s; job age 2000s → stuck
    assert report.marked_dead == ["j"]


# ── orphan worker detection ───────────────────────────────────────────


@dataclass
class FakeRedis:
    heartbeats: list[str] = field(default_factory=list)
    consumers: list[dict[str, Any]] = field(default_factory=list)
    raise_on_hb: Exception | None = None
    raise_on_consumers: Exception | None = None

    def list_worker_heartbeats(self) -> list[str]:
        if self.raise_on_hb is not None:
            raise self.raise_on_hb
        return list(self.heartbeats)

    def list_consumers(self, group: str) -> list[dict[str, Any]]:
        if self.raise_on_consumers is not None:
            raise self.raise_on_consumers
        return list(self.consumers)


def test_orphan_detector_finds_consumer_without_heartbeat() -> None:
    redis = FakeRedis(
        heartbeats=["nami:worker:nami-worker-lottery-9999"],
        consumers=[
            {"name": "nami-worker-lottery-9999", "pending": 0},
            {"name": "nami-worker-lottery-OLD", "pending": 5},
        ],
    )
    report = detect_orphan_workers(redis)
    assert report.live == ["nami:worker:nami-worker-lottery-9999"]
    assert len(report.orphans) == 1
    assert report.orphans[0].consumer_id == "nami-worker-lottery-OLD"
    assert report.orphans[0].pending_count == 5


def test_orphan_detector_ignores_consumers_with_zero_pending() -> None:
    redis = FakeRedis(
        heartbeats=[],
        consumers=[{"name": "ghost", "pending": 0}],
    )
    report = detect_orphan_workers(redis)
    assert report.orphans == []


def test_orphan_detector_handles_redis_failure() -> None:
    redis = FakeRedis(raise_on_hb=RuntimeError("redis down"))
    report = detect_orphan_workers(redis)
    assert report.orphans == []
    assert any("redis down" in e for e in report.errors)


def test_orphan_detector_handles_consumer_listing_failure() -> None:
    redis = FakeRedis(heartbeats=["nami:worker:x"], raise_on_consumers=RuntimeError("noop"))
    report = detect_orphan_workers(redis)
    assert report.live == ["nami:worker:x"]
    assert any("noop" in e for e in report.errors)
