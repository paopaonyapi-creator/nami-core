#!/usr/bin/env bash
# Phase 26.3 + 30 — atomic deploy with eval gate, smoke gate, and auto-rollback.
#
# Pipeline:
#   1. Eval gate (Phase 26.3) — nami-evals fail-under threshold
#   2. Symlink-swap to new release (atomic)
#   3. Optional restart hook ($NAMI_RESTART_CMD)
#   4. Smoke gate (Phase 30) — scripts/smoke.sh
#   5. On smoke failure → scripts/rollback.sh (revert + restart) → exit 1
#
# Break-glass:
#   SKIP_EVAL=1     bypass eval gate (logged to incidents.md)
#   SKIP_SMOKE=1    bypass smoke gate (logged)
#   NAMI_DEPLOY_DRY_RUN=1   stop after eval gate (default)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf -- "[deploy] %s\n" "$*"; }
incident() { printf -- "- %s %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> incidents.md; }

# ── Eval gate ──────────────────────────────────────────────────────────
if [[ "${SKIP_EVAL:-0}" == "1" ]]; then
  log "SKIP_EVAL=1; bypassing eval gate"
  incident "SKIP_EVAL=1 eval gate bypass before deploy"
else
  python nami-evals/runner.py run --all --fail-under "${NAMI_EVAL_FAIL_UNDER:-0.85}"
fi

if [[ "${NAMI_DEPLOY_DRY_RUN:-1}" == "1" ]]; then
  log "deploy dry-run complete; eval gate passed"
  exit 0
fi

# ── Required env for symlink-swap ──────────────────────────────────────
if [[ -z "${NAMI_RELEASES_DIR:-}" || -z "${NAMI_CURRENT_SYMLINK:-}" || -z "${NAMI_RELEASE_ID:-}" ]]; then
  echo "NAMI_RELEASES_DIR, NAMI_CURRENT_SYMLINK, and NAMI_RELEASE_ID are required for deploy" >&2
  exit 2
fi

release_dir="$NAMI_RELEASES_DIR/$NAMI_RELEASE_ID"
if [[ ! -d "$release_dir" ]]; then
  echo "release directory not found: $release_dir" >&2
  exit 2
fi

# ── Record previous release for rollback.sh ────────────────────────────
prev_target="$(readlink -f "$NAMI_CURRENT_SYMLINK" 2>/dev/null || true)"
if [[ -n "$prev_target" && -d "$prev_target" ]]; then
  prev_id="$(basename "$prev_target")"
  echo "$prev_id" > "$NAMI_RELEASES_DIR/.previous"
  log "recorded previous release: $prev_id"
fi

# ── Promote (atomic) ───────────────────────────────────────────────────
ln -sfn "$release_dir" "$NAMI_CURRENT_SYMLINK"
log "promoted $release_dir -> $NAMI_CURRENT_SYMLINK"

# ── Optional restart ───────────────────────────────────────────────────
if [[ -n "${NAMI_RESTART_CMD:-}" ]]; then
  log "running restart hook: $NAMI_RESTART_CMD"
  eval "$NAMI_RESTART_CMD"
fi

# ── Smoke gate + auto-rollback ─────────────────────────────────────────
if [[ "${SKIP_SMOKE:-0}" == "1" ]]; then
  log "SKIP_SMOKE=1; bypassing smoke gate"
  incident "SKIP_SMOKE=1 smoke gate bypass after promote of $NAMI_RELEASE_ID"
  exit 0
fi

if bash "$ROOT_DIR/scripts/smoke.sh"; then
  log "smoke green; deploy of $NAMI_RELEASE_ID complete"
  exit 0
fi

# Smoke failed — auto-rollback.
log "SMOKE FAILED for $NAMI_RELEASE_ID; auto-rolling back"
incident "AUTO-ROLLBACK triggered after $NAMI_RELEASE_ID smoke fail"
bash "$ROOT_DIR/scripts/rollback.sh"
exit 1
