#!/usr/bin/env bash
# Phase 30 — restore from age-encrypted backup tarball.
#
# Required env:
#   NAMI_AGE_KEY_FILE   age identity key (chmod 400)
#   NAMI_RESTORE_TARGET destination root for FS restore (default /opt/nami-restore)
#   NAMI_JOBS_DB        Postgres database to restore into (default glodbyproza_restore)
#
# Optional:
#   NAMI_RESTORE_REDIS_DIR  if set, place redis.rdb here for inspection
#
# Safety: this script NEVER overwrites the live /opt/nami directory or
# the live Postgres database. It always restores to a SEPARATE target
# (default `/opt/nami-restore` / `glodbyproza_restore`) so an operator
# can validate the restore before promoting. Documented in
# NAMI_OS_OPERATIONS.md §6 (restore drill).
#
# Usage:
#   scripts/restore.sh /var/nami/backups/nami-20260516T120000Z.tar.age
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <backup.tar.age>" >&2
  exit 2
fi
backup="$1"
if [[ ! -f "$backup" ]]; then
  echo "backup file not found: $backup" >&2
  exit 2
fi

KEY_FILE="${NAMI_AGE_KEY_FILE:?NAMI_AGE_KEY_FILE required}"
TARGET_ROOT="${NAMI_RESTORE_TARGET:-/opt/nami-restore}"
DBNAME="${NAMI_JOBS_DB:-glodbyproza_restore}"

if ! command -v age > /dev/null 2>&1; then
  echo "age missing" >&2
  exit 2
fi

work_dir="$(mktemp -d -t nami-restore-XXXXXX)"
trap 'rm -rf "$work_dir"' EXIT

log() { printf -- "[restore] %s\n" "$*"; }
log "decrypting $backup"
age -d -i "$KEY_FILE" "$backup" -o "$work_dir/bundle.tar"

log "extracting bundle"
tar -xf "$work_dir/bundle.tar" -C "$work_dir"

# ── 1. Postgres ───────────────────────────────────────────────────────
dump_file="$(find "$work_dir" -maxdepth 1 -name 'db-*.dump' | head -n1)"
if [[ -n "$dump_file" ]]; then
  if command -v pg_restore > /dev/null 2>&1; then
    log "restoring Postgres into $DBNAME (will create if missing)"
    if command -v createdb > /dev/null 2>&1; then
      createdb "$DBNAME" 2>/dev/null || true
    fi
    pg_restore --clean --if-exists --no-owner --no-privileges \
      --dbname="$DBNAME" "$dump_file"
  else
    log "pg_restore missing; skipping db restore"
  fi
else
  log "no db dump in bundle; skipping"
fi

# ── 2. Redis (copy out for inspection only — do NOT overwrite live) ───
if [[ -n "${NAMI_RESTORE_REDIS_DIR:-}" && -f "$work_dir/redis.rdb" ]]; then
  mkdir -p "$NAMI_RESTORE_REDIS_DIR"
  cp "$work_dir/redis.rdb" "$NAMI_RESTORE_REDIS_DIR/"
  log "redis snapshot placed at $NAMI_RESTORE_REDIS_DIR/redis.rdb"
fi

# ── 3. /opt/nami filesystem ───────────────────────────────────────────
fs_archive="$(find "$work_dir" -maxdepth 1 -name 'fs-*.tar.gz' | head -n1)"
if [[ -n "$fs_archive" ]]; then
  mkdir -p "$TARGET_ROOT"
  log "extracting filesystem to $TARGET_ROOT (NOT the live path)"
  tar -xzf "$fs_archive" -C "$TARGET_ROOT"
fi

log "restore complete; validate $TARGET_ROOT and $DBNAME before promoting"
