# Async Queue (Phase 26.1)

This document describes the Redis Streams + Postgres queue foundation introduced in Phase 26.1.

## Overview

- **Stream:** `nami:jobs` (Redis Streams)
- **Consumer group:** `workers`
- **Dead-letter stream:** `nami:jobs:dead`
- **Events stream:** `nami:events` (fan-out to `/runtime/events`)
- **State:** Postgres `jobs` table

`lottery.backtest_v6` is the canary action routed through the queue. All other actions remain synchronous.

## Environment Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `NAMI_REDIS_URL` | Redis connection for Streams | (required for queue) |
| `NAMI_JOBS_DSN` | Postgres DSN for jobs table | (optional) |
| `NAMI_JOBS_DB` | Postgres DB name if DSN absent | `glodbyproza` |
| `NAMI_JOBS_AUTO_DDL` | Auto-create jobs table on startup | `0` |
| `NAMI_JOB_MAX_RETRIES` | Job retry limit | `3` |
| `NAMI_JOB_MAX_SECONDS` | Per-job timeout | `300` |
| `NAMI_JOB_MAX_TOKENS` | Token budget (LLM) | `50000` |
| `NAMI_SYNC_FALLBACK` | Fall back to sync dispatch when queue fails | `1` |

## Migrations

Apply the Phase 26.1 migration before enabling the queue:

```bash
psql $NAMI_JOBS_DSN -f migrations/0001_jobs_table.sql
```

## Systemd Units

- `deploy/systemd/nami-worker.service` — single worker instance (lottery).
- `deploy/systemd/nami-worker@.service` — templated workers for scaling (Phase 32).
- `deploy/systemd/nami-worker-sync@.service` — legacy sync worker runner.

## Event Flow

1. `POST /dispatch` with `lottery.backtest_v6` → job enqueued in Redis + row inserted in `jobs` table.
2. `nami-worker` consumes from `nami:jobs`, updates job status, and emits events into `nami:events`.
3. `nami-core` bridges `nami:events` → `/runtime/events` SSE + WebSocket broadcast.

## Rollback

- Stop `nami-worker` systemd unit(s).
- Set `NAMI_SYNC_FALLBACK=1` (default) to allow sync dispatch.
- `jobs` table can remain (orphaned rows are acceptable).
