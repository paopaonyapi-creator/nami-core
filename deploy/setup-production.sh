#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  Nami Core — Full VPS Production Setup
#  Run on VPS: bash deploy/setup-production.sh
#
#  Does: Redis install, nginx API proxy fix, nami-core env config
# ──────────────────────────────────────────────────────────────
set -euo pipefail

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Nami Core — Full Production Setup                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# ─── Step 1: Install Redis ──────────────────────────────────────
echo "[1/4] Installing Redis..."
if command -v redis-server &>/dev/null; then
    echo "  ✅ Redis already installed: $(redis-server --version | head -1)"
else
    apt-get update -qq
    apt-get install -y redis-server
    echo "  ✅ Redis installed"
fi

# Configure Redis for production (cache-only, no persistence)
REDIS_CONF="/etc/redis/redis.conf"
if [[ -f "$REDIS_CONF" ]]; then
    sed -i 's/^bind .*/bind 127.0.0.1/' "$REDIS_CONF"
    sed -i 's/^save .*/# save disabled for cache-only mode/' "$REDIS_CONF"
    grep -q "^maxmemory" "$REDIS_CONF" && sed -i 's/^maxmemory .*/maxmemory 256mb/' "$REDIS_CONF" || echo "maxmemory 256mb" >> "$REDIS_CONF"
    grep -q "^maxmemory-policy" "$REDIS_CONF" && sed -i 's/^maxmemory-policy .*/maxmemory-policy allkeys-lru/' "$REDIS_CONF" || echo "maxmemory-policy allkeys-lru" >> "$REDIS_CONF"
    echo "  ✅ Redis configured (localhost, 256MB, LRU, no persistence)"
fi

systemctl enable redis-server
systemctl restart redis-server
sleep 2
if redis-cli ping 2>/dev/null | grep -q PONG; then
    echo "  ✅ Redis running (PING → PONG)"
else
    echo "  ❌ Redis failed to start"
    journalctl -u redis-server --no-pager -n 10
    exit 1
fi

# ─── Step 2: Configure nami-core environment ────────────────────
echo "[2/4] Configuring nami-core environment..."
NAMI_ENV="/opt/nami-core/.env"
REDIS_URL="redis://localhost:6379/0"

mkdir -p /opt/nami-core
if [[ -f "$NAMI_ENV" ]]; then
    grep -q "NAMI_REDIS_URL" "$NAMI_ENV" && sed -i "s|NAMI_REDIS_URL=.*|NAMI_REDIS_URL=$REDIS_URL|" "$NAMI_ENV" || echo "NAMI_REDIS_URL=$REDIS_URL" >> "$NAMI_ENV"
else
    echo "NAMI_REDIS_URL=$REDIS_URL" > "$NAMI_ENV"
fi
echo "  ✅ NAMI_REDIS_URL=$REDIS_URL"

# systemd override
SYSTEMD_OVERRIDE="/etc/systemd/system/nami-core.service.d/override.conf"
mkdir -p /etc/systemd/system/nami-core.service.d/
if [[ -f "$SYSTEMD_OVERRIDE" ]]; then
    grep -q "NAMI_REDIS_URL" "$SYSTEMD_OVERRIDE" && sed -i "s|Environment=NAMI_REDIS_URL=.*|Environment=NAMI_REDIS_URL=$REDIS_URL|" "$SYSTEMD_OVERRIDE" || echo "Environment=NAMI_REDIS_URL=$REDIS_URL" >> "$SYSTEMD_OVERRIDE"
else
    cat > "$SYSTEMD_OVERRIDE" << EOF
[Service]
Environment=NAMI_REDIS_URL=$REDIS_URL
EOF
fi
systemctl daemon-reload
echo "  ✅ systemd override configured"

# ─── Step 3: Fix nginx — remove auth_basic for API endpoints ───
echo "[3/4] Fixing nginx config for API access..."
NGINX_CONF="/etc/nginx/sites-available/nami"

if [[ -f "$NGINX_CONF" ]]; then
    # Backup
    cp "$NGINX_CONF" "${NGINX_CONF}.bak.$(date +%Y%m%d%H%M%S)"

    # Add location blocks that skip auth for API endpoints
    # These must come BEFORE the generic location / block
    if ! grep -q "location /health" "$NGINX_CONF"; then
        # Insert API no-auth blocks before the main location block
        sed -i '/location \/ {/i \
    # API endpoints — no auth (dashboard calls these from Netlify)\
    location ~ ^/(health|workers|metrics|metrics/prometheus|docs|redoc|openapi.json|audit|cache|db|scheduler) {\
        proxy_pass http://127.0.0.1:8092;\
        proxy_http_version 1.1;\
        proxy_set_header Upgrade $http_upgrade;\
        proxy_set_header Connection "upgrade";\
        proxy_set_header Host $host;\
        proxy_set_header X-Real-IP $remote_addr;\
        proxy_cache_bypass $http_upgrade;\
        # No auth_basic here — public read endpoints\
    }\
\
    # WebSocket — no auth\
    location /ws {\
        proxy_pass http://127.0.0.1:8092/ws;\
        proxy_http_version 1.1;\
        proxy_set_header Upgrade $http_upgrade;\
        proxy_set_header Connection "upgrade";\
        proxy_set_header Host $host;\
        proxy_set_header X-Real-IP $remote_addr;\
        # No auth_basic here\
    }\
' "$NGINX_CONF"
        echo "  ✅ Added no-auth API and WS location blocks"
    else
        echo "  ✅ API no-auth blocks already exist"
    fi

    # Test and reload nginx
    if nginx -t 2>/dev/null; then
        systemctl reload nginx
        echo "  ✅ nginx reloaded"
    else
        echo "  ❌ nginx config test failed — restoring backup"
        cp "${NGINX_CONF}.bak."* "$NGINX_CONF" 2>/dev/null || true
        nginx -t && systemctl reload nginx
    fi
else
    echo "  ⚠️  nginx config not found at $NGINX_CONF — manual setup needed"
fi

# ─── Step 4: Restart nami-core and verify ──────────────────────
echo "[4/4] Restarting nami-core and verifying..."
systemctl restart nami-core
sleep 5

if systemctl is-active nami-core &>/dev/null; then
    echo "  ✅ nami-core running"
else
    echo "  ❌ nami-core failed to start"
    journalctl -u nami-core --no-pager -n 20
    exit 1
fi

# Verify Redis cache
CACHE_STATS=$(curl -sf http://127.0.0.1:8092/cache 2>/dev/null || echo '{"backend":"unknown"}')
echo "  Cache: $CACHE_STATS"

# Verify health
HEALTH=$(curl -sf http://127.0.0.1:8092/health 2>/dev/null || echo '{"status":"error"}')
echo "  Health: $HEALTH"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Production Setup Complete!                                  ║"
echo "║                                                              ║"
echo "║  Redis:    redis://localhost:6379/0                          ║"
echo "║  API:      https://nami.178.104.181.132.nip.io              ║"
echo "║  Dashboard: https://nami-dashboard-5e6b3149.netlify.app     ║"
echo "║                                                              ║"
echo "║  Verify:                                                    ║"
echo "║    curl https://nami.178.104.181.132.nip.io/health          ║"
echo "║    curl https://nami.178.104.181.132.nip.io/cache           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
