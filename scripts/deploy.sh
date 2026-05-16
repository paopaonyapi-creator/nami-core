#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${SKIP_EVAL:-0}" == "1" ]]; then
  echo "SKIP_EVAL=1 set; bypassing eval gate"
  printf -- "- %s SKIP_EVAL=1 eval gate bypass before deploy\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> incidents.md
else
  python nami-evals/runner.py run --all --fail-under "${NAMI_EVAL_FAIL_UNDER:-0.85}"
fi

if [[ "${NAMI_DEPLOY_DRY_RUN:-1}" == "1" ]]; then
  echo "deploy dry-run complete; eval gate passed"
  exit 0
fi

if [[ -z "${NAMI_RELEASES_DIR:-}" || -z "${NAMI_CURRENT_SYMLINK:-}" || -z "${NAMI_RELEASE_ID:-}" ]]; then
  echo "NAMI_RELEASES_DIR, NAMI_CURRENT_SYMLINK, and NAMI_RELEASE_ID are required for deploy" >&2
  exit 2
fi

release_dir="$NAMI_RELEASES_DIR/$NAMI_RELEASE_ID"
if [[ ! -d "$release_dir" ]]; then
  echo "release directory not found: $release_dir" >&2
  exit 2
fi

ln -sfn "$release_dir" "$NAMI_CURRENT_SYMLINK"
echo "promoted $release_dir -> $NAMI_CURRENT_SYMLINK"
