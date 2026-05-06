# Nami Core Roadmap

## Current: v0.13.0 — Dashboard + API Polish (2026-05-06)

- [x] Nginx proxy fix for `/events` (SSE), `/workers/`, write endpoints
- [x] Rate Limits panel in dashboard (per-worker progress bars)
- [x] Interactive API docs at `/docs` (try-it-now for 18 endpoints)
- [x] Alert toast on worker health failure
- [x] Worker detail page (`/workers/[name]`)

## Done

### v0.12.0 — TypeScript SDK + Health Cards
- [x] `nami-dashboard/src/lib/sdk.ts` — `NamiClient` (health, workers, dispatch, batchDispatch, SSE)
- [x] Worker Health Cards with auto-refresh
- [x] Batch Dispatch panel + SSE Event Log
- [x] `docs/examples.md` (curl + TS examples)

### v0.11.0 — Real-Time Layer
- [x] Batch dispatch (`POST /dispatch/batch`, up to 10)
- [x] Webhook HMAC-SHA256 signing
- [x] Worker health checks (`GET /workers/{name}/health`)
- [x] SSE streaming (`GET /events`) with `Last-Event-ID` reconnect
- [x] Redis pub/sub with in-process fallback (`nami_core.pubsub`)

### v0.10.0 — Production Deploy
- [x] Dashboard deployed to Netlify
- [x] `netlify.toml` + `deploy/setup-redis.sh` + `deploy/setup-production.sh`
- [x] API URL settled on `nami.178.104.181.132.nip.io`

### v0.7.0–v0.9.0 — AI Workers + Hardening
- [x] AI workers: `ai_chat`, `sentiment`, `search`, `image`
- [x] Redis cache + cache stats endpoints
- [x] Graceful restart + hot-reload workers
- [x] React/Next.js dashboard (Chart.js, Lucide, Tailwind)
- [x] CSS utility-class refactor + accessibility pass

### v0.4.0–v0.6.0 — API Server + SDK
- [x] FastAPI + uvicorn (replaces stdlib HTTP server)
- [x] WebSocket merged into FastAPI on port 8092
- [x] Swagger / ReDoc / OpenAPI / Prometheus endpoints
- [x] Python SDK (`nami_sdk.client`)
- [x] Email, webhook relay, pipeline workers
- [x] Locust load test
- [x] CI/CD v2 with coverage + auto-release on tag

### v0.1.0–v0.3.0 — Real Service Migration
- [x] Scheduler daemon, cron worker
- [x] HTTP API on port 8092 (auth, CORS, audit)
- [x] WebSocket broadcast for dispatch / webhook / scheduler events
- [x] nginx reverse proxy with WSS
- [x] `gateway_worker.agent_route`, `graphify_worker.load_graphs`
- [x] nami-bot, hanoi-bot, MiroShark, Gold Signal, maxplus-proxy all routed through nami-core
- [x] Cron cleanup (28 → 8 entries)

### v0.0.1 — Foundation + 9 Workers
- [x] Hermes task router and dispatcher
- [x] YAML harness config loader
- [x] Secure secret loading from `/etc/nami-harness`
- [x] PostgreSQL connection pool
- [x] Worker plugin registry with auto-discovery
- [x] 9 base workers (signal, proxy, lottery, bot, trading, gateway, status, bridge, graphify)
- [x] Deploy scripts (systemd, nginx, install.sh)

## Next: v0.14.0 — VPS Production Deploy

Blocked on Day 4–5 distribution outcome. **Do not start until Day 5 decision** says "deploy". See `.audit/NAMI_DAY3_5_UNIFIED_PLAN_2026-05-06.md`.

- [ ] Install Redis on VPS (`bash deploy/setup-redis.sh`)
- [ ] Remove `auth_basic` from public read endpoints (`/health`, `/workers`, `/metrics`, `/docs`, `/ws`)
- [ ] Verify Redis cache backend (`curl https://nami.178.104.181.132.nip.io/cache`)
- [ ] Backup `/opt/nami-core` before pull
- [ ] Pull master and shadow-deploy
- [ ] 24h shadow comparison vs current production services
- [ ] nginx switchover only after shadow comparison passes

## Future: v0.15.0+ — Driven by Real Usage

Unblocked once at least one paid user OR one external developer is using nami-core. Until then, no speculative feature work.

Candidate items (re-prioritize when signal arrives):

- [ ] Per-worker kill switch tested in production
- [ ] Plugin API for third-party workers (entry-points based)
- [ ] Sensor log aggregation + searchable UI
- [ ] Multi-tenant rate limit (per-API-key, not per-worker only)
- [ ] gRPC dispatch alongside HTTP
- [ ] Worker dependency graph visualization
- [ ] Documentation site (mkdocs or Docusaurus)
- [ ] Demo video and tutorial series
