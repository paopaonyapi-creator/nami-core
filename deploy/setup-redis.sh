#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  Nami Core — Redis Setup on VPS
#  Run on VPS: bash deploy/setup-redis.sh
#
#  Installs Redis, configures it for production, and sets
#  NAMI_REDIS_URL in nami-core environment.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Nami Core — Redis Production Setup                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Step 1: Install Redis
echo "[1/5] Installing Redis..."
if command -v redis-server &>/dev/null; then
    echo "  ✅ Redis already installed: $(redis-server --version | head -1)"
else
    apt-get update -qq
    apt-get install -y redis-server
    echo "  ✅ Redis installed"
fi

# Step 2: Configure Redis for production
echo "[2/5] Configuring Redis for production..."
REDIS_CONF="/etc/redis/redis.conf"
if [[ -f "$REDIS_CONF" ]]; then
    # Bind to localhost only
    sed -i 's/^bind .*/bind 127.0.0.1/' "$REDIS_CONF"
    # Disable persistence (cache-only, no disk writes)
    sed -i 's/^save .*/# save disabled for cache-only mode/' "$REDIS_CONF"
    # Set max memory (256MB for cache)
    grep -q "^maxmemory" "$REDIS_CONF" && sed -i 's/^maxmemory .*/maxmemory 256mb/' "$REDIS_CONF" || echo "maxmemory 256mb" >> "$REDIS_CONF"
    # Eviction policy
    grep -q "^maxmemory-policy" "$REDIS_CONF" && sed -i 's/^maxmemory-policy .*/maxmemory-policy allkeys-lru/' "$REDIS_CONF" || echo "maxmemory-policy allkeys-lru" >> "$REDIS_CONF"
    echo "  ✅ Redis configured (localhost, 256MB, LRU eviction, no persistence)"
else
    echo "  ⚠️  Config not found at $REDIS_CONF, using defaults"
fi

# Step 3: Start Redis
echo "[3/5] Starting Redis..."
systemctl enable redis-server
systemctl restart redis-server
sleep 2
if redis-cli ping 2>/dev/null | grep -q PONG; then
    echo "  ✅ Redis is running (PING → PONG)"
else
    echo "  ❌ Redis failed to start"
    journalctl -u redis-server --no-pager -n 10
    exit 1
fi

# Step 4: Configure nami-core environment
echo "[4/5] Configuring nami-core to use Redis..."
NAMI_ENV="/opt/nami-core/.env"
REDIS_URL="redis://localhost:6379/0"

if [[ -f "$NAMI_ENV" ]]; then
    if grep -q "NAMI_REDIS_URL" "$NAMI_ENV"; then
        sed -i "s|NAMI_REDIS_URL=.*|NAMI_REDIS_URL=$REDIS_URL|" "$NAMI_ENV"
    else
        echo "NAMI_REDIS_URL=$REDIS_URL" >> "$NAMI_ENV"
    fi
else
    echo "NAMI_REDIS_URL=$REDIS_URL" > "$NAMI_ENV"
fi
echo "  ✅ NAMI_REDIS_URL=$REDIS_URL set in $NAMI_ENV"

# Also set in systemd override if exists
SYSTEMD_OVERRIDE="/etc/systemd/system/nami-core.service.d/override.conf"
mkdir -p /etc/systemd/system/nami-core.service.d/
if [[ -f "$SYSTEMD_OVERRIDE" ]]; then
    if grep -q "NAMI_REDIS_URL" "$SYSTEMD_OVERRIDE"; then
        sed -i "s|Environment=NAMI_REDIS_URL=.*|Environment=NAMI_REDIS_URL=$REDIS_URL|" "$SYSTEMD_OVERRIDE"
    else
        echo "Environment=NAMI_REDIS_URL=$REDIS_URL" >> "$SYSTEMD_OVERRIDE"
    fi
else
    cat > "$SYSTEMD_OVERRIDE" << EOF
[Service]
Environment=NAMI_REDIS_URL=$REDIS_URL
EOF
fi
systemctl daemon-reload
echo "  ✅ systemd override configured"

# Step 5: Restart nami-core and verify
echo "[5/5] Restarting nami-core and verifying..."
systemctl restart nami-core
sleep 5

if systemctl is-active nami-core &>/dev/null; then
    echo "  ✅ nami-core is running"
else
    echo "  ❌ nami-core failed to start"
    journalctl -u nami-core --no-pager -n 20
    exit 1
fi

# Verify Redis is being used
CACHE_STATS=$(curl -sf http://127.0.0.1:8092/cache 2>/dev/null || echo '{"error":"unreachable"}')
echo ""
echo "  Cache stats: $CACHE_STATS"
if echo "$CACHE_STATS" | grep -q '"redis"'; then
    echo "  ✅ Redis cache backend confirmed!"
else
    echo "  ⚠️  Cache backend not showing Redis — may need manual check"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Redis Setup Complete!                                       ║"
echo "║  Redis: redis://localhost:6379/0                             ║"
echo "║  Cache: verify at /cache endpoint                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
