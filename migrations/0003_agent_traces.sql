-- Phase 27 PR-B: agent_traces table.
-- One row per agent step (plan/act/observe/halt) per RUNTIME §7.
-- Indexed by job_id, trace_id for OTel correlation.

CREATE TABLE IF NOT EXISTS agent_traces (
    id              BIGSERIAL PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
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
);

CREATE INDEX IF NOT EXISTS idx_agent_traces_job ON agent_traces (job_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_trace ON agent_traces (trace_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_kind ON agent_traces (kind);
