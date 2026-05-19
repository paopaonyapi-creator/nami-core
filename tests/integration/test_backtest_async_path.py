"""Integration test for async queue dispatch of lottery.backtest_v6."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from nami_core.app import create_app
from nami_core.runtime.queue.jobs_dao import JobsDAO
from nami_core.scheduler import build_core


def _redis_url(container) -> str:
    """Compat shim: testcontainers>=4.10 dropped get_connection_url()."""
    legacy = getattr(container, "get_connection_url", None)
    if callable(legacy):
        return legacy()
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


def test_backtest_dispatch_queues_job(monkeypatch):
    with RedisContainer("redis:7-alpine") as redis, PostgresContainer("postgres:15-alpine") as postgres:
        # driver=None strips `+psycopg2` so psycopg3 can parse the URL.
        pg_dsn = postgres.get_connection_url(driver=None)
        monkeypatch.setenv("NAMI_REDIS_URL", _redis_url(redis))
        monkeypatch.setenv("NAMI_JOBS_DSN", pg_dsn)
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

        dao = JobsDAO(dsn=pg_dsn)
        job = dao.get_by_id(job_id)
        assert job is not None
        assert job["status"] == "queued"
