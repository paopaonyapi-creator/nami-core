#!/usr/bin/env bash
# Nami OS T1 — VPS cutover (idempotent end-to-end)
# Run on the VPS as root from /opt/nami/current.
# Each step is safe to re-run; existing state is detected and skipped.
#
# Usage:
#   sudo bash scripts/vps_cutover.sh
#
# Env overrides (defaults match VPS_CUTOVER.md):
#   NAMI_DB=glodbyproza
#   NAMI_CURRENT=/opt/nami/current
#   NAMI_HARNESS_DIR=/etc/nami-harness
#   NAMI_PG_VERSION=16        # for postgresql-${ver}-pgvector
#   NAMI_SKIP_APT=0           # set 1 to skip apt-get install
#   NAMI_SKIP_PIP=0           # set 1 to skip pip install
#   NAMI_SKIP_KEYGEN=0        # set 1 if backup key already exists
#   NAMI_SKIP_TIMER=0         # set 1 to skip systemd timer enable
#   NAMI_SKIP_SMOKE=0         # set 1 to skip smoke.sh at the end

set -u

NAMI_DB="${NAMI_DB:-glodbyproza}"
NAMI_CURRENT="${NAMI_CURRENT:-/opt/nami/current}"
NAMI_HARNESS_DIR="${NAMI_HARNESS_DIR:-/etc/nami-harness}"
NAMI_PG_VERSION="${NAMI_PG_VERSION:-16}"

PASS=0
FAIL=0
SKIP=0

ok()    { printf '  [ok ] %s\n' "$1"; PASS=$((PASS + 1)); }
fail()  { printf '  [FAIL] %s\n' "$1"; FAIL=$((FAIL + 1)); }
skip()  { printf '  [skip] %s\n' "$1"; SKIP=$((SKIP + 1)); }
banner(){ printf '\n=== %s ===\n' "$1"; }
die()   { printf '\nABORTED: %s\n' "$1"; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  die "must run as root"
fi

if [ ! -d "$NAMI_CURRENT" ]; then
  die "$NAMI_CURRENT does not exist; deploy the symlink first"
fi
cd "$NAMI_CURRENT" || die "cd $NAMI_CURRENT failed"

# ── §1 system packages ────────────────────────────────────────────────
banner "§1 system packages"
if [ "${NAMI_SKIP_APT:-0}" = "1" ]; then
  skip "apt install (NAMI_SKIP_APT=1)"
else
  apt-get update -qq
  apt-get install -y -qq tmux git bubblewrap age postgresql-client \
    "postgresql-${NAMI_PG_VERSION}-pgvector" >/dev/null 2>&1 || true
  for bin in tmux bwrap age git psql; do
    command -v "$bin" >/dev/null 2>&1 \
      && ok "$bin installed" \
      || fail "$bin still missing after apt"
  done
fi

# ── §2 python packages ────────────────────────────────────────────────
banner "§2 python deps"
VENV="$NAMI_CURRENT/.venv"
if [ ! -d "$VENV" ]; then
  fail "$VENV missing — deploy must create the venv first"
else
  PY="$VENV/bin/python"
  PIP="$VENV/bin/pip"
  if [ "${NAMI_SKIP_PIP:-0}" = "1" ]; then
    skip "pip install (NAMI_SKIP_PIP=1)"
  else
    "$PIP" install --quiet --upgrade libtmux 'psycopg[binary]' redis
  fi
  for mod in libtmux psycopg redis; do
    "$PY" -c "import $mod" 2>/dev/null \
      && ok "$mod importable" \
      || fail "$mod import failed"
  done
fi

# ── §3 backup key (age) ───────────────────────────────────────────────
banner "§3 backup key"
mkdir -p "$NAMI_HARNESS_DIR"
chmod 700 "$NAMI_HARNESS_DIR"
KEY="$NAMI_HARNESS_DIR/backup.age.key"
PUB="$NAMI_HARNESS_DIR/backup.age.pub"

if [ -f "$KEY" ]; then
  ok "backup key already exists at $KEY (preserved)"
elif [ "${NAMI_SKIP_KEYGEN:-0}" = "1" ]; then
  skip "key generation (NAMI_SKIP_KEYGEN=1)"
elif command -v age-keygen >/dev/null 2>&1; then
  age-keygen -o "$KEY" 2>"$PUB"
  chmod 400 "$KEY"
  chmod 444 "$PUB"
  chown root:root "$KEY" "$PUB"
  ok "generated $KEY + $PUB"
  printf '\n  ⚠ Public key (copy to Bitwarden + USB):\n'
  printf '    %s\n' "$(cat "$PUB")"
else
  fail "age-keygen not available"
fi

if [ -f "$KEY" ]; then
  perm=$(stat -c '%a' "$KEY")
  [ "$perm" = "400" ] && ok "key mode 400" || fail "key mode is $perm (chmod 400 $KEY)"
fi

# ── §4 pgvector + migrations ─────────────────────────────────────────
banner "§4 postgres + pgvector + migrations"
if ! command -v psql >/dev/null 2>&1; then
  fail "psql not available; cannot apply migrations"
else
  pg_isready -q && ok "postgres accepting connections" || fail "pg_isready failed"

  EXTV=$(sudo -u postgres psql -d "$NAMI_DB" -tAc \
        "SELECT extversion FROM pg_extension WHERE extname='vector'" 2>/dev/null || true)
  if [ -z "$EXTV" ]; then
    sudo -u postgres psql -d "$NAMI_DB" -v ON_ERROR_STOP=1 \
      -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null \
      && ok "pgvector extension created" \
      || fail "CREATE EXTENSION vector failed"
    EXTV=$(sudo -u postgres psql -d "$NAMI_DB" -tAc \
          "SELECT extversion FROM pg_extension WHERE extname='vector'" 2>/dev/null || true)
  fi
  [ -n "$EXTV" ] && ok "pgvector $EXTV active in $NAMI_DB"

  for f in migrations/0003_agent_traces.sql \
           migrations/0004_mcp_calls.sql \
           migrations/0005_pgvector_ext.sql \
           migrations/0006_memory_tables.sql; do
    if [ ! -f "$f" ]; then
      fail "$f missing in $NAMI_CURRENT"
      continue
    fi
    sudo -u postgres psql -d "$NAMI_DB" -v ON_ERROR_STOP=1 -f "$f" >/dev/null 2>&1 \
      && ok "applied $f (idempotent)" \
      || fail "psql -f $f failed"
  done

  for tbl in agent_traces mcp_calls agent_episodes embeddings; do
    EXISTS=$(sudo -u postgres psql -d "$NAMI_DB" -tAc \
            "SELECT 1 FROM information_schema.tables WHERE table_name='$tbl'" 2>/dev/null)
    [ "$EXISTS" = "1" ] && ok "table $tbl exists" || fail "table $tbl missing"
  done
fi

# ── §5 reconciler timer ───────────────────────────────────────────────
banner "§5 reconciler timer"
if [ "${NAMI_SKIP_TIMER:-0}" = "1" ]; then
  skip "systemd timer setup (NAMI_SKIP_TIMER=1)"
elif [ ! -f deploy/systemd/nami-reconciler.timer ]; then
  fail "deploy/systemd/nami-reconciler.timer not found in repo"
else
  cp -u deploy/systemd/nami-reconciler.service /etc/systemd/system/ \
    && ok "service unit copied"
  cp -u deploy/systemd/nami-reconciler.timer /etc/systemd/system/ \
    && ok "timer unit copied"
  systemctl daemon-reload
  systemctl enable --now nami-reconciler.timer >/dev/null 2>&1 \
    && ok "nami-reconciler.timer enabled + active" \
    || fail "systemctl enable nami-reconciler.timer failed"
fi

# ── §6 smoke ─────────────────────────────────────────────────────────
banner "§6 smoke"
if [ "${NAMI_SKIP_SMOKE:-0}" = "1" ]; then
  skip "smoke.sh (NAMI_SKIP_SMOKE=1)"
elif [ -x "$NAMI_CURRENT/scripts/smoke.sh" ]; then
  if NAMI_SMOKE_HEALTH_URL="${NAMI_SMOKE_HEALTH_URL:-http://127.0.0.1:8092/runtime/health}" \
     NAMI_SMOKE_SERVICES="${NAMI_SMOKE_SERVICES:-nami-core nami-worker@lottery}" \
     bash "$NAMI_CURRENT/scripts/smoke.sh" >/tmp/nami-smoke.log 2>&1; then
    ok "smoke.sh passed"
  else
    fail "smoke.sh failed (see /tmp/nami-smoke.log)"
  fi
else
  fail "scripts/smoke.sh not executable"
fi

# ── §7 incidents log ──────────────────────────────────────────────────
banner "§7 incidents log"
if [ "$FAIL" -eq 0 ]; then
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf -- "- %s CUTOVER T1 — migrations 0003-0006 applied, deps installed, reconciler enabled, smoke green\n" "$ts" \
    >> "$NAMI_CURRENT/incidents.md" 2>/dev/null \
    && ok "appended to incidents.md" \
    || skip "incidents.md not writable"
fi

# ── summary ──────────────────────────────────────────────────────────
banner "summary"
printf '  pass=%d  fail=%d  skip=%d\n' "$PASS" "$FAIL" "$SKIP"
if [ "$FAIL" -gt 0 ]; then
  printf '\nCUTOVER FAILED — fix [FAIL] lines and re-run (idempotent).\n'
  exit 1
fi
printf '\nCUTOVER GREEN — T1 operationally live. Next: first agent.run dispatch.\n'
exit 0
