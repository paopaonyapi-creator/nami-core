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
);

CREATE INDEX IF NOT EXISTS idx_jobs_idempotency ON jobs (idempotency_key);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status) WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs (parent_id) WHERE parent_id IS NOT NULL;
