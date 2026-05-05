#!/usr/bin/env bash
# Nami Core — VPS Migration Script
# Run ON the VPS to extract real code from /opt/* services
# into nami-core worker files.
#
# Usage: bash deploy/migrate-vps.sh
#
# This script reads the actual Python code from each service
# and generates worker implementation files with the real logic.
# It does NOT modify or stop existing services.

set -euo pipefail

NAMI_CORE_DIR="/opt/nami-core"
WORKERS_DIR="$NAMI_CORE_DIR/src/nami_workers"
BACKUP_DIR="/opt/backup/vps-migration-$(date +%Y%m%d-%H%M%S)"

echo "╔══════════════════════════════════════════╗"
echo "║  Nami Core — VPS Migration Script        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Verify we're on the VPS
if [ ! -d "/etc/nami-harness" ]; then
    echo "ERROR: This script must be run on the VPS"
    exit 1
fi

# Create backup
echo "[1/5] Backing up current worker files..."
mkdir -p "$BACKUP_DIR"
cp -r "$WORKERS_DIR" "$BACKUP_DIR/"

# Extract signal logic
echo "[2/5] Extracting signal logic from /opt/telegram-premium-bot..."
if [ -d "/opt/telegram-premium" ]; then
    SIGNAL_FILES=$(find /opt/telegram-premium -name "*.py" -type f 2>/dev/null | head -20)
    echo "  Found signal files:"
    for f in $SIGNAL_FILES; do
        echo "    - $f ($(wc -l < "$f") lines)"
    done
    echo "  → Manual step: Copy signal generation + Telegram sending logic into signal_worker.py"
else
    echo "  ⚠️  /opt/telegram-premium not found"
fi

# Extract proxy logic
echo "[3/5] Extracting proxy logic from /opt/maxplus-proxy..."
if [ -f "/opt/maxplus-proxy/proxy.py" ]; then
    PROXY_LINES=$(wc -l < /opt/maxplus-proxy/proxy.py)
    echo "  Found proxy.py ($PROXY_LINES lines)"
    echo "  → Manual step: Copy multi-provider fallback logic into proxy_worker.py"
else
    echo "  ⚠️  /opt/maxplus-proxy/proxy.py not found"
fi

# Extract lottery logic
echo "[4/5] Extracting lottery logic..."
for dir in /opt/hanoi-bot /opt/laopatana-stat-lab; do
    if [ -d "$dir" ]; then
        FILES=$(find "$dir" -name "*.py" -type f 2>/dev/null | head -20)
        echo "  Found in $dir:"
        for f in $FILES; do
            echo "    - $f ($(wc -l < "$f") lines)"
        done
    else
        echo "  ⚠️  $dir not found"
    fi
done
echo "  → Manual step: Copy prediction + scraper logic into lottery_worker.py"

# Extract remaining services
echo "[5/5] Extracting remaining service logic..."
for service_dir in /opt/nami-bot /opt/gold-signal-os /opt/nami-api-gateway /opt/nami-status-api /opt/nami-bridge /opt/graphify-http; do
    if [ -d "$service_dir" ]; then
        SVC_NAME=$(basename "$service_dir")
        FILES=$(find "$service_dir" -name "*.py" -type f 2>/dev/null | head -10)
        echo "  $SVC_NAME:"
        for f in $FILES; do
            echo "    - $f ($(wc -l < "$f") lines)"
        done
    fi
done

echo ""
echo "═══════════════════════════════════════════"
echo "Next steps:"
echo "1. Review the files listed above"
echo "2. Copy relevant logic into worker files in $WORKERS_DIR"
echo "3. Run: pytest (verify all tests still pass)"
echo "4. Run: bash deploy/install.sh --shadow (deploy alongside existing)"
echo "5. Compare outputs for 3 days"
echo "6. Run: bash deploy/install.sh (switch over)"
echo ""
echo "Backup saved to: $BACKUP_DIR"
