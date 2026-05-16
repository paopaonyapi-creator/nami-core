"""Reconciler CLI integration tests — D13 wiring."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from nami_core.runtime.reconcile.__main__ import _worker_id_from_key, main


_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)


class _FakeJobsDAO:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def list_running(self) -> list[dict]:
        return list(self.rows)

    def mark_dead(self, job_id: str, error: dict) -> None:
        pass

    # Used by _DAOAdapter.list_running fallback path; not triggered when
    # we patch _DAOAdapter directly. Kept for safety.
    def _connect(self):  # pragma: no cover
        raise RuntimeError("test should not connect")


class _FakeRedisAdapter:
    def __init__(self, heartbeat_keys: list[str]) -> None:
        self.heartbeat_keys = heartbeat_keys

    def list_worker_heartbeats(self) -> list[str]:
        return list(self.heartbeat_keys)

    def list_consumers(self, group: str) -> list[dict]:
        return []


def _row(job_id: str, age_seconds: int, worker_id: str | None) -> dict:
    # Use real `datetime.now()` so JobsReconciler (which calls real now() by
    # default) sees fresh rows. The D13 helper accepts an explicit `now=`
    # in production callers; the CLI uses real time for both.
    started = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {
        "id": job_id,
        "action": "agent.run",
        "started_at": started,
        "worker_id": worker_id,
    }


def _run_main(rows: list[dict], heartbeat_keys: list[str]) -> tuple[int, dict]:
    """Run the CLI with patched DAO / Redis adapters; return (exit_code, parsed_json)."""
    with patch("nami_core.runtime.reconcile.__main__.JobsDAO"), \
         patch("nami_core.runtime.reconcile.__main__.RedisStream"), \
         patch(
             "nami_core.runtime.reconcile.__main__._DAOAdapter",
             return_value=_FakeJobsDAO(rows),
         ), \
         patch(
             "nami_core.runtime.reconcile.__main__._RedisAdapter",
             return_value=_FakeRedisAdapter(heartbeat_keys),
         ):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main()
        payload = json.loads(buf.getvalue())
    return code, payload


def test_worker_id_from_key_strips_prefix() -> None:
    assert _worker_id_from_key("nami:worker:lottery-1234") == "lottery-1234"


def test_worker_id_from_key_passthrough_when_no_prefix() -> None:
    assert _worker_id_from_key("bare-id") == "bare-id"


def test_cli_emits_heartbeat_detections_key() -> None:
    code, payload = _run_main(rows=[], heartbeat_keys=[])
    assert "heartbeat_detections" in payload
    assert payload["heartbeat_detections"] == []
    assert code == 0


def test_cli_no_d13_when_heartbeat_present() -> None:
    # Stuck-window default is 2h; keep age below that so no jobs marked dead
    # AND below the D13 60s threshold isn't required (heartbeat present satisfies D13).
    rows = [_row("j1", age_seconds=600, worker_id="w-alive")]
    keys = ["nami:worker:w-alive"]
    code, payload = _run_main(rows=rows, heartbeat_keys=keys)
    assert payload["heartbeat_detections"] == []
    assert payload["jobs_marked_dead"] == []
    assert code == 0


def test_cli_flags_d13_when_heartbeat_missing() -> None:
    # 600s = past D13 60s threshold but well under JobsReconciler 2h stuck window.
    rows = [
        _row("j-fast", age_seconds=10, worker_id="w-alive"),
        _row("j-stale", age_seconds=600, worker_id="w-dead"),
    ]
    keys = ["nami:worker:w-alive"]
    code, payload = _run_main(rows=rows, heartbeat_keys=keys)
    dets = payload["heartbeat_detections"]
    assert len(dets) == 1
    assert dets[0]["pattern"] == "D13"
    assert dets[0]["action"] == "halt_branch"
    assert dets[0]["metadata"]["job_id"] == "j-stale"
    assert dets[0]["metadata"]["worker_id"] == "w-dead"
    assert payload["jobs_marked_dead"] == []  # 600s is far below 2h stuck window
