#!/usr/bin/env bash
# Phase 30 — post-deploy smoke test (5 checks).
# Exit 0 → all green; exit 1 → any check fails.
# Called by deploy.sh after symlink-swap; auto-rollback fires on non-zero.
#
# Override URLs/services via env if needed:
#   NAMI_SMOKE_HEALTH_URL    default http://127.0.0.1:8092/runtime/health
#   NAMI_SMOKE_DISPATCH_URL  default http://127.0.0.1:8092/runtime/health (cheap)
#   NAMI_SMOKE_SERVICES      default "nami-core nami-worker"
#   NAMI_SMOKE_TIMEOUT       default 10 (curl seconds)
set -euo pipefail

HEALTH_URL="${NAMI_SMOKE_HEALTH_URL:-http://127.0.0.1:8092/runtime/health}"
DISPATCH_URL="${NAMI_SMOKE_DISPATCH_URL:-$HEALTH_URL}"
SERVICES="${NAMI_SMOKE_SERVICES:-nami-core nami-worker}"
TIMEOUT="${NAMI_SMOKE_TIMEOUT:-10}"

failures=0
log() { printf -- "[smoke] %s\n" "$*"; }
fail() { log "FAIL: $*"; failures=$((failures + 1)); }

# 1. Health endpoint reachable
log "1/5 health"
if ! curl --max-time "$TIMEOUT" -fsS "$HEALTH_URL" > /tmp/nami-smoke-health.json; then
  fail "health endpoint unreachable: $HEALTH_URL"
fi

# 2. Dispatch endpoint reachable
log "2/5 dispatch"
if ! curl --max-time "$TIMEOUT" -fsS "$DISPATCH_URL" > /dev/null; then
  fail "dispatch endpoint unreachable: $DISPATCH_URL"
fi

# 3. systemd services active (skipped if not on systemd host)
log "3/5 services"
if command -v systemctl > /dev/null 2>&1; then
  for svc in $SERVICES; do
    if ! systemctl is-active --quiet "$svc"; then
      fail "service not active: $svc"
    fi
  done
else
  log "systemctl not present; skipping service check"
fi

# 4. Redis reachable (via redis-cli if present)
log "4/5 redis"
if command -v redis-cli > /dev/null 2>&1; then
  if ! redis-cli ping > /dev/null 2>&1; then
    fail "redis-cli ping failed"
  fi
else
  log "redis-cli not present; skipping"
fi

# 5. Postgres reachable (via psql if NAMI_JOBS_DB set + psql present)
log "5/5 postgres"
if [[ -n "${NAMI_JOBS_DB:-}" ]] && command -v psql > /dev/null 2>&1; then
  if ! psql -d "$NAMI_JOBS_DB" -c "SELECT 1" > /dev/null 2>&1; then
    fail "psql connect failed: $NAMI_JOBS_DB"
  fi
else
  log "skipping (NAMI_JOBS_DB unset or psql missing)"
fi

if [[ "$failures" -gt 0 ]]; then
  log "$failures check(s) failed"
  exit 1
fi
log "all checks passed"
