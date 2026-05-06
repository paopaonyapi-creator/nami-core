# nami-core v0.13.0

## Highlights
- Dashboard users now get per-worker rate limit visibility with green, yellow, and red progress bars.
- The dashboard now includes an interactive `/docs` page with try-it-now support for all 18 endpoints.
- Worker health failures now surface as fixed-position alert toasts.
- The TypeScript SDK covers health, workers, dispatch, batch dispatch, worker health, rate limits, and SSE events.
- Runtime APIs now include batch dispatch, webhook HMAC signing, worker health checks, SSE streaming, and Redis pub/sub fallback.

## Changes

### Added
- Nginx proxy locations for `/events`, `/workers/` sub-paths, `/webhook/verify`, `/rotate-key`, `/restart`, `/reload-workers`, and `/cache/flush`.
- Dashboard Rate Limits panel for per-worker rate limit status.
- Interactive dashboard API docs at `/docs` with API key storage and worker-name inputs.
- Alert toast when a worker health check fails.
- Header API Docs link with BookOpen icon.
- TypeScript SDK in `nami-dashboard/src/lib/sdk.ts`.
- Worker Health Cards with 30-second auto-refresh.
- Batch Dispatch panel.
- SSE Event Log with LIVE/OFF indicator.
- API examples in `docs/examples.md`.
- Batch dispatch endpoint at `POST /dispatch/batch` for up to 10 dispatches.
- Webhook HMAC-SHA256 signing with `NAMI_WEBHOOK_SECRET` and `GET /webhook/verify`.
- Worker health endpoint at `GET /workers/{name}/health`.
- SSE streaming endpoint at `GET /events` with heartbeat and `Last-Event-ID` reconnect support.
- Redis pub/sub module with in-process broadcast fallback.

### Changed
- App version moved from 0.12.0 to 0.13.0.
- Nginx config split into dedicated locations for SSE, workers, and write endpoints.
- Dashboard worker chips changed to Worker Health Cards with health status.
- Webhook responses now include a `signature` field with `sha256=<hex>` HMAC.
- Test count moved to 225 passing tests.

## Upgrade Notes
- From v0.10.x: install Redis for production, or use the in-process fallback.
- From v0.11.x: webhook responses now include an HMAC `signature` field.
- Dashboard users should re-run `npm install` for the SDK-backed dashboard module.

## What's Next
- VPS shadow deploy is pending the Day 5 decision.
- See `ROADMAP.md` for v0.14.0 scope.

## Verification
- `python -m pytest` -> 225 passed
