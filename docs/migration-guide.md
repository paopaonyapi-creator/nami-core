# Migration Guide — From VPS Services to Nami Core Workers

## Overview

This guide explains how to migrate from the current 10+ independent services
running on the VPS to the unified Nami Core system.

## Current Architecture

```text
10 independent services, each with:
- Own systemd unit
- Own Python code in /opt/<service>/
- Own env file / secrets
- No shared harness (no rails, brakes, sensors, quality)
- No unified audit trail
```

## Target Architecture

```text
1 nami-core service with 9 workers, each wrapped by:
- HarnessRuntime (rails + brakes + sensors + quality)
- YAML config per worker
- Unified audit log
- Per-worker kill switch
```

## Migration Steps

### Step 1: Deploy Nami Core in Shadow Mode

```bash
# On VPS, from /opt/nami-core
bash deploy/install.sh --shadow
```

This installs Nami Core alongside existing services. Nothing is stopped.

### Step 2: Extract Real Logic

Run the migration discovery script:

```bash
bash deploy/migrate-vps.sh
```

This lists all Python files in each /opt/* service directory.
Then manually copy the relevant logic into each worker file:

| Source | Target Worker | What to Copy |
|---|---|---|
| `/opt/telegram-premium/bot.py` | `signal_worker.py` | Signal generation, AI call, Telegram send |
| `/opt/maxplus-proxy/proxy.py` | `proxy_worker.py` | Multi-provider fallback, API key rotation |
| `/opt/hanoi-bot/hanoi_bot.py` | `lottery_worker.py` | Prediction logic, KQXS scraper |
| `/opt/laopatana-stat-lab/` | `lottery_worker.py` | Lao prediction, shared with hanoi |
| `/opt/nami-bot/nami_bot.py` | `bot_worker.py` | Command handlers, help, status |
| `/opt/gold-signal-os/` | `trading_worker.py` | TradingView parsing, OANDA paper trade |
| `/opt/nami-api-gateway/` | `gateway_worker.py` | REST routes, auth middleware |
| `/opt/nami-status-api/` | `status_worker.py` | Health check endpoints |
| `/opt/nami-bridge/` | `bridge_worker.py` | WebSocket relay logic |
| `/opt/graphify-http/` | `graphify_worker.py` | Neo4j queries, code analysis |

### Step 3: Verify Tests

```bash
cd /opt/nami-core
pytest
```

All tests must pass before proceeding.

### Step 4: Shadow Mode Comparison

For each worker, run both old and new in parallel:

1. Send same input to both old service and new worker
2. Compare outputs
3. Log any differences
4. Continue for 3 days minimum

### Step 5: Switch Over

Once verified:

```bash
# Stop old service
systemctl stop telegram-premium-bot
systemctl disable telegram-premium-bot

# Enable nami-core worker
systemctl enable nami-worker@signal.service
systemctl start nami-worker@signal.service
```

Repeat for each worker, one at a time.

### Step 6: Cleanup

After all workers are switched:

```bash
# Remove old service directories (after backup)
# Remove old systemd units
# Consolidate nginx config
# Single health endpoint
```

## Safety Rules

- **Never stop a service until its replacement is verified**
- **Never modify /etc/nami-harness/** (secrets stay root-only)
- **Always backup before migration**
- **One worker at a time** — don't switch all at once
- **Keep old services available for rollback** for at least 7 days

## Rollback

If something goes wrong:

```bash
# Stop nami-core
systemctl stop nami-core
systemctl stop nami-worker@signal

# Re-enable old service
systemctl enable telegram-premium-bot
systemctl start telegram-premium-bot
```
