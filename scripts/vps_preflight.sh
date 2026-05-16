#!/usr/bin/env bash
# Nami OS T1 — VPS preflight
# Companion to VPS_CUTOVER.md. Run on the VPS as root.
# Strictly read-only checks + idempotent installs. Does NOT apply migrations
# (that's still a manual step in §5 of VPS_CUTOVER.md).
#
# Usage:
#   sudo bash scripts/vps_preflight.sh
#   sudo NAMI_PREFLIGHT_INSTALL=1 bash scripts/vps_preflight.sh   # also runs apt + pip
#
# Exit codes:
#   0  every gate green
#   1  at least one gate failed (details printed)

set -u

PASS=0
FAIL=0
WARN=0

ok()    { printf '  [ok ] %s\n' "$1"; PASS=$((PASS + 1)); }
fail()  { printf '  [FAIL] %s\n' "$1"; FAIL=$((FAIL + 1)); }
warn()  { printf '  [warn] %s\n' "$1"; WARN=$((WARN + 1)); }
banner(){ printf '\n=== %s ===\n' "$1"; }

NAMI_DB="${NAMI_DB:-glodbyproza}"
NAMI_REDIS_URL="${NAMI_REDIS_URL:-redis://127.0.0.1:6379/0}"
NAMI_HEALTH_URL="${NAMI_HEALTH_URL:-http://127.0.0.1:8092/runtime/health}"
NAMI_METRICS_URL="${NAMI_METRICS_URL:-http://127.0.0.1:8092/metrics/prometheus}"
NAMI_CURRENT="${NAMI_CURRENT:-/opt/nami/current}"

# ── §1 system packages ────────────────────────────────────────────────
banner "system packages"
if [ "${NAMI_PREFLIGHT_INSTALL:-0}" = "1" ]; then
  apt-get update -qq && apt-get install -y -qq tmux git bubblewrap age >/dev/null
fi
for bin in tmux bwrap age git; do
  command -v "$bin" >/dev/null 2>&1 && ok "$bin present" || fail "$bin missing (apt install $bin)"
done

# ── §2 python deps ────────────────────────────────────────────────────
banner "python deps"
if [ -f "$NAMI_CURRENT/.venv/bin/python" ]; then
  PY="$NAMI_CURRENT/.venv/bin/python"
  ok "venv at $NAMI_CURRENT/.venv"
else
  PY="$(command -v python3 || true)"
  warn "venv not at $NAMI_CURRENT/.venv — using system python3"
fi
if [ -n "${PY:-}" ]; then
  for mod in libtmux psycopg redis; do
    "$PY" -c "import $mod" 2>/dev/null && ok "$mod importable" || fail "$mod missing (pip install $mod)"
  done
else
  fail "no python interpreter found"
fi

# ── §3 backup key ────────────────────────────────────────────────────
banner "backup key (age)"
if [ -f /etc/nami-harness/backup.age.key ]; then
  perm=$(stat -c '%a' /etc/nami-harness/backup.age.key 2>/dev/null || echo "?")
  [ "$perm" = "400" ] && ok "backup.age.key present, mode 400" \
    || fail "backup.age.key mode is $perm (want 400 — chmod 400)"
else
  warn "backup.age.key not present — VPS_CUTOVER §3 not yet run"
fi
[ -f /etc/nami-harness/backup.age.pub ] && ok "backup.age.pub present" \
  || warn "backup.age.pub missing (still ok for read-only preflight)"

# ── §4 postgres + pgvector ───────────────────────────────────────────
banner "postgres + pgvector"
if command -v pg_isready >/dev/null 2>&1; then
  pg_isready -q && ok "postgres accepting connections" || fail "pg_isready failed"
else
  warn "pg_isready not installed (postgresql-client missing)"
fi
if command -v psql >/dev/null 2>&1; then
  EXTV=$(sudo -u postgres psql -d "$NAMI_DB" -tAc \
        "SELECT extversion FROM pg_extension WHERE extname='vector'" 2>/dev/null || true)
  if [ -n "$EXTV" ]; then
    ok "pgvector $EXTV installed in $NAMI_DB"
  else
    fail "pgvector not installed in $NAMI_DB (CREATE EXTENSION vector;)"
  fi
  for tbl in agent_traces mcp_calls agent_episodes embeddings; do
    EXISTS=$(sudo -u postgres psql -d "$NAMI_DB" -tAc \
            "SELECT 1 FROM information_schema.tables WHERE table_name='$tbl'" 2>/dev/null || true)
    [ "$EXISTS" = "1" ] && ok "table $tbl exists" || fail "table $tbl missing (apply migrations)"
  done
else
  warn "psql not installed; skipping schema checks"
fi

# ── §5 redis ─────────────────────────────────────────────────────────
banner "redis"
if command -v redis-cli >/dev/null 2>&1; then
  PONG=$(redis-cli -u "$NAMI_REDIS_URL" PING 2>/dev/null || true)
  [ "$PONG" = "PONG" ] && ok "redis PING -> PONG" || fail "redis PING failed"
  DLQ=$(redis-cli -u "$NAMI_REDIS_URL" XLEN nami:jobs:dead 2>/dev/null || echo "?")
  if [ "$DLQ" = "?" ]; then
    warn "could not read XLEN nami:jobs:dead"
  elif [ "$DLQ" -gt 50 ]; then
    fail "DLQ length $DLQ > 50 (D14 threshold; investigate before cutover)"
  else
    ok "DLQ length $DLQ (<= 50, D14 silent)"
  fi
else
  warn "redis-cli not installed; skipping redis checks"
fi

# ── §6 reconciler timer ─────────────────────────────────────────────
banner "reconciler timer"
if systemctl list-timers --all 2>/dev/null | grep -q nami-reconciler; then
  STATE=$(systemctl is-enabled nami-reconciler.timer 2>/dev/null || echo unknown)
  ok "nami-reconciler.timer registered ($STATE)"
  systemctl is-active --quiet nami-reconciler.timer && ok "timer active" \
    || warn "timer not active (systemctl enable --now nami-reconciler.timer)"
else
  warn "nami-reconciler.timer not registered (cp deploy/systemd/* /etc/systemd/system/)"
fi

# ── §7 inference gateway / runtime health ────────────────────────────
banner "runtime health"
if command -v curl >/dev/null 2>&1; then
  HEALTH=$(curl -fsS --max-time 5 "$NAMI_HEALTH_URL" 2>/dev/null || true)
  if [ -n "$HEALTH" ]; then
    ok "$NAMI_HEALTH_URL responded"
    echo "$HEALTH" | grep -q '"dlq"' && ok "health JSON includes dlq field (D14 wired)" \
      || warn "health JSON missing dlq field (Phase 33 not deployed?)"
  else
    fail "no response from $NAMI_HEALTH_URL"
  fi
else
  warn "curl not installed; skipping health probe"
fi

# ── §8 prometheus metrics exposure ───────────────────────────────────
banner "prometheus metrics"
if command -v curl >/dev/null 2>&1; then
  METRICS=$(curl -fsS --max-time 5 "$NAMI_METRICS_URL" 2>/dev/null || true)
  if [ -n "$METRICS" ]; then
    echo "$METRICS" | grep -q 'nami_safety_detection_total' \
      && ok "nami_safety_detection_total exposed" \
      || fail "nami_safety_detection_total missing from /metrics/prometheus"
    echo "$METRICS" | grep -q 'nami_cost_usd_total' \
      && ok "nami_cost_usd_total exposed" \
      || fail "nami_cost_usd_total missing from /metrics/prometheus"
  else
    fail "no response from $NAMI_METRICS_URL"
  fi
fi

# ── §9 smoke script availability ─────────────────────────────────────
banner "smoke script"
if [ -x "$NAMI_CURRENT/scripts/smoke.sh" ]; then
  ok "scripts/smoke.sh executable"
else
  warn "scripts/smoke.sh not executable at $NAMI_CURRENT/scripts/smoke.sh"
fi

# ── summary ──────────────────────────────────────────────────────────
banner "summary"
printf '  pass=%d  fail=%d  warn=%d\n' "$PASS" "$FAIL" "$WARN"
if [ "$FAIL" -gt 0 ]; then
  printf '\nPREFLIGHT FAILED — fix the [FAIL] lines above before cutover.\n'
  exit 1
fi
printf '\nPREFLIGHT GREEN — proceed to VPS_CUTOVER.md §5 (apply migrations).\n'
exit 0
