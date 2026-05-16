"""Tests for the D13 heartbeat health helper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nami_core.runtime.reconcile.heartbeat_health import (
    HeartbeatProbe,
    check_heartbeat_health,
    probes_from_running,
)


_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)


def _probe(job_id: str, age_seconds: float, heartbeat: bool, worker: str = "w1") -> HeartbeatProbe:
    return HeartbeatProbe(
        job_id=job_id,
        worker_id=worker,
        started_at=_NOW - timedelta(seconds=age_seconds),
        heartbeat_present=heartbeat,
    )


# ── check_heartbeat_health ─────────────────────────────────────────────


def test_missing_heartbeat_past_threshold_fires() -> None:
    dets = check_heartbeat_health([_probe("j1", 120, heartbeat=False)], now=_NOW)
    assert len(dets) == 1
    assert dets[0].pattern == "D13"
    assert dets[0].metadata["job_id"] == "j1"
    assert dets[0].metadata["worker_id"] == "w1"


def test_present_heartbeat_passes() -> None:
    dets = check_heartbeat_health([_probe("j1", 600, heartbeat=True)], now=_NOW)
    assert dets == []


def test_short_running_skipped_even_without_heartbeat() -> None:
    dets = check_heartbeat_health([_probe("j1", 30, heartbeat=False)], now=_NOW)
    assert dets == []


def test_mixed_batch_only_flags_offenders() -> None:
    probes = [
        _probe("ok-fast", 30, heartbeat=False),
        _probe("ok-alive", 300, heartbeat=True),
        _probe("missing-1", 200, heartbeat=False, worker="w-a"),
        _probe("missing-2", 1000, heartbeat=False, worker="w-b"),
    ]
    dets = check_heartbeat_health(probes, now=_NOW)
    flagged = {d.metadata["job_id"] for d in dets}
    assert flagged == {"missing-1", "missing-2"}


def test_empty_probes_empty_detections() -> None:
    assert check_heartbeat_health([], now=_NOW) == []


# ── probes_from_running ────────────────────────────────────────────────


def _row(job_id: str, age_seconds: float, worker: str | None = "w1") -> dict:
    return {
        "id": job_id,
        "action": "agent.run",
        "started_at": _NOW - timedelta(seconds=age_seconds),
        "worker_id": worker,
    }


def test_probes_from_running_uses_injected_reader() -> None:
    seen: list[str] = []

    def reader(worker_id: str) -> bool:
        seen.append(worker_id)
        return worker_id == "alive"

    rows = [_row("j1", 200, worker="alive"), _row("j2", 200, worker="dead")]
    probes = probes_from_running(rows, reader)
    assert {p.job_id for p in probes} == {"j1", "j2"}
    assert {p.heartbeat_present for p in probes} == {True, False}
    assert sorted(seen) == ["alive", "dead"]


def test_probes_skip_rows_without_started_at() -> None:
    rows = [{"id": "x", "started_at": None, "worker_id": "w1"}]
    probes = probes_from_running(rows, lambda _w: True)
    assert probes == []


def test_probes_coerce_naive_started_at_to_utc() -> None:
    naive = (_NOW - timedelta(seconds=200)).replace(tzinfo=None)
    rows = [{"id": "j", "started_at": naive, "worker_id": "w1"}]
    probes = probes_from_running(rows, lambda _w: False)
    assert probes[0].started_at.tzinfo is not None
    dets = check_heartbeat_health(probes, now=_NOW)
    assert len(dets) == 1


def test_probes_no_worker_id_marks_heartbeat_missing() -> None:
    rows = [_row("j", 200, worker=None)]
    probes = probes_from_running(rows, lambda _w: True)
    assert probes[0].heartbeat_present is False
    dets = check_heartbeat_health(probes, now=_NOW)
    assert len(dets) == 1
