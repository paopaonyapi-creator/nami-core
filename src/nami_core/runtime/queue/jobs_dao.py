"""Postgres-backed job persistence for async queue."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from nami_core.db import get_connection
from nami_core.runtime.queue.types import JobBudget


JOB_STATUSES = {"queued", "running", "succeeded", "failed", "dead", "cancelled"}


class JobsDAO:
    def __init__(self, dbname: str | None = None, dsn: str | None = None) -> None:
        self.dbname = dbname or os.environ.get("NAMI_JOBS_DB", "glodbyproza")
        self.dsn = dsn or os.environ.get("NAMI_JOBS_DSN")

    def _connect(self):
        if self.dsn:
            import psycopg

            return psycopg.connect(self.dsn)
        return get_connection(self.dbname)

    def ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id              TEXT PRIMARY KEY,
                action          TEXT NOT NULL,
                payload         JSONB NOT NULL,
                idempotency_key TEXT NOT NULL,
                trace_id        TEXT NOT NULL,
                parent_id       TEXT REFERENCES jobs(id),
                budget          JSONB NOT NULL,
                status          TEXT NOT NULL DEFAULT 'queued'
                                CHECK (status IN ('queued','running','succeeded','failed','dead','cancelled')),
                attempt         INT NOT NULL DEFAULT 1,
                result          JSONB,
                error           JSONB,
                worker_id       TEXT,
                enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
                started_at      TIMESTAMPTZ,
                finished_at     TIMESTAMPTZ,
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_jobs_idempotency ON jobs (idempotency_key)",
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status) WHERE status IN ('queued','running')",
            "CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs (parent_id) WHERE parent_id IS NOT NULL",
        ]
        with self._connect() as conn:
            for stmt in statements:
                conn.execute(stmt)
            conn.commit()

    def insert_job(
        self,
        *,
        job_id: str,
        action: str,
        payload: dict[str, Any],
        idempotency_key: str,
        trace_id: str,
        parent_id: str | None,
        budget: JobBudget,
        status: str = "queued",
        attempt: int = 1,
    ) -> None:
        if status not in JOB_STATUSES:
            raise ValueError(f"invalid status: {status}")
        budget_payload = json.dumps(asdict(budget), ensure_ascii=False, default=str)
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (id, action, payload, idempotency_key, trace_id, parent_id, budget, status, attempt, enqueued_at, updated_at)
                    VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s, now(), now())
                    """,
                    (job_id, action, payload_json, idempotency_key, trace_id, parent_id, budget_payload, status, attempt),
                )
            conn.commit()

    def get_by_id(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
                row = cur.fetchone()
                if not row:
                    return None
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))

    def get_by_idempotency(self, key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM jobs
                    WHERE idempotency_key = %s
                    ORDER BY enqueued_at DESC
                    LIMIT 1
                    """,
                    (key,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))

    def mark_running(self, job_id: str, worker_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'running', started_at = now(), updated_at = now(), worker_id = %s
                    WHERE id = %s
                    """,
                    (worker_id, job_id),
                )
            conn.commit()

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> None:
        payload = json.dumps(result, ensure_ascii=False, default=str)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'succeeded', result = %s::jsonb, finished_at = now(), updated_at = now()
                    WHERE id = %s
                    """,
                    (payload, job_id),
                )
            conn.commit()

    def mark_failed(self, job_id: str, error: dict[str, Any], attempt: int) -> None:
        payload = json.dumps(error, ensure_ascii=False, default=str)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', error = %s::jsonb, attempt = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (payload, attempt, job_id),
                )
            conn.commit()

    def mark_dead(self, job_id: str, error: dict[str, Any]) -> None:
        payload = json.dumps(error, ensure_ascii=False, default=str)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'dead', error = %s::jsonb, finished_at = now(), updated_at = now()
                    WHERE id = %s
                    """,
                    (payload, job_id),
                )
            conn.commit()

    def requeue(self, job_id: str, attempt: int) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'queued', attempt = %s, updated_at = now(), enqueued_at = now()
                    WHERE id = %s
                    """,
                    (attempt, job_id),
                )
            conn.commit()


__all__ = ["JobsDAO", "JOB_STATUSES"]
