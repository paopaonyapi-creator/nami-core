#!/usr/bin/env bash
# Nami Core — One-command deploy
# Usage: bash deploy/install.sh [--shadow]
#
# --shadow: install alongside existing services (no switch)
# default: install and switch over

set -euo pipefail

DEPLOY_DIR="/opt/nami-core"
CONFIG_DIR="/opt/nami-core/config"
LOG_DIR="/var/log/nami-harness"
BACKUP_DIR="/opt/backup/nami-core-$(date +%Y%m%d-%H%M%S)"
SHADOW_MODE=false

if [[ "${1:-}" == "--shadow" ]]; then
    SHADOW_MODE=true
    echo "[INFO] Shadow mode: will not disable existing services"
fi

echo "=== Nami Core Deploy ==="
echo "Target: $DEPLOY_DIR"
echo "Shadow: $SHADOW_MODE"
echo ""

# 1. Backup existing if present
if [[ -d "$DEPLOY_DIR" ]]; then
    echo "[1/7] Backing up existing deployment..."
    mkdir -p "$BACKUP_DIR"
    cp -r "$DEPLOY_DIR" "$BACKUP_DIR/"
    echo "  Backup: $BACKUP_DIR"
else
    echo "[1/7] No existing deployment, skipping backup"
fi

# 2. Create directories
echo "[2/7] Creating directories..."
mkdir -p "$DEPLOY_DIR/src"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"

# 3. Copy source
echo "[3/7] Copying source files..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cp -r "$PROJECT_DIR/src/"* "$DEPLOY_DIR/src/"
cp -r "$PROJECT_DIR/config/"* "$CONFIG_DIR/"
cp "$PROJECT_DIR/pyproject.toml" "$DEPLOY_DIR/"

# 4. Create venv and install
echo "[4/7] Setting up Python environment..."
if [[ ! -d "$DEPLOY_DIR/.venv" ]]; then
    python3 -m venv "$DEPLOY_DIR/.venv"
fi
"$DEPLOY_DIR/.venv/bin/pip" install -e "$DEPLOY_DIR[dev]" --quiet

# 5. Install systemd units
echo "[5/7] Installing systemd units..."
cp "$PROJECT_DIR/deploy/systemd/nami-core.service" /etc/systemd/system/
cp "$PROJECT_DIR/deploy/systemd/nami-worker@.service" /etc/systemd/system/
systemctl daemon-reload

# 6. Install nginx config (shadow mode: skip)
if [[ "$SHADOW_MODE" == "false" ]]; then
    echo "[6/7] Installing nginx config..."
    cp "$PROJECT_DIR/deploy/nginx/nami-core.conf" /etc/nginx/sites-available/
    ln -sf /etc/nginx/sites-available/nami-core.conf /etc/nginx/sites-enabled/
    nginx -t
else
    echo "[6/7] Shadow mode: skipping nginx config change"
fi

# 7. Start services
echo "[7/7] Starting services..."
systemctl enable nami-core.service
systemctl start nami-core.service

if [[ "$SHADOW_MODE" == "false" ]]; then
    echo ""
    echo "=== Switch-over mode ==="
    echo "Old services should be stopped manually after verification."
    echo "Run: systemctl status nami-core"
else
    echo ""
    echo "=== Shadow mode ==="
    echo "Nami Core running alongside existing services."
    echo "Verify: systemctl status nami-core"
    echo "Logs: journalctl -u nami-core -f"
fi

echo ""
echo "Deploy complete."
