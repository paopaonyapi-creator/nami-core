# Nami Core

![Nami Core Dashboard](docs/img/dashboard-overview.png)

Unified agentic system: **Hermes brain** + **Harness control** + **9 worker plugins**.

## Core Model

```text
Hermes = brain / agentic workforce
Nami Harness = rails / brakes / sensors / quality system
Nami Workers = pluggable task handlers, each harnessed
```

## Architecture

```text
User / Task request
  → Hermes plans and routes
  → Harness rails authorize scope
  → Worker executes task
  → Harness quality validates output
  → Harness sensors record trace
  → Harness brakes can stop execution
  → result shipped only if quality passes
```

## Workers

| Worker | Source Service | Description |
|---|---|---|
| `signal_worker` | telegram-premium-bot | AI gold/market signal generation + Telegram delivery |
| `proxy_worker` | maxplus-proxy | LLM API proxy with multi-provider fallback |
| `lottery_worker` | hanoi-bot + laopatana | Hanoi/Lao lottery AI prediction (shared engine) |
| `bot_worker` | nami-bot | General Telegram bot commands (help, packages, subscribe) |
| `trading_worker` | gold-signal-os | TradingView signal analysis + OANDA paper trading |
| `gateway_worker` | nami-api-gateway | Unified REST API routing |
| `status_worker` | nami-status-api | Health checks and service monitoring |
| `bridge_worker` | nami-bridge | WebSocket relay for real-time updates |
| `graphify_worker` | graphify-http | Knowledge Graph API for code intelligence |

## Shared Utilities (`nami_workers/utils.py`)

- **`telegram_send(chat_id, text)`** — Send messages via Telegram Bot API (token from `/etc/nami-harness/telegram_bot_token`)
- **`ai_chat_completion(messages, model)`** — Call AI via maxplus-proxy → OpenRouter fallback (config from `/etc/nami-harness/ai_config.json`)
- **`oanda_paper_trade(instrument, units, direction)`** — Place paper trades via OANDA practice API (config from `/etc/nami-harness/oanda.env`)

## Quality Gates

Every worker output is validated before shipping:

- `signal_worker`: Blocks "guarantee", "แน่นอน", "100%", "การันตีกำไร"
- `lottery_worker`: Blocks guarantee terms
- `trading_worker`: Requires `signal` + `risk_level`
- `proxy_worker`: Blocks `raw_secret`, `api_key=`
- All workers: Require non-empty output fields

## Packages

- `nami_harness` — Rails, brakes, sensors, quality, runtime (v0.1.0)
- `nami_core` — Hermes router, YAML config loader, secrets, database
- `nami_workers` — 9 workers + shared utils + plugin registry

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows
pip install -e ".[dev]"
pytest
```

## Demo

```bash
python examples/nami_core_full_demo.py
```

## Deploy to VPS

**One-shot setup:**
```bash
# On VPS
git clone https://github.com/paopaonyapi-creator/nami-core.git /opt/nami-core
cd /opt/nami-core && bash deploy/vps-setup.sh --shadow
```

**Remote deploy (from any machine with SSH access):**
```bash
bash deploy/remote-deploy.sh --shadow
```

**CI/CD:** Push to `master` triggers GitHub Actions → test → auto-deploy to VPS.

## Configuration

Each worker has a YAML harness config in `config/`:

```yaml
# config/signal_harness.yaml
name: signal
allowed_agents: [hermes]
allowed_actions: [generate_signal, send_signal, send_dm]
quality:
  require_non_empty: [signal, reason]
  forbid_terms: [guarantee, แน่นอน, "100%", การันตีกำไร]
```

Secrets are loaded from `/etc/nami-harness/` (root-only 700/600).

Runtime diagnostics can be controlled with `NAMI_RUNTIME_DIAGNOSTIC_CHECKS`:

- `runtime_pytest,dashboard_build` — default; runs Runtime API pytest and dashboard production build when project files are present.
- `runtime_pytest` — Python Runtime API verification only.
- `dashboard_build` — dashboard production build only.
- `none` — disables automatic diagnostics after approved mutating runtime tools.

Environment-specific diagnostics policies can be set with `NAMI_RUNTIME_ENV` and `NAMI_RUNTIME_DIAGNOSTIC_POLICY_<ENV>`. `NAMI_RUNTIME_DIAGNOSTIC_CHECKS` remains the highest-priority override.

## Test Results

```
225 passed in 37.66s
```

## Status

**Current version: v0.13.0** (2026-05-06)

Shipped highlights:
- FastAPI server with batch dispatch, SSE streaming, webhook HMAC signing
- Redis pub/sub with in-process fallback
- 23 plugin workers (signal, proxy, lottery, bot, trading, gateway, status,
  bridge, graphify, ai_chat, sentiment, search, image, email, relay,
  pipeline, scheduler, cron, notification, analytics, default + 2 utility)
- Per-worker rate limit visibility (`GET /workers/{name}/rate-limit`)
- Per-worker health checks (`GET /workers/{name}/health`)
- Hot-reload (`POST /reload-workers`) and graceful restart (`POST /restart`)
- Audit trail (SQLite) and Prometheus metrics
- TypeScript SDK + Next.js dashboard with interactive `/docs` page
- Dashboard auto-deployed to Netlify
- 225 tests in CI

Next: Deploy v0.13.0 to VPS in shadow mode (Redis install + nginx fix pending).
See `CHANGELOG.md` for the full per-version log.

## License

MIT
