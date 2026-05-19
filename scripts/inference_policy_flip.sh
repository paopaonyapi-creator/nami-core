#!/usr/bin/env bash
# Nami OS T1 — flip inference_policy.yaml (atomic, reversible)
#
# Companion to nami-rollout-stage.sh (which only handles env-var knobs).
# This script flips policy.enabled / policy.dry_run with auto-backup so
# the cutover from "stub mode" → "real LLM traffic" is a single command
# and always rolls back cleanly.
#
# Usage:
#   sudo bash scripts/inference_policy_flip.sh status
#   sudo bash scripts/inference_policy_flip.sh stub-mode      # enabled=true, dry_run=true
#   sudo bash scripts/inference_policy_flip.sh real-traffic   # enabled=true, dry_run=false   (REQUIRES APPROVAL)
#   sudo bash scripts/inference_policy_flip.sh kill-switch    # enabled=false, dry_run=true   (hard halt all LLM)
#   sudo bash scripts/inference_policy_flip.sh rollback       # restore newest backup
#
# Approval (for real-traffic only):
#   NAMI_INFERENCE_FLIP_APPROVED=real-traffic sudo bash scripts/inference_policy_flip.sh real-traffic
#
# Env overrides:
#   NAMI_INFERENCE_POLICY_FILE   default: /opt/nami-core/config/inference_policy.yaml
#                                fallback: /opt/nami/current/config/inference_policy.yaml
#                                fallback: /etc/nami-harness/inference_policy.yaml
#   NAMI_INFERENCE_BACKUP_DIR    default: /etc/nami-harness/inference-backup

set -u

POLICY_FILE="${NAMI_INFERENCE_POLICY_FILE:-}"
if [ -z "$POLICY_FILE" ]; then
  for c in \
    /opt/nami-core/config/inference_policy.yaml \
    /opt/nami/current/config/inference_policy.yaml \
    /opt/nami/current/nami-core/config/inference_policy.yaml \
    /etc/nami-harness/inference_policy.yaml; do
    [ -f "$c" ] && POLICY_FILE="$c" && break
  done
fi

BACKUP_DIR="${NAMI_INFERENCE_BACKUP_DIR:-/etc/nami-harness/inference-backup}"
ACTION="${1:-}"

die() { printf 'ABORT: %s\n' "$1" >&2; exit 1; }
ok()  { printf '[ok ] %s\n' "$1"; }
warn(){ printf '[warn] %s\n' "$1"; }

if [ -z "$ACTION" ]; then
  cat <<EOF
Usage: $0 <action>

Actions:
  status         show current enabled/dry_run + last backup
  stub-mode      enabled=true,  dry_run=true   (planner runs, no spend)
  real-traffic   enabled=true,  dry_run=false  (REAL API spend; needs approval)
  kill-switch    enabled=false, dry_run=true   (hard halt all LLM)
  rollback       restore newest backup

Approval for real-traffic:
  NAMI_INFERENCE_FLIP_APPROVED=real-traffic $0 real-traffic
EOF
  exit 1
fi

if [ -z "$POLICY_FILE" ] || [ ! -f "$POLICY_FILE" ]; then
  die "policy file not found (set NAMI_INFERENCE_POLICY_FILE)"
fi

read_bool() {
  local key="$1"
  grep -E "^[[:space:]]*${key}:" "$POLICY_FILE" | head -n 1 | awk -F: '{print $2}' | tr -d '[:space:]'
}

print_status() {
  printf 'policy_file = %s\n' "$POLICY_FILE"
  printf 'enabled     = %s\n' "$(read_bool enabled || echo missing)"
  printf 'dry_run     = %s\n' "$(read_bool dry_run || echo missing)"
  if [ -d "$BACKUP_DIR" ]; then
    last=$(ls -1t "$BACKUP_DIR" 2>/dev/null | head -n 1)
    [ -n "$last" ] && printf 'last_backup = %s/%s\n' "$BACKUP_DIR" "$last" \
      || printf 'last_backup = (none)\n'
  else
    printf 'last_backup = (no backup dir)\n'
  fi
}

backup_now() {
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  bkp="$BACKUP_DIR/inference_policy.yaml.$ts"
  cp -p "$POLICY_FILE" "$bkp" || die "backup failed"
  chmod 400 "$bkp"
  printf '%s\n' "$bkp"
}

# Atomic in-place flip. Pure sed; YAML schema and all other keys untouched.
flip_keys() {
  local enabled_val="$1"
  local dry_run_val="$2"
  local tmp
  tmp="$(mktemp "${POLICY_FILE}.flip.XXXXXX")" || die "mktemp failed"
  # Preserve mode + owner of original.
  cp -p "$POLICY_FILE" "$tmp" || die "stage copy failed"
  sed -i \
    -e "s/^[[:space:]]*enabled:[[:space:]]*[a-zA-Z]*[[:space:]]*$/enabled: ${enabled_val}/" \
    -e "s/^[[:space:]]*dry_run:[[:space:]]*[a-zA-Z]*[[:space:]]*$/dry_run: ${dry_run_val}/" \
    "$tmp" \
    || { rm -f "$tmp"; die "sed flip failed"; }
  mv "$tmp" "$POLICY_FILE" || die "atomic mv failed"
}

require_approval() {
  local stage="$1"
  if [ "${NAMI_INFERENCE_FLIP_APPROVED:-}" != "$stage" ]; then
    cat >&2 <<EOF
Refusing $stage without explicit approval.

This action enables real LLM API spending. Re-run with:
  NAMI_INFERENCE_FLIP_APPROVED=$stage $0 $stage
EOF
    exit 2
  fi
}

case "$ACTION" in
  status)
    print_status
    exit 0
    ;;

  stub-mode)
    bkp=$(backup_now); ok "backup -> $bkp"
    flip_keys true true; ok "policy: enabled=true dry_run=true"
    print_status
    cat <<EOF

Next steps:
  systemctl restart nami-core
  systemctl restart 'nami-worker@*'

Verify:
  curl -fsS http://127.0.0.1:8092/runtime/health
  bash scripts/inference_policy_flip.sh status
EOF
    ;;

  real-traffic)
    require_approval real-traffic
    cur_enabled=$(read_bool enabled || echo missing)
    cur_dry=$(read_bool dry_run || echo missing)
    if [ "$cur_enabled" != "true" ] || [ "$cur_dry" != "true" ]; then
      die "preflight: must transition from enabled=true,dry_run=true (current: enabled=$cur_enabled dry_run=$cur_dry). Run stub-mode first."
    fi
    bkp=$(backup_now); ok "backup -> $bkp"
    flip_keys true false; ok "policy: enabled=true dry_run=false"
    print_status
    cat <<EOF

⚠ REAL TRAFFIC NOW ARMED. Watch:
  /metrics/prometheus | grep nami_inference_cost_estimate_usd
  /metrics/prometheus | grep nami_inference_failures_total

Restart workers:
  systemctl restart nami-core
  systemctl restart 'nami-worker@*'

Rollback if anything looks off:
  bash scripts/inference_policy_flip.sh rollback
EOF
    ;;

  kill-switch)
    bkp=$(backup_now); ok "backup -> $bkp"
    flip_keys false true; ok "policy: enabled=false dry_run=true (hard halt)"
    print_status
    cat <<EOF

Hard halt active. Inference gateway will raise RuntimeError on every call.
Restart workers to apply:
  systemctl restart nami-core
  systemctl restart 'nami-worker@*'
EOF
    ;;

  rollback)
    [ -d "$BACKUP_DIR" ] || die "no backup dir at $BACKUP_DIR"
    last=$(ls -1t "$BACKUP_DIR" 2>/dev/null | head -n 1)
    [ -n "$last" ] || die "no backup file in $BACKUP_DIR"
    cur_bkp=$(backup_now); ok "snapshot current -> $cur_bkp"
    cp -p "$BACKUP_DIR/$last" "$POLICY_FILE" || die "restore failed"
    ok "restored from $BACKUP_DIR/$last"
    print_status
    cat <<EOF

Restart workers:
  systemctl restart nami-core
  systemctl restart 'nami-worker@*'
EOF
    ;;

  *)
    die "unknown action: $ACTION (try: status, stub-mode, real-traffic, kill-switch, rollback)"
    ;;
esac
