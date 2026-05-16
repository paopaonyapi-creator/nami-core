"""Tests for D14 DLQ-length wiring on /runtime/health."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from nami_core.app import create_app
from nami_core.hermes import Hermes
from nami_harness.runtime import HarnessContext, HarnessResult, HarnessRuntime


class _MockScheduler:
    def status(self):
        return {"running": True, "jobs": 0}


def _client_with_dlq(dlq_length: int | Exception) -> TestClient:
    hermes = Hermes()
    runtime = MagicMock(spec=HarnessRuntime)
    ctx = HarnessContext(agent="hermes", action="health", estimated_cost=0, correlation_id="")
    runtime.run.return_value = HarnessResult(context=ctx, output={"status": "ok"}, passed_quality=True)
    hermes.register("status", runtime, lambda payload: {"status": "ok"}, actions={"health"})
    app = create_app(hermes=hermes, scheduler=_MockScheduler(), api_key="test-key")

    fake_client = MagicMock()
    if isinstance(dlq_length, Exception):
        fake_client.xlen.side_effect = dlq_length
    else:
        fake_client.xlen.return_value = dlq_length
    app.state.job_stream._get_client = lambda: fake_client  # noqa: SLF001
    return TestClient(app)


def test_runtime_health_reports_dlq_length_below_threshold() -> None:
    client = _client_with_dlq(10)
    response = client.get("/runtime/health")
    assert response.status_code == 200
    dlq = response.json()["dlq"]
    assert dlq["length"] == 10
    assert dlq["stream"] == "nami:jobs:dead"
    assert "detection" not in dlq


def test_runtime_health_surfaces_d14_above_threshold() -> None:
    client = _client_with_dlq(75)
    response = client.get("/runtime/health")
    assert response.status_code == 200
    dlq = response.json()["dlq"]
    assert dlq["length"] == 75
    detection = dlq["detection"]
    assert detection["pattern"] == "D14"
    assert detection["action"] == "halt_action"


def test_runtime_health_at_threshold_no_detection() -> None:
    client = _client_with_dlq(50)
    response = client.get("/runtime/health")
    dlq = response.json()["dlq"]
    assert dlq["length"] == 50
    assert "detection" not in dlq


def test_runtime_health_redis_failure_returns_zero_with_error() -> None:
    client = _client_with_dlq(RuntimeError("connection refused"))
    response = client.get("/runtime/health")
    assert response.status_code == 200
    dlq = response.json()["dlq"]
    assert dlq["length"] == 0
    assert "error" in dlq
    assert "connection refused" in dlq["error"]
    assert "detection" not in dlq
