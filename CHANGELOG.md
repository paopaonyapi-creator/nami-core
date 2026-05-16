# Changelog

## 0.15.0 — 2026-05-09

### Added
- **Lottery worker** new actions for nami-os Phase 21 dashboard:
  - `latest_prediction(region)` — tile-friendly latest locked Lao prediction
  - `accuracy_stats(region, last_n)` — per-bet-type hit rate, streak, last hit date
  - `history(region, limit)` — last N predictions paired with actual draws + per-row hit/miss flag
  - `hot_cold(region, window_days)` — digit frequency map over time window
- **`_lao_db_connect`** dual-path: tries Unix-socket peer auth first, falls back to TCP+password.

### Changed
- **`_lao_db_query`** migrated from `psql` shell-out (pipe-delim parsing) to `psycopg` with parameterised queries.
- Closes SQL-injection surface where `prediction_id` was f-string interpolated.
- Falls back to legacy psql path only if psycopg is missing AND no parameters supplied.
- **`Hermes.dispatch`** — now injects `action` into payload before invoking the worker task. Without this, workers that route on `payload["action"]` (e.g. lottery, ai_chat) couldn't see the action that Hermes was given. Caller-supplied `action` in payload still wins.
- **`config/lottery_harness.yaml`** — added `latest_prediction`, `accuracy_stats`, `history`, `hot_cold` to `allowed_actions`. Removed the stale `quality.require_non_empty: [prediction]` rule that rejected every result not shaped like the legacy `predict` action.
- **App version**: 0.14.0 -> 0.15.0.

### Notes
- No new dependencies — `psycopg[binary]>=3.1` already pinned.
- **Operator action:** `/etc/nami-harness/postgres_password` must contain the actual postgres password (`nami2024` per the working `nami-os.env`). Earlier secret was stale and caused TCP auth fail; service runs as `root` so socket peer auth also fails.

## 0.14.0 — 2026-05-07

### Added
- **Runtime API v2** under `/runtime/*`: health, tools, tool invoke, jobs, events.
- **Tool registry + execution policy**: classifies actions as `read_only`, `protected_read`, `mutating`, `dangerous`, `admin_only` with server-side enforcement.
- **Persistent runtime jobs** with optional JSON storage via `NAMI_RUNTIME_JOBS_FILE`.
- **MCP client** (`src/nami_core/mcp_client.py`) for `stdio`, `sse`, `websocket` transports with reconnect/health controls.
- **MCP config loader** (`src/nami_core/mcp_config.py`) and `config/mcp_servers.example.yaml`.
- `/runtime/mcp/servers`, `/runtime/mcp/tools`, `/runtime/mcp/tools/invoke`, `/runtime/mcp/reconnect`.
- **Phase 6 rollback diagnostics**: pre/post git worktree snapshots, changed-file diagnostics, recovery metadata.
- `/runtime/jobs/{job_id}/recovery/preview`, `/recovery/diff`, `/recovery/restore` (authenticated, with stale-candidate guard).
- Diagnostics runners (Runtime API pytest, dashboard build) gated by `NAMI_RUNTIME_DIAGNOSTIC_CHECKS`.
- Environment-specific diagnostics policies via `NAMI_RUNTIME_ENV` and `NAMI_RUNTIME_DIAGNOSTIC_POLICY_<ENV>`.
- Runtime recovery events broadcast through WebSocket `runtime.event` channel.
- Dashboard Runtime API v2 panel: tools, jobs, snapshot detail, recovery preview/diff/restore, MCP servers, MCP tool invocation, MCP reconnect.
- TypeScript SDK helpers for Runtime API v2 and MCP.
- `tests/test_runtime_api_v2.py` (772 lines) and `tests/test_mcp_config.py` (67 lines).
- `docs/codex-handoff.md` and `docs/deepseek-tui-adaptation-plan.md`.

### Changed
- **App version**: 0.13.0 -> 0.14.0.
- **`pyproject.toml` version**: 0.3.0 -> 0.14.0 (sync with runtime app).
- Discovered MCP tools share `/runtime/tools` with worker tools (single registry surface).
- **Tests**: 225 -> 258 passed (+33).

### Notes
- Runtime API v2 endpoints are additive; existing dispatch/workers behavior unchanged.
- MCP is opt-in (no servers configured by default).

## 0.13.0 — 2026-05-06

### Added

- **Nginx Proxy Fix**: Added `/events` (SSE with `proxy_buffering off`), `/workers/` sub-paths, `/webhook/verify`, `/rotate-key`, `/restart`, `/reload-workers`, `/cache/flush` — all endpoints now properly proxied
- **Rate Limits Panel**: Dashboard card showing per-worker rate limit status with green/yellow/red progress bars, requires API key input
- **Interactive API Docs**: New `/docs` page — try-it-now for all 18 endpoints, API key stored in localStorage, worker name input for `{name}` paths
- **Alert Toast**: Fixed-position notification when worker health check fails
- **API Docs Link**: BookOpen icon in header linking to `/docs`

### Changed

- **App version**: 0.12.0 → 0.13.0
- **Nginx config**: Split into dedicated locations for SSE, workers, write endpoints

## 0.12.0 — 2026-05-06

### Added

- **TypeScript SDK**: `nami-dashboard/src/lib/sdk.ts` — `NamiClient` class with health, workers, dispatch, batchDispatch, workerHealth, rateLimit, events (SSE)
- **Worker Health Cards**: Dashboard shows per-worker health status with green/red badges, auto-refresh every 30s
- **Batch Dispatch Panel**: Dashboard UI for sending multiple dispatches in one request
- **SSE Event Log**: Real-time event stream display with LIVE/OFF indicator
- **API Examples**: `docs/examples.md` — curl + TypeScript examples for all endpoints

### Changed

- **App version**: 0.11.0 → 0.12.0
- **Dashboard**: WorkerChips → WorkerHealthCards with health status

## 0.11.0 — 2026-05-06

### Added

- **Batch Dispatch**: `POST /dispatch/batch` — send up to 10 dispatches in one request, returns array of results
- **Webhook Auth Signing**: HMAC-SHA256 payload signing with `NAMI_WEBHOOK_SECRET` (auto-generated if not set), `GET /webhook/verify` for verification instructions
- **Worker Health Checks**: `GET /workers/{name}/health` — run a worker's health action and return detailed status (public read)
- **SSE Streaming**: `GET /events` — Server-Sent Events stream for real-time dashboard updates with heartbeat and `Last-Event-ID` reconnect support
- **Redis Pub/Sub**: `nami_core.pubsub` module — publish/subscribe via Redis channel `nami:events`, falls back to in-process broadcast

### Changed

- **App version**: 0.10.0 → 0.11.0
- **Webhook response**: now includes `signature` field with `sha256=<hex>` HMAC
- **Tests**: 225 passed (was 213)

## 0.10.0 — 2026-05-06

### Added

- **Dashboard deployed to Netlify**: `https://nami-dashboard-5e6b3149.netlify.app` — CDN, HTTPS, auto-deploy
- **`netlify.toml`**: Next.js build config with `@netlify/plugin-nextjs`
- **`deploy/setup-redis.sh`**: Redis production setup script (install, configure, verify)
- **`deploy/setup-production.sh`**: Full VPS production setup (Redis + nginx API proxy + env config)

### Changed

- **API URL**: `nami-api.178.104.181.132.nip.io` → `nami.178.104.181.132.nip.io` (SSL cert coverage)
- **App version**: 0.9.0 → 0.10.0

### Pending (requires SSH to VPS)

- Install Redis on VPS: `bash deploy/setup-production.sh` or `bash deploy/setup-redis.sh`
- Fix nginx: remove `auth_basic` for API endpoints (GET /health, /workers, /metrics, /docs, /ws)
- Verify Redis cache backend: `curl https://nami.178.104.181.132.nip.io/cache`

## 0.9.0 — 2026-05-06

### Changed

- **Dashboard code quality**: Replaced all ~40 inline CSS styles in `page.tsx` with CSS utility classes (`card`, `card-title`, `input-dark`, `btn-gold`, `btn-icon`, `chip`, etc.)
- **Accessibility**: Added `aria-label` and `title` attributes to `<select>`, `<button>`, `<input>`, `<textarea>` elements
- **CSS architecture**: Added 15+ utility classes to `globals.css` for consistent theming via CSS custom properties

## 0.8.0 — 2026-05-06

### Added
- **AI image worker**: `image_worker` — generate (text→image via DALL-E/OpenRouter), describe (image→text), models
- **Per-worker rate limits**: configurable via `NAMI_DISPATCH_RATE_LIMIT` env var (default 30/min per worker)
- **GET /workers/{name}/rate-limit**: view rate limit status per worker
- **SQLite async pool**: `nami_core.db` — aiosqlite with sync fallback, WAL mode, busy timeout
- **GET /db**: database pool statistics endpoint
- **Dashboard deploy script**: `deploy/dashboard-deploy.sh` — VPS systemd + nginx setup
- **Dashboard standalone output**: `next.config.ts` → `output: "standalone"` for production
- **CI/CD v3**: Redis service container for tests, dashboard build job, deploy depends on both test+dashboard
- **23 workers** total (up from 22): +image

### Changed
- App version bumped from 0.5.0 → 0.8.0
- Deploy job now depends on both `test` and `dashboard` CI jobs
- Release job now depends on both `test` and `dashboard` CI jobs

## 0.7.0 — 2026-05-06

### Added
- **Test coverage 100%**: 204 tests (up from 86) — worker, SDK, integration, production tests
- **AI workers**: ai_chat (chat/complete/summarize/translate), sentiment (analyze/batch), search (web/knowledge)
- **Production hardening**: Redis cache module with in-memory fallback, cache stats/flush endpoints
- **Graceful restart**: POST /restart — drains and restarts via SIGTERM
- **Hot-reload workers**: POST /reload-workers — rebuilds Hermes without restart
- **New API endpoints**: GET /cache, POST /cache/flush, POST /restart, POST /reload-workers
- **React dashboard**: Next.js 16 + TypeScript + Tailwind + Chart.js + Lucide icons
  - Real-time WebSocket status badge
  - Worker chips, dispatch latency chart, worker actions bar chart
  - Audit trail table, dispatch test panel, quick actions
  - Dark/light theme toggle, auto-refresh every 60s
- **build_core()**: Extracted shared setup function for reuse in tests and app
- **Harness configs**: ai_chat_harness.yaml, sentiment_harness.yaml, search_harness.yaml
- **22 workers** total (up from 19): +ai_chat, +sentiment, +search

### Fixed
- Module import issue: `import nami_workers.X` returns function not module — use `importlib.import_module` in tests and search_worker
- Auth status code: API returns 401 (not 403) for unauthorized requests
- Async SDK tests: use `asyncio.run()` instead of deprecated `get_event_loop()`

## 0.6.0 — 2026-05-06

### Added

- SDK v2: NamiAsyncClient (httpx-based), NamiWSListener (auto-reconnect WS)
- SDK new methods: audit(), rotate_key(), scheduler_run_now(), cron_schedule(), cron_list(), cron_cancel()
- Email worker: SMTP send, batch, templates
- Webhook relay worker: register, unregister, list, trigger external URLs
- Pipeline worker: transform, aggregate, export (JSON/CSV/summary)
- Locust load test script (deploy/locustfile.py)
- CI/CD v2: coverage report, health check on deploy, auto-release on tag push
- 19 workers total (was 16)

### Changed

- CI test matrix: Python 3.11 + 3.12 (dropped 3.13)
- Deploy script now runs pip install + health check

## 0.5.0 — 2026-05-06

### Added

- Rate limiting: 60 req/min on /dispatch, 120/min on GET (per-IP sliding window)
- Audit trail: SQLite-backed dispatch log (worker, action, caller IP, latency)
- API key rotation: POST /rotate-key (requires current key auth)
- Audit query: GET /audit (auth required)
- Request logging middleware: structured JSON per request
- CORS hardening: configurable via NAMI_CORS_ORIGINS env var
- Scheduler worker: list, enable, disable, run_now via dispatch
- Cron worker: schedule, cancel, list one-off delayed jobs (SQLite + background checker)
- Dashboard v2: dark/light mode toggle, WS status badge, Grafana iframe embed
- 16 workers total (was 14)

### Changed

- WebSocket URL updated to port 8092 (unified with HTTP)
- 86 tests passing (was 81)

## 0.4.0 — 2026-05-06

### Added

- FastAPI + uvicorn async server (replaces HTTPServer + ws.py)
- WebSocket endpoint at /ws (unified with HTTP on port 8092)
- Swagger UI at /docs, ReDoc at /redoc, OpenAPI spec at /openapi.json
- Prometheus text format at /metrics/prometheus
- Python SDK: `nami_sdk.client.NamiClient` (health, workers, dispatch, webhook, metrics)
- Notification worker: send/subscribe/unsubscribe (Telegram + webhook channels)
- Analytics worker: dispatch_log, summary, leaderboard, recent (SQLite-backed)
- Harness configs for notification + analytics workers
- `deploy/setup-monitoring.sh` — Prometheus + Grafana one-shot setup

### Changed

- HTTP server upgraded from BaseHTTPRequestHandler to FastAPI
- WebSocket merged into FastAPI (no separate port 8093)
- Integration tests use FastAPI TestClient (faster, no threading)
- 81 tests passing (was 79)

## 0.3.0 — 2026-05-06

### Added

- WebSocket server on port 8093 (`src/nami_core/ws.py`)
- Real-time broadcast: dispatch, webhook, scheduler events pushed to dashboard
- Dashboard WebSocket client with auto-reconnect + debounced refresh
- nginx `/ws` proxy with Upgrade headers for WSS
- Dashboard auth via nginx `auth_basic` (user: nami)
- `/metrics` endpoint also protected with auth_basic
- `deploy/setup_dashboard_auth.sh` — one-shot auth setup
- `deploy/setup-domain.sh` — one-shot permanent domain + SSL setup
- `deploy/nginx-nami-api.conf` — reference nginx config with WS proxy

## 0.2.0 — 2026-05-06

### Added
- `GET /metrics` endpoint: request count, dispatch count, errors, avg/p95 latency
- `POST /webhook` endpoint: external event ingestion (source, event, data)
- Dispatch latency tracking with rolling 100-sample window
- `gateway_worker.agent_route` action: AI agent routing (migrated from agent-wrappers)
- `gateway_worker` routes: `/api/gold`, `/api/miroshark`, `/api/graphify`
- `graphify_worker.load_graphs` + `list_graphs`: VFS graph data loading
- Dashboard: Hanoi Lottery card, Paper Trading card, API Metrics card, Dispatch Test panel
- Dashboard: Mobile responsive CSS (@media max-width 640px)
- CI/CD: Auto-deploy to VPS on master push with restart verification
- nami-bot: `nami_core` in PROJECTS, `/logs nami-core`, `/restart nami-core`
- Secrets: symlinked laopatana-stat-lab.env + hanoi-stats-analyzer.env into /etc/nami-harness/

### Changed
- CI/CD deploy step now does real restart instead of shadow mode
- `/dispatch` response includes `latency_ms` field

### Removed
- Unused /opt/ directories: nami-audit-backups, nami-harness-backups, ecosystem-dashboard

## 0.1.0 — 2026-05-06

### Added
- Scheduler daemon with 6 periodic jobs
- HTTP API on port 8092 (GET /health, /workers, /scheduler; POST /dispatch)
- 12 workers: lottery, signal, status, proxy, trading, gateway, bridge, graphify, bot, miroshark, gold, default
- API key auth on POST /dispatch via NAMI_API_KEY
- CORS support (OPTIONS handler)
- Unified dashboard at /dashboard.html
- nami-bot /vip, /status, /health, /agents routed through nami-core API
- hanoi-bot fetch_results routed through nami-core API
- MiroShark Oracle → miroshark_worker
- Gold Signal OS → gold_worker
- maxplus-proxy → proxy_worker primary LLM provider
- Cron cleanup: 28 → 8 entries
- nginx reverse proxy with SSL for nami-api subdomain

## 0.0.1 — 2026-05-05

Nami Core: unified agentic system with Hermes brain, Harness control, and 9 worker plugins.

### Added — Phase 0: Foundation

- `nami_core/hermes.py` — Task router and dispatcher
- `nami_core/config.py` — YAML harness config loader → HarnessRuntime builder
- `nami_core/secrets.py` — Secure secret loading from /etc/nami-harness
- `nami_core/db.py` — PostgreSQL connection pool
- `nami_core/main.py` — Main entry point
- `nami_core/worker.py` — Single-worker runner for systemd template units
- `nami_workers/registry.py` — Worker plugin registry with auto-discovery
- 10 harness YAML configs (signal, proxy, lottery, trading, bot, gateway, status, bridge, graphify, default)
- Deploy scripts (systemd units, nginx config, install.sh with --shadow mode)
- VPS migration script (migrate-vps.sh)
- Migration guide (docs/migration-guide.md)
- GitHub issue/PR templates

### Added — Phase 1: Workers

- `signal_worker` — Gold/AI signal generation + Telegram delivery
- `proxy_worker` — LLM API proxy with multi-provider fallback
- `lottery_worker` — Hanoi + Lao lottery AI prediction (shared)
- `bot_worker` — General Telegram bot commands
- `trading_worker` — Gold Signal OS paper trading
- `gateway_worker` — Unified REST API routing
- `status_worker` — Health checks
- `bridge_worker` — WebSocket relay
- `graphify_worker` — Knowledge Graph API

### Inherited from nami-harness v0.1.0

- Rails policy primitive
- Rate limit rail
- File kill switch
- Circuit breaker
- Budget guard
- JSONL sensor with stable schema
- Quality gate
- Integrated harness runtime
- Hermes pipeline demo
- 65 tests passing
