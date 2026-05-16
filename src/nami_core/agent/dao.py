"""AgentTracesDAO — Phase 27 PR-B follow-up.

Persists agent loop steps to the `agent_traces` table created by
migration `0003_agent_traces.sql`. Mirrors the pattern from
`nami_core.runtime.queue.jobs_dao`.

Best-effort: the DAO is optional in `AgentLoop`. Persistence failures
log a warning and do NOT crash the loop, so observability gaps never
take production down (RUNTIME §9 SLO note: traces are nice-to-have, the
job lifecycle table `jobs` remains source of truth).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from nami_core.agent.state import AgentState, AgentStep
from nami_core.db import get_connection

logger = logging.getLogger("nami_core.agent.dao")


class AgentTracesDAO:
    def __init__(self, dbname: str | None = None, dsn: str | None = None) -> None:
        self.dbname = dbname or os.environ.get("NAMI_JOBS_DB", "glodbyproza")
        self.dsn = dsn or os.environ.get("NAMI_JOBS_DSN")

    def _connect(self):
        if self.dsn:
            import psycopg

            return psycopg.connect(self.dsn)
        return get_connection(self.dbname)

    def ensure_schema(self) -> None:
        """Create the table if missing. Idempotent."""
        statements = [
            """
            CREATE TABLE IF NOT EXISTS agent_traces (
                id              BIGSERIAL PRIMARY KEY,
                job_id          TEXT NOT NULL,
                trace_id        TEXT NOT NULL,
                parent_id       TEXT,
                step_index      INT NOT NULL,
                kind            TEXT NOT NULL
                                CHECK (kind IN ('plan','act','observe','halt')),
                content         TEXT NOT NULL DEFAULT '',
                tool            TEXT,
                tool_args       JSONB NOT NULL DEFAULT '{}'::jsonb,
                tool_result     JSONB,
                cost_usd        NUMERIC(10,6) NOT NULL DEFAULT 0,
                tokens_in       INT NOT NULL DEFAULT 0,
                tokens_out      INT NOT NULL DEFAULT 0,
                depth           INT NOT NULL DEFAULT 0,
                error           TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (job_id, step_index)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_agent_traces_job ON agent_traces (job_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_traces_trace ON agent_traces (trace_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_traces_kind ON agent_traces (kind)",
        ]
        with self._connect() as conn:
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
            conn.commit()

    def insert_step(self, state: AgentState, step: AgentStep, step_index: int) -> bool:
        """Persist one agent step. Returns True on success, False on failure (best-effort)."""
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO agent_traces (
                            job_id, trace_id, parent_id, step_index, kind,
                            content, tool, tool_args, tool_result,
                            cost_usd, tokens_in, tokens_out, depth, error
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                                %s, %s, %s, %s, %s)
                        ON CONFLICT (job_id, step_index) DO NOTHING
                        """,
                        (
                            state.job_id,
                            state.trace_id,
                            state.parent_id,
                            step_index,
                            step.kind,
                            step.content,
                            step.tool,
                            json.dumps(step.tool_args or {}),
                            json.dumps(step.tool_result) if step.tool_result is not None else None,
                            step.cost_usd,
                            step.tokens_in,
                            step.tokens_out,
                            state.depth,
                            step.error,
                        ),
                    )
                conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort persistence
            logger.warning("agent_traces insert failed: %s", exc)
            return False

    def list_for_job(self, job_id: str) -> list[dict[str, Any]]:
        """Read back all steps for a job, ordered by step_index."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT step_index, kind, content, tool, tool_args, tool_result,
                           cost_usd, tokens_in, tokens_out, depth, error, created_at
                    FROM agent_traces
                    WHERE job_id = %s
                    ORDER BY step_index ASC
                    """,
                    (job_id,),
                )
                rows = cur.fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "step_index": row[0],
                    "kind": row[1],
                    "content": row[2],
                    "tool": row[3],
                    "tool_args": row[4],
                    "tool_result": row[5],
                    "cost_usd": float(row[6]) if row[6] is not None else 0.0,
                    "tokens_in": row[7],
                    "tokens_out": row[8],
                    "depth": row[9],
                    "error": row[10],
                    "created_at": row[11].isoformat() if row[11] else None,
                }
            )
        return result


__all__ = ["AgentTracesDAO"]
