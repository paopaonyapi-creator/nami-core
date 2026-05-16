from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from nami_core.app import create_app


def test_runtime_job_detail_falls_back_to_queue_job_store(monkeypatch):
    monkeypatch.delenv("NAMI_REDIS_URL", raising=False)
    app = create_app(api_key="test-key")
    app.state.jobs_dao = MagicMock()
    app.state.jobs_dao.get_by_id.return_value = {
        "id": "01HQUEUEJOB000000000000000",
        "action": "lottery.backtest_v6",
        "payload": {"region": "lao"},
        "result": None,
        "error": None,
        "trace_id": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
        "parent_id": None,
        "attempt": 1,
        "worker_id": None,
        "status": "queued",
        "enqueued_at": "2026-05-16T00:00:00+00:00",
        "started_at": None,
        "finished_at": None,
        "updated_at": "2026-05-16T00:00:00+00:00",
    }

    client = TestClient(app)
    response = client.get("/runtime/jobs/01HQUEUEJOB000000000000000")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "01HQUEUEJOB000000000000000"
    assert data["requested_action"] == "lottery.backtest_v6"
    assert data["status"] == "queued"
    assert data["payload"] == {"region": "lao"}
    assert data["source"] == "queue"
