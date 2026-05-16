-- Phase 28: mcp_calls audit trail.
-- One row per MCP invocation per EVOLUTION §2.3 + GOVERNANCE §5.
-- trace_id is NOT NULL so the audit-completeness check
--   SELECT count(*) FROM mcp_calls WHERE trace_id IS NULL = 0
-- is structurally satisfied.

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
);

CREATE INDEX IF NOT EXISTS idx_mcp_calls_trace ON mcp_calls (trace_id);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_server_tool ON mcp_calls (server, tool);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_status ON mcp_calls (status);
