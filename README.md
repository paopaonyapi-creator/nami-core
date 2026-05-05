# Nami Core

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

## Test Results

```
69 passed in 8.57s
```

## Status

Phase 0+1+2+3+4 complete. Workers have real integration code (Telegram, AI, OANDA).
Next: Deploy to VPS in shadow mode and extract remaining service-specific logic.

## License

MIT
