#!/usr/bin/env bash
# Setup dashboard authentication with nginx auth_basic
# Usage:
#   DASHBOARD_USER=<user> DASHBOARD_PASS=<pass> bash setup_dashboard_auth.sh
#   OR positional: bash setup_dashboard_auth.sh <user> <password>
# Both env vars and positional args are supported; env vars take precedence.

set -e

USER="${DASHBOARD_USER:-${1:-}}"
PASS="${DASHBOARD_PASS:-${2:-}}"
HTPASSWD="/etc/nami-harness/dashboard.htpasswd"

if [ -z "$USER" ] || [ -z "$PASS" ]; then
    echo "ERROR: username and password required" >&2
    echo "Usage: DASHBOARD_USER=<user> DASHBOARD_PASS=<pass> bash setup_dashboard_auth.sh" >&2
    exit 1
fi

echo "Setting up dashboard auth for user: $USER"

# Install apache2-utils if needed (for htpasswd)
if ! command -v htpasswd &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq apache2-utils
fi

# Create htpasswd file
# Create htpasswd file
# Permissions: dir 755 so nginx (www-data) can traverse, file 640 root:www-data so nginx can read
mkdir -p /etc/nami-harness
chmod 755 /etc/nami-harness
htpasswd -cb "$HTPASSWD" "$USER" "$PASS"
chmod 640 "$HTPASSWD"
chown root:www-data "$HTPASSWD"

echo "Created $HTPASSWD"

# Patch nginx landing config to add auth_basic on dashboard
NGINX_CONF="/etc/nginx/conf.d/nami-landing.conf"
if [ ! -f "$NGINX_CONF" ]; then
    NGINX_CONF="/etc/nginx/sites-enabled/nami-landing"
fi

# Add auth_basic directives if not already present
if ! grep -q "auth_basic" "$NGINX_CONF"; then
    sed -i '/location \/ {/a\        auth_basic "Nami Dashboard";\n        auth_basic_user_file /etc/nami-harness/dashboard.htpasswd;' "$NGINX_CONF"
    echo "Added auth_basic to $NGINX_CONF"
else
    echo "auth_basic already configured in $NGINX_CONF"
fi

# Also protect the API dashboard proxy
NGINX_API="/etc/nginx/conf.d/nami-api.conf"
if [ -f "$NGINX_API" ] && ! grep -q "auth_basic" "$NGINX_API"; then
    # Only protect /ws and specific endpoints, not /health or /webhook
    # Add auth for /metrics endpoint
    sed -i '/location \/ {/i\    location /metrics {\n        auth_basic "Nami Metrics";\n        auth_basic_user_file /etc/nami-harness/dashboard.htpasswd;\n        proxy_pass http://127.0.0.1:8092;\n        proxy_set_header Host $host;\n    }\n' "$NGINX_API"
    echo "Added auth_basic for /metrics in $NGINX_API"
fi

nginx -t && systemctl reload nginx

echo ""
echo "=== Dashboard Auth Setup Complete ==="
echo "User: $USER"
echo "Password: (set via env var, not displayed)"
echo "Credentials stored in $HTPASSWD"
echo "Dashboard URL: https://nami.178.104.181.132.nip.io/dashboard.html"
