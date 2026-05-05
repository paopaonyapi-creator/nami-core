# Changelog

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
