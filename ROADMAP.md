# Nami Core Roadmap

## Current: v0.0.1 — Foundation + Workers

- [x] Hermes task router and dispatcher
- [x] YAML harness config loader → HarnessRuntime builder
- [x] Secure secret loading from /etc/nami-harness
- [x] PostgreSQL connection pool
- [x] Worker plugin registry with auto-discovery
- [x] 9 workers with placeholder logic (signal, proxy, lottery, bot, trading, gateway, status, bridge, graphify)
- [x] 10 harness YAML configs
- [x] Deploy scripts (systemd, nginx, install.sh)
- [x] 65 tests passing

## Next: v0.1.0 — Real Logic Migration

- [ ] Extract real signal logic from /opt/telegram-premium-bot → signal_worker
- [ ] Extract real proxy logic from /opt/maxplus-proxy/proxy.py → proxy_worker
- [ ] Merge hanoi-bot + laopatana → lottery_worker (shared prediction engine)
- [ ] Extract nami-bot commands → bot_worker
- [ ] Extract gold-signal-os → trading_worker
- [ ] Extract nami-api-gateway → gateway_worker
- [ ] Extract nami-status-api → status_worker
- [ ] Extract nami-bridge → bridge_worker
- [ ] Extract graphify-http → graphify_worker
- [ ] Shadow mode deployment alongside existing services
- [ ] 3-day comparison verification per worker

## Future: v0.2.0 — Unified Service

- [ ] Single nami-core.service replaces all 10 systemd units
- [ ] Unified sensor log (single JSONL for all workers)
- [ ] Unified nginx config
- [ ] Remove old /opt/* service directories
- [ ] Health dashboard
- [ ] Per-worker kill switch tested in production

## Future: v0.3.0 — OSS Release

- [ ] Public GitHub repo
- [ ] Demo video
- [ ] Documentation site
- [ ] Community templates
- [ ] Plugin API for third-party workers
