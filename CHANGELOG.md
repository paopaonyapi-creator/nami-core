# Changelog

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
