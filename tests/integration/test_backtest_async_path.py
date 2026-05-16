"""Integration test for async queue dispatch of lottery.backtest_v6."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from nami_core.app import create_app
from nami_core.runtime.queue.jobs_dao import JobsDAO
from nami_core.scheduler import build_core


def test_backtest_dispatch_queues_job(monkeypatch):
    with RedisContainer("redis:7-alpine") as redis, PostgresContainer("postgres:15-alpine") as postgres:
        monkeypatch.setenv("NAMI_REDIS_URL", redis.get_connection_url())
        monkeypatch.setenv("NAMI_JOBS_DSN", postgres.get_connection_url())
        monkeypatch.setenv("NAMI_JOBS_AUTO_DDL", "1")
        monkeypatch.setenv("NAMI_SYNC_FALLBACK", "0")

        hermes, scheduler = build_core(config_dir="config")
        app = create_app(hermes=hermes, scheduler=scheduler, api_key="test-key")

        with TestClient(app) as client:
            response = client.post(
                "/dispatch",
                headers={"Authorization": "Bearer test-key"},
                json={"worker": "lottery", "action": "backtest_v6", "payload": {"region": "lao"}},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body.get("ok") is True
            assert body.get("status") == "queued"
            job_id = body.get("job_id")
            assert job_id

        dao = JobsDAO(dsn=postgres.get_connection_url())
        job = dao.get_by_id(job_id)
        assert job is not None
        assert job["status"] == "queued"
