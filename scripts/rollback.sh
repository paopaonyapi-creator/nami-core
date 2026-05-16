#!/usr/bin/env bash
# Phase 30 — atomic-deploy rollback.
# Reverts NAMI_CURRENT_SYMLINK to the previous release recorded in
# $NAMI_RELEASES_DIR/.previous (written by deploy.sh on every promote).
# Idempotent; fails closed if no previous release exists.
set -euo pipefail

if [[ -z "${NAMI_RELEASES_DIR:-}" || -z "${NAMI_CURRENT_SYMLINK:-}" ]]; then
  echo "NAMI_RELEASES_DIR and NAMI_CURRENT_SYMLINK required" >&2
  exit 2
fi

prev_file="$NAMI_RELEASES_DIR/.previous"
if [[ ! -f "$prev_file" ]]; then
  echo "no previous release recorded at $prev_file" >&2
  exit 2
fi

prev_id="$(cat "$prev_file")"
prev_dir="$NAMI_RELEASES_DIR/$prev_id"
if [[ ! -d "$prev_dir" ]]; then
  echo "previous release dir missing: $prev_dir" >&2
  exit 2
fi

current_target="$(readlink -f "$NAMI_CURRENT_SYMLINK" 2>/dev/null || true)"
ln -sfn "$prev_dir" "$NAMI_CURRENT_SYMLINK"
printf -- "- %s ROLLBACK %s -> %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$current_target" "$prev_dir" >> incidents.md
echo "rolled back to $prev_dir"

if [[ -n "${NAMI_RESTART_CMD:-}" ]]; then
  eval "$NAMI_RESTART_CMD"
fi
