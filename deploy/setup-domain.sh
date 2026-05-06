#!/usr/bin/env bash
# Setup permanent domain for Nami ecosystem
# Usage: bash setup-domain.sh <domain>
# Example: bash setup-domain.sh namipro.com
#
# Prerequisites:
#   1. Own the domain and point DNS A record to 178.104.181.132
#   2. Wait for DNS propagation (check: dig +short <domain>)
#
# This script:
#   - Generates SSL cert via certbot/let's encrypt
#   - Creates nginx configs for the domain
#   - Updates dashboard API URL

set -e

DOMAIN="${1:?Usage: bash setup-domain.sh <domain>}"
VPS_IP="178.104.181.132"
HOMEDIR="/opt/nami-core"

echo "=== Setting up domain: $DOMAIN ==="

# Check DNS
RESOLVED=$(dig +short "$DOMAIN" 2>/dev/null | head -1)
if [ "$RESOLVED" != "$VPS_IP" ]; then
    echo "WARNING: $DOMAIN does not resolve to $VPS_IP (got: $RESOLVED)"
    echo "Make sure DNS A record points to $VPS_IP before continuing."
    echo "Press Ctrl+C to abort, or Enter to continue anyway..."
    read -r
fi

# Install certbot if needed
if ! command -v certbot &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq certbot python3-certbot-nginx
fi

# Generate SSL cert
echo "Obtaining SSL certificate..."
certbot certonly --nginx -d "$DOMAIN" -d "api.$DOMAIN" --non-interactive --agree-tos --email admin@"$DOMAIN" || {
    echo "Certbot failed. Trying standalone mode..."
    certbot certonly --standalone -d "$DOMAIN" -d "api.$DOMAIN" --non-interactive --agree-tos --email admin@"$DOMAIN"
}

SSL_CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
SSL_KEY="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

if [ ! -f "$SSL_CERT" ]; then
    echo "ERROR: SSL cert not found at $SSL_CERT"
    exit 1
fi

echo "SSL cert obtained: $SSL_CERT"

# Create nginx config for main site (dashboard + landing)
cat > /etc/nginx/conf.d/"$DOMAIN".conf <<EOF
server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate $SSL_CERT;
    ssl_certificate_key $SSL_KEY;

    root /opt/nami-landing;
    index index.html;

    gzip on;
    gzip_vary on;
    gzip_comp_level 6;
    gzip_min_length 256;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        try_files \$uri \$uri/ =404;
        auth_basic "Nami Dashboard";
        auth_basic_user_file /etc/nami-harness/dashboard.htpasswd;
    }
}

server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}
EOF

# Create nginx config for API subdomain
cat > /etc/nginx/conf.d/api."$DOMAIN".conf <<EOF
server {
    listen 443 ssl http2;
    server_name api.$DOMAIN;

    ssl_certificate $SSL_CERT;
    ssl_certificate_key $SSL_KEY;

    location /ws {
        proxy_pass http://127.0.0.1:8093;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location /metrics {
        auth_basic "Nami Metrics";
        auth_basic_user_file /etc/nami-harness/dashboard.htpasswd;
        proxy_pass http://127.0.0.1:8092;
        proxy_set_header Host \$host;
    }

    location / {
        proxy_pass http://127.0.0.1:8092;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }
}

server {
    listen 80;
    server_name api.$DOMAIN;
    return 301 https://\$host\$request_uri;
}
EOF

# Test and reload nginx
nginx -t && systemctl reload nginx

echo ""
echo "=== Domain Setup Complete ==="
echo "Dashboard: https://$DOMAIN/dashboard.html"
echo "API:       https://api.$DOMAIN/health"
echo "WebSocket: wss://api.$DOMAIN/ws"
echo ""
echo "To update dashboard API URL, edit /opt/nami-landing/dashboard.html"
echo "Change const API to: https://api.$DOMAIN"
echo "Change const WS_URL to: wss://api.$DOMAIN/ws"
