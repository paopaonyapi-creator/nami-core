#!/usr/bin/env bash
# Phase 30 — backup pipeline (Postgres + Redis + /opt/nami).
# Outputs an age-encrypted tarball; uploads to Backblaze B2 if rclone configured.
#
# Required env:
#   NAMI_BACKUP_DIR         where to write the tarball (default /var/nami/backups)
#   NAMI_AGE_PUBKEY_FILE    age recipient public key file (chmod 444)
#                           OR NAMI_AGE_PUBKEY (literal recipient string)
#   NAMI_JOBS_DB            Postgres database name (default glodbyproza)
#
# Optional:
#   NAMI_BACKUP_ROOT        what to tar (default /opt/nami)
#   NAMI_B2_REMOTE          rclone remote name (e.g. "b2:nami-backups")
#   NAMI_BACKUP_RETAIN_DAYS prune local files older than N days (default 14)
#
# Failure modes documented in NAMI_OS_OPERATIONS.md §6 (backup).
set -euo pipefail

BACKUP_DIR="${NAMI_BACKUP_DIR:-/var/nami/backups}"
BACKUP_ROOT="${NAMI_BACKUP_ROOT:-/opt/nami}"
DBNAME="${NAMI_JOBS_DB:-glodbyproza}"
RETAIN_DAYS="${NAMI_BACKUP_RETAIN_DAYS:-14}"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
work_dir="$(mktemp -d -t nami-backup-XXXXXX)"
trap 'rm -rf "$work_dir"' EXIT

mkdir -p "$BACKUP_DIR"

log() { printf -- "[backup] %s\n" "$*"; }
log "writing to $work_dir; final dir=$BACKUP_DIR"

# ── 1. Postgres dump ──────────────────────────────────────────────────
if command -v pg_dump > /dev/null 2>&1; then
  log "pg_dump $DBNAME"
  pg_dump --format=custom --compress=9 --file="$work_dir/db-$DBNAME.dump" "$DBNAME"
else
  echo "pg_dump missing; aborting" >&2
  exit 2
fi

# ── 2. Redis BGSAVE snapshot copy ─────────────────────────────────────
if command -v redis-cli > /dev/null 2>&1; then
  log "redis BGSAVE"
  redis-cli BGSAVE > /dev/null
  # Wait up to 60s for BGSAVE to finish.
  for _ in $(seq 1 60); do
    state="$(redis-cli LASTSAVE 2>/dev/null || echo 0)"
    sleep 1
    new_state="$(redis-cli LASTSAVE 2>/dev/null || echo 0)"
    if [[ "$new_state" != "$state" ]]; then
      break
    fi
  done
  rdb_path="$(redis-cli CONFIG GET dir 2>/dev/null | tail -n1)/$(redis-cli CONFIG GET dbfilename 2>/dev/null | tail -n1)"
  if [[ -f "$rdb_path" ]]; then
    cp "$rdb_path" "$work_dir/redis.rdb"
  else
    log "WARN: redis dump file not found at $rdb_path; skipping"
  fi
else
  log "redis-cli missing; skipping redis snapshot"
fi

# ── 3. /opt/nami filesystem tar ───────────────────────────────────────
if [[ -d "$BACKUP_ROOT" ]]; then
  log "tar $BACKUP_ROOT"
  tar --warning=no-file-changed --exclude='*.log' --exclude='__pycache__' \
      -czf "$work_dir/fs-$(basename "$BACKUP_ROOT").tar.gz" \
      -C "$(dirname "$BACKUP_ROOT")" "$(basename "$BACKUP_ROOT")"
fi

# ── 4. Bundle + age encrypt ───────────────────────────────────────────
bundle="$work_dir/bundle.tar"
tar -cf "$bundle" -C "$work_dir" .
out="$BACKUP_DIR/nami-$ts.tar.age"

recipient_args=()
if [[ -n "${NAMI_AGE_PUBKEY_FILE:-}" ]]; then
  recipient_args+=(-R "$NAMI_AGE_PUBKEY_FILE")
elif [[ -n "${NAMI_AGE_PUBKEY:-}" ]]; then
  recipient_args+=(-r "$NAMI_AGE_PUBKEY")
else
  echo "NAMI_AGE_PUBKEY_FILE or NAMI_AGE_PUBKEY required" >&2
  exit 2
fi

if ! command -v age > /dev/null 2>&1; then
  echo "age missing; install via apt-get install age" >&2
  exit 2
fi

log "age encrypt -> $out"
age "${recipient_args[@]}" -o "$out" "$bundle"
chmod 400 "$out"
log "wrote $out ($(stat -c %s "$out" 2>/dev/null || stat -f %z "$out") bytes)"

# ── 5. Optional remote upload ─────────────────────────────────────────
if [[ -n "${NAMI_B2_REMOTE:-}" ]] && command -v rclone > /dev/null 2>&1; then
  log "rclone copy -> $NAMI_B2_REMOTE"
  rclone copy "$out" "$NAMI_B2_REMOTE" --no-traverse --transfers=2
fi

# ── 6. Local retention ────────────────────────────────────────────────
log "pruning local backups older than $RETAIN_DAYS days"
find "$BACKUP_DIR" -type f -name 'nami-*.tar.age' -mtime "+$RETAIN_DAYS" -delete

log "backup complete"
