-- Phase 29 — agent memory tables (episodic + semantic embeddings).
-- RUNTIME §10 LOCKED: Postgres rows = source of truth; pgvector = derivative.
-- Embedding dim 1536 matches OpenAI text-embedding-3-small.

CREATE TABLE IF NOT EXISTS agent_episodes (
    id            BIGSERIAL PRIMARY KEY,
    job_id        TEXT NOT NULL,
    trace_id      TEXT,
    role          TEXT NOT NULL,
    summary       TEXT NOT NULL,
    outcome       TEXT NOT NULL CHECK (outcome IN ('succeeded','failed','cancelled')),
    cost_usd      NUMERIC(12, 6) NOT NULL DEFAULT 0,
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ NOT NULL,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding     vector(1536),
    model_version TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_episodes_job_id   ON agent_episodes (job_id);
CREATE INDEX IF NOT EXISTS idx_agent_episodes_role     ON agent_episodes (role);
CREATE INDEX IF NOT EXISTS idx_agent_episodes_finished ON agent_episodes (finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_episodes_model    ON agent_episodes (model_version);

-- Semantic store for project knowledge (rebuildable from `source_ref`).
CREATE TABLE IF NOT EXISTS embeddings (
    id            BIGSERIAL PRIMARY KEY,
    namespace     TEXT NOT NULL,
    source_ref    TEXT NOT NULL,
    chunk_index   INT  NOT NULL DEFAULT 0,
    content       TEXT NOT NULL,
    embedding     vector(1536) NOT NULL,
    model_version TEXT NOT NULL,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (namespace, source_ref, chunk_index, model_version)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_namespace ON embeddings (namespace);
CREATE INDEX IF NOT EXISTS idx_embeddings_model     ON embeddings (model_version);
