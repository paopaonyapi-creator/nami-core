#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  Nami Core — One-Shot VPS Setup                              ║
# ║  Run this on the VPS to install everything in one go         ║
# ║                                                              ║
# ║  Usage:                                                      ║
# ║    bash deploy/vps-setup.sh                                  ║
# ║    bash deploy/vps-setup.sh --shadow   (alongside existing)  ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

SHADOW_MODE=false
if [[ "${1:-}" == "--shadow" ]]; then
    SHADOW_MODE=true
fi

DEPLOY_DIR="/opt/nami-core"
LOG_DIR="/var/log/nami-harness"
BACKUP_DIR="/opt/backup/nami-core-$(date +%Y%m%d-%H%M%S)"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Nami Core — One-Shot VPS Setup                             ║"
echo "║  Shadow mode: $SHADOW_MODE                                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ─── Step 1: Clone repo ─────────────────────────────────────────
echo "[1/8] Cloning nami-core from GitHub..."
if [[ -d "$DEPLOY_DIR" ]]; then
    echo "  Already exists, pulling latest..."
    cd "$DEPLOY_DIR" && git pull
else
    git clone https://github.com/paopaonyapi-creator/nami-core.git "$DEPLOY_DIR"
fi

# ─── Step 2: Create directories ────────────────────────────────
echo "[2/8] Creating directories..."
mkdir -p "$LOG_DIR"
mkdir -p "$BACKUP_DIR"

# ─── Step 3: Setup Python venv ─────────────────────────────────
echo "[3/8] Setting up Python environment..."
cd "$DEPLOY_DIR"
if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -e ".[dev]" --quiet

# ─── Step 4: Discover real VPS code ─────────────────────────────
echo "[4/8] Discovering real VPS service code..."
echo ""
echo "  Services found:"
for dir in /opt/telegram-premium /opt/maxplus-proxy /opt/hanoi-bot /opt/laopatana-stat-lab /opt/nami-bot /opt/gold-signal-os /opt/nami-api-gateway /opt/nami-status-api /opt/nami-bridge /opt/graphify-http; do
    if [[ -d "$dir" ]]; then
        PY_COUNT=$(find "$dir" -name "*.py" -type f 2>/dev/null | wc -l)
        echo "    ✅ $dir ($PY_COUNT Python files)"
    else
        echo "    ❌ $dir (not found)"
    fi
done
echo ""

# ─── Step 5: Extract real code into workers ─────────────────────
echo "[5/8] Extracting real code into workers..."
WORKERS_DIR="$DEPLOY_DIR/src/nami_workers"

# --- Signal Worker ---
if [[ -f "/opt/telegram-premium/bot.py" ]]; then
    echo "  Extracting signal logic from /opt/telegram-premium/bot.py..."
    # Find the signal generation function and AI call logic
    SIGNAL_SRC="/opt/telegram-premium/bot.py"
    # Copy relevant functions
    grep -n "def.*signal\|def.*generate\|def.*send.*signal\|def.*ai\|def.*call_ai\|def.*openrouter\|def.*chat_completion" "$SIGNAL_SRC" 2>/dev/null | head -20 || true
fi

# --- Proxy Worker ---
if [[ -f "/opt/maxplus-proxy/proxy.py" ]]; then
    echo "  Extracting proxy logic from /opt/maxplus-proxy/proxy.py..."
    PROXY_SRC="/opt/maxplus-proxy/proxy.py"
    grep -n "def.*chat\|def.*completion\|def.*model\|def.*embed\|def.*fallback\|def.*provider" "$PROXY_SRC" 2>/dev/null | head -20 || true
fi

# --- Lottery Worker ---
for dir in /opt/hanoi-bot /opt/laopatana-stat-lab; do
    if [[ -d "$dir" ]]; then
        echo "  Found lottery code in $dir"
        find "$dir" -name "*.py" -exec grep -l "predict\|lottery\|kqxs\|scraper" {} \; 2>/dev/null | head -5 || true
    fi
done

# --- Bot Worker ---
if [[ -f "/opt/nami-bot/nami_bot.py" ]]; then
    echo "  Extracting bot logic from /opt/nami-bot/nami_bot.py..."
    grep -n "def.*help\|def.*status\|def.*package\|def.*subscribe\|def.*command" "/opt/nami-bot/nami_bot.py" 2>/dev/null | head -20 || true
fi

# --- Trading Worker ---
if [[ -d "/opt/gold-signal-os" ]]; then
    echo "  Extracting trading logic from /opt/gold-signal-os..."
    find "/opt/gold-signal-os" -name "*.py" -exec grep -l "trade\|oanda\|signal\|paper" {} \; 2>/dev/null | head -5 || true
fi

# --- Gateway Worker ---
if [[ -d "/opt/nami-api-gateway" ]]; then
    echo "  Extracting gateway logic from /opt/nami-api-gateway..."
    find "/opt/nami-api-gateway" -name "*.py" -exec grep -l "route\|api\|auth\|gateway" {} \; 2>/dev/null | head -5 || true
fi

# --- Status Worker ---
if [[ -d "/opt/nami-status-api" ]]; then
    echo "  Extracting status logic from /opt/nami-status-api..."
    find "/opt/nami-status-api" -name "*.py" -exec grep -l "health\|status\|check" {} \; 2>/dev/null | head -5 || true
fi

# --- Bridge Worker ---
if [[ -d "/opt/nami-bridge" ]]; then
    echo "  Extracting bridge logic from /opt/nami-bridge..."
    find "/opt/nami-bridge" -name "*.py" -exec grep -l "websocket\|relay\|bridge\|subscribe" {} \; 2>/dev/null | head -5 || true
fi

# --- Graphify Worker ---
if [[ -d "/opt/graphify-http" ]]; then
    echo "  Extracting graphify logic from /opt/graphify-http..."
    find "/opt/graphify-http" -name "*.py" -exec grep -l "neo4j\|graph\|query\|cypher" {} \; 2>/dev/null | head -5 || true
fi

echo ""
echo "  ⚠️  Automatic extraction is discovery-only."
echo "  Manual step: Copy real logic from the files above into worker files."
echo "  Worker files are in: $WORKERS_DIR"
echo ""

# ─── Step 6: Run tests ──────────────────────────────────────────
echo "[6/8] Running tests..."
cd "$DEPLOY_DIR"
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -5
echo ""

# ─── Step 7: Install systemd units ──────────────────────────────
echo "[7/8] Installing systemd units..."
cp "$DEPLOY_DIR/deploy/systemd/nami-core.service" /etc/systemd/system/
cp "$DEPLOY_DIR/deploy/systemd/nami-worker@.service" /etc/systemd/system/
systemctl daemon-reload
echo "  ✅ systemd units installed"

# ─── Step 8: Start services ─────────────────────────────────────
echo "[8/8] Starting services..."

if [[ "$SHADOW_MODE" == "true" ]]; then
    echo ""
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║  SHADOW MODE                                        ║"
    echo "  ║  Nami Core installed alongside existing services    ║"
    echo "  ║  No existing services were stopped                 ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo ""
    systemctl enable nami-core.service
    systemctl start nami-core.service
    echo "  Verify: systemctl status nami-core"
    echo "  Logs:   journalctl -u nami-core -f"
else
    echo ""
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║  SWITCH-OVER MODE                                   ║"
    echo "  ║  Nami Core installed and started                   ║"
    echo "  ║  Old services still running — stop manually        ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo ""
    systemctl enable nami-core.service
    systemctl start nami-core.service

    # Install nginx config
    cp "$DEPLOY_DIR/deploy/nginx/nami-core.conf" /etc/nginx/sites-available/
    ln -sf /etc/nginx/sites-available/nami-core.conf /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
    echo "  ✅ nginx configured"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Setup Complete!                                             ║"
echo "║                                                              ║"
echo "║  Next steps:                                                 ║"
echo "║  1. Copy real logic from /opt/* into worker files            ║"
echo "║  2. Run: pytest (verify all tests pass)                      ║"
echo "║  3. Compare outputs with old services for 3 days             ║"
echo "║  4. Switch over when verified                                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
