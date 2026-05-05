#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  Nami Core — Remote VPS Deploy                               ║
# ║  Run from ANY machine that has SSH access to the VPS         ║
# ║                                                              ║
# ║  Usage:                                                      ║
# ║    bash deploy/remote-deploy.sh                              ║
# ║    bash deploy/remote-deploy.sh --shadow                     ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

VPS_HOST="root@178.104.181.132"
SHADOW_MODE=""
if [[ "${1:-}" == "--shadow" ]]; then
    SHADOW_MODE="--shadow"
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Nami Core — Remote VPS Deploy                              ║"
echo "║  Target: $VPS_HOST                                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Verify SSH access
echo "[1/4] Verifying SSH access..."
if ssh -o ConnectTimeout=10 "$VPS_HOST" "echo SSH_OK" 2>/dev/null; then
    echo "  ✅ SSH access confirmed"
else
    echo "  ❌ SSH access denied"
    echo ""
    echo "  To add this machine's SSH key to the VPS:"
    echo "  1. From a machine that already has access, run:"
    echo "     ssh-copy-id -i ~/.ssh/id_ed25519.pub $VPS_HOST"
    echo ""
    echo "  2. Or manually add the public key to VPS:"
    echo "     cat ~/.ssh/id_ed25519.pub"
    echo "     # Then on VPS: echo '<public_key>' >> ~/.ssh/authorized_keys"
    exit 1
fi

# Step 2: Clone/pull nami-core on VPS
echo "[2/4] Setting up nami-core on VPS..."
ssh "$VPS_HOST" bash -s << 'REMOTE_SCRIPT'
set -euo pipefail
DEPLOY_DIR="/opt/nami-core"
if [[ -d "$DEPLOY_DIR" ]]; then
    cd "$DEPLOY_DIR" && git pull
else
    git clone https://github.com/paopaonyapi-creator/nami-core.git "$DEPLOY_DIR"
fi
REMOTE_SCRIPT
echo "  ✅ Repo ready on VPS"

# Step 3: Run VPS setup script
echo "[3/4] Running VPS setup script..."
ssh "$VPS_HOST" "cd /opt/nami-core && bash deploy/vps-setup.sh $SHADOW_MODE"
echo "  ✅ VPS setup complete"

# Step 4: Verify
echo "[4/4] Verifying deployment..."
ssh "$VPS_HOST" bash -s << 'REMOTE_SCRIPT'
set -euo pipefail
echo "  Services:"
systemctl is-active nami-core.service || echo "    nami-core: not running"
echo "  Disk:"
df -h /opt/nami-core 2>/dev/null || echo "    N/A"
echo "  Tests:"
cd /opt/nami-core && PYTHONPATH=src .venv/bin/python -m pytest tests/ -q 2>&1 | tail -1
REMOTE_SCRIPT

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Remote Deploy Complete!                                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
