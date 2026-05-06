# Changelog

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
