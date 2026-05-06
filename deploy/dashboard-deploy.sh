#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Nami Dashboard — VPS Deploy Script
#  Run on VPS: bash deploy/dashboard-deploy.sh
#
#  Prerequisites: Node.js 20+, npm, nginx
# ──────────────────────────────────────────────────────────────
set -euo pipefail

DASHBOARD_DIR="/opt/nami-dashboard"
REPO_DIR="/opt/nami-core"
DASHBOARD_SRC="$REPO_DIR/nami-dashboard"
PORT=3000

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Nami Dashboard — VPS Deploy                                ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Step 1: Copy dashboard source
echo "[1/5] Copying dashboard source..."
rm -rf "$DASHBOARD_DIR"
cp -r "$DASHBOARD_SRC" "$DASHBOARD_DIR"
cd "$DASHBOARD_DIR"

# Step 2: Install dependencies
echo "[2/5] Installing dependencies..."
npm ci --production=false

# Step 3: Create env file
echo "[3/5] Creating .env.local..."
cat > .env.local << 'EOF'
NEXT_PUBLIC_API_URL=https://nami-api.178.104.181.132.nip.io
NEXT_PUBLIC_WS_URL=wss://nami-api.178.104.181.132.nip.io/ws
EOF

# Step 4: Build
echo "[4/5] Building..."
npm run build

# Step 5: Install systemd service
echo "[5/5] Installing systemd service..."
cat > /etc/systemd/system/nami-dashboard.service << EOF
[Unit]
Description=Nami Dashboard (Next.js)
After=network.target

[Service]
Type=simple
WorkingDirectory=$DASHBOARD_DIR
ExecStart=$(which node) .next/standalone/server.js
Environment=PORT=$PORT
Environment=HOSTNAME=0.0.0.0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nami-dashboard
systemctl restart nami-dashboard

sleep 3
if systemctl is-active nami-dashboard; then
    echo "  ✅ nami-dashboard running on port $PORT"
else
    echo "  ❌ nami-dashboard failed to start"
    journalctl -u nami-dashboard --no-pager -n 20
    exit 1
fi

# Nginx config (append if not exists)
NGINX_CONF="/etc/nginx/sites-available/nami"
if ! grep -q "location /dashboard" "$NGINX_CONF" 2>/dev/null; then
    echo ""
    echo "⚠️  Add this to your nginx config:"
    echo ""
    echo "    location /dashboard {"
    echo "        proxy_pass http://127.0.0.1:$PORT;"
    echo "        proxy_http_version 1.1;"
    echo "        proxy_set_header Upgrade \$http_upgrade;"
    echo "        proxy_set_header Connection 'upgrade';"
    echo "        proxy_set_header Host \$host;"
    echo "        proxy_cache_bypass \$http_upgrade;"
    echo "    }"
    echo ""
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Dashboard Deploy Complete!                                  ║"
echo "║  URL: https://nami.178.104.181.132.nip.io/dashboard         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
