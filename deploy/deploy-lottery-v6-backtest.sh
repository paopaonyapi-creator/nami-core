#!/usr/bin/env bash
# Nami Core — Deploy lottery_worker.py + lottery_harness.yaml for Phase 25.14
#
# Usage (from local with SSH access to VPS):
#   bash nami-core/deploy/deploy-lottery-v6-backtest.sh
#
# Or run inline on VPS after copying files manually.

set -euo pipefail

VPS_HOST="${VPS_HOST:-root@178.104.181.132}"
NAMI_CORE_ROOT="${NAMI_CORE_ROOT:-/opt/nami-core}"
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

WORKER_SRC="$LOCAL_ROOT/src/nami_workers/lottery_worker.py"
HARNESS_SRC="$LOCAL_ROOT/config/lottery_harness.yaml"

WORKER_DEST="$NAMI_CORE_ROOT/src/nami_workers/lottery_worker.py"
HARNESS_DEST="$NAMI_CORE_ROOT/config/lottery_harness.yaml"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Phase 25.14 — Lottery v6 Backtest Harness Deploy           ║"
echo "║  Target: $VPS_HOST                                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

[ -f "$WORKER_SRC" ]  || { echo "❌ missing $WORKER_SRC"; exit 1; }
[ -f "$HARNESS_SRC" ] || { echo "❌ missing $HARNESS_SRC"; exit 1; }

echo "[1/5] Verifying SSH access..."
ssh -o ConnectTimeout=10 "$VPS_HOST" "echo SSH_OK" >/dev/null || { echo "❌ SSH failed"; exit 1; }
echo "  ✅ SSH ok"

echo "[2/5] Backing up current worker + harness on VPS..."
TS="$(date -u +%Y%m%dT%H%M%SZ)"
ssh "$VPS_HOST" "
  set -e
  cp '$WORKER_DEST'  '$WORKER_DEST.bak.$TS'  2>/dev/null || true
  cp '$HARNESS_DEST' '$HARNESS_DEST.bak.$TS' 2>/dev/null || true
  ls -la '$WORKER_DEST.bak.$TS' '$HARNESS_DEST.bak.$TS' 2>/dev/null || true
"

echo "[3/5] Uploading new files..."
scp -q "$WORKER_SRC"  "$VPS_HOST:$WORKER_DEST"
scp -q "$HARNESS_SRC" "$VPS_HOST:$HARNESS_DEST"
echo "  ✅ files uploaded"

echo "[4/5] Syntax-checking new worker (py_compile)..."
ssh "$VPS_HOST" "cd '$NAMI_CORE_ROOT' && python3 -m py_compile '$WORKER_DEST'" \
  && echo "  ✅ py_compile ok" \
  || { echo "❌ py_compile failed; reverting"; \
       ssh "$VPS_HOST" "cp '$WORKER_DEST.bak.$TS' '$WORKER_DEST'"; exit 1; }

echo "[5/5] Restarting nami-core service..."
ssh "$VPS_HOST" "systemctl restart nami-core && sleep 2 && systemctl is-active nami-core"
echo "  ✅ nami-core active"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Deploy complete. Smoke test:                                ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  curl -X POST http://127.0.0.1:8092/dispatch \\               ║"
echo "║    -H 'Content-Type: application/json' \\                     ║"
echo "║    -d '{\"worker\":\"lottery\",\"action\":\"backtest_v6\",          ║"
echo "║         \"payload\":{\"region\":\"lao\",\"dry_run\":true,           ║"
echo "║         \"days\":60,\"min_history\":30}}' | jq .                ║"
echo "║                                                              ║"
echo "║  Rollback (if needed):                                       ║"
echo "║  ssh $VPS_HOST 'cp $WORKER_DEST.bak.$TS $WORKER_DEST &&      ║"
echo "║      systemctl restart nami-core'                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
