"""Idempotency behavior backed by Postgres jobs table."""

from __future__ import annotations

from testcontainers.postgres import PostgresContainer

from nami_core.runtime.queue.idempotency import idempotency_key
from nami_core.runtime.queue.jobs_dao import JobsDAO
from nami_core.runtime.queue.types import JobBudget
from nami_core.runtime.queue.ulid import generate_ulid


def test_idempotency_key_stable_for_payload_order():
    payload_a = {"region": "lao", "days": 10}
    payload_b = {"days": 10, "region": "lao"}
    assert idempotency_key("lottery.backtest_v6", payload_a) == idempotency_key("lottery.backtest_v6", payload_b)


def test_idempotency_returns_existing_job():
    with PostgresContainer("postgres:15-alpine") as postgres:
        # driver=None drops the `+psycopg2` suffix that confuses psycopg3.
        dsn = postgres.get_connection_url(driver=None)
        dao = JobsDAO(dsn=dsn)
        dao.ensure_schema()

        job_id = generate_ulid()
        action = "lottery.backtest_v6"
        payload = {"region": "lao"}
        key = idempotency_key(action, payload)
        dao.insert_job(
            job_id=job_id,
            action=action,
            payload=payload,
            idempotency_key=key,
            trace_id="00-" + "e" * 32 + "-" + "f" * 16 + "-01",
            parent_id=None,
            budget=JobBudget(),
            status="running",
            attempt=1,
        )

        existing = dao.get_by_idempotency(key)
        assert existing is not None
        assert existing["id"] == job_id
