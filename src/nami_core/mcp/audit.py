"""MCP audit DAO — Phase 28.

Persists every MCP invocation to the `mcp_calls` table per
EVOLUTION §2.3 audit-trail requirement. Mirrors the best-effort
pattern of `nami_core.agent.dao.AgentTracesDAO`: connect failure
returns False, never raises.

Audit completeness contract (validation #3 of Phase 28):
    SELECT count(*) FROM mcp_calls WHERE trace_id IS NULL = 0
The DAO normalises trace_id to "" rather than NULL when missing,
matching the column NOT NULL constraint defined in the migration.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from nami_core.db import get_connection
from nami_core.mcp.types import MCPRequest, MCPResponse

logger = logging.getLogger("nami_core.mcp.audit")


def _hash_payload(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MCPAuditDAO:
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
            CREATE TABLE IF NOT EXISTS mcp_calls (
                id              BIGSERIAL PRIMARY KEY,
                trace_id        TEXT NOT NULL,
                job_id          TEXT NOT NULL DEFAULT '',
                server          TEXT NOT NULL,
                tool            TEXT NOT NULL,
                role            TEXT NOT NULL,
                input_hash      TEXT NOT NULL,
                output_hash     TEXT,
                status          TEXT NOT NULL
                                CHECK (status IN ('ok','denied','escape','timeout','error')),
                error           TEXT,
                latency_ms      INT NOT NULL DEFAULT 0,
                sandboxed       BOOLEAN NOT NULL DEFAULT TRUE,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_mcp_calls_trace ON mcp_calls (trace_id)",
            "CREATE INDEX IF NOT EXISTS idx_mcp_calls_server_tool ON mcp_calls (server, tool)",
            "CREATE INDEX IF NOT EXISTS idx_mcp_calls_status ON mcp_calls (status)",
        ]
        with self._connect() as conn:
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
            conn.commit()

    def record(
        self,
        request: MCPRequest,
        response: MCPResponse | None,
        status: str,
        error: str | None = None,
    ) -> bool:
        """Insert one audit row. Returns True on success, False on DB failure."""
        if status not in {"ok", "denied", "escape", "timeout", "error"}:
            raise ValueError(f"invalid mcp status: {status}")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO mcp_calls (
                            trace_id, job_id, server, tool, role,
                            input_hash, output_hash, status, error,
                            latency_ms, sandboxed
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            request.trace_id or "",
                            request.job_id or "",
                            request.server,
                            request.tool,
                            request.role,
                            _hash_payload(request.args),
                            _hash_payload(response.output) if response is not None else None,
                            status,
                            error,
                            response.latency_ms if response is not None else 0,
                            response.sandboxed if response is not None else False,
                        ),
                    )
                conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort persistence
            logger.warning("mcp_calls insert failed: %s", exc)
            return False

    def list_for_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT trace_id, job_id, server, tool, role,
                           input_hash, output_hash, status, error,
                           latency_ms, sandboxed, created_at
                    FROM mcp_calls
                    WHERE trace_id = %s
                    ORDER BY id ASC
                    """,
                    (trace_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "trace_id": r[0],
                "job_id": r[1],
                "server": r[2],
                "tool": r[3],
                "role": r[4],
                "input_hash": r[5],
                "output_hash": r[6],
                "status": r[7],
                "error": r[8],
                "latency_ms": r[9],
                "sandboxed": r[10],
                "created_at": r[11].isoformat() if r[11] else None,
            }
            for r in rows
        ]


__all__ = ["MCPAuditDAO"]
