#!/usr/bin/env bash
# Setup Prometheus + Grafana monitoring stack on VPS
# Usage: bash setup-monitoring.sh

set -e

echo "=== Setting up Prometheus + Grafana ==="

# Install Prometheus
if ! command -v prometheus &>/dev/null; then
    echo "Installing Prometheus..."
    PROM_VERSION="2.52.0"
    cd /tmp
    wget -q "https://github.com/prometheus/prometheus/releases/download/v${PROM_VERSION}/prometheus-${PROM_VERSION}.linux-amd64.tar.gz"
    tar xzf prometheus-${PROM_VERSION}.linux-amd64.tar.gz
    cp prometheus-${PROM_VERSION}.linux-amd64/prometheus /usr/local/bin/
    cp prometheus-${PROM_VERSION}.linux-amd64/promtool /usr/local/bin/
    mkdir -p /etc/prometheus /var/lib/prometheus
fi

# Prometheus config
cat > /etc/prometheus/prometheus.yml <<'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'nami-core'
    scheme: https
    metrics_path: /metrics/prometheus
    static_configs:
      - targets: ['nami-api.178.104.181.132.nip.io']
    tls_config:
      insecure_skip_verify: true
EOF

# Prometheus systemd service
cat > /etc/systemd/system/prometheus.service <<EOF
[Unit]
Description=Prometheus
After=network.target

[Service]
Type=simple
User=prometheus
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/var/lib/prometheus/ --web.listen-address=127.0.0.1:9090
Restart=always

[Install]
WantedBy=multi-user.target
EOF

id -u prometheus &>/dev/null || useradd -r -s /bin/false prometheus
chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus
systemctl daemon-reload
systemctl enable prometheus
systemctl restart prometheus
echo "Prometheus started on :9090"

# Install Grafana
if ! command -v grafana-server &>/dev/null; then
    echo "Installing Grafana..."
    apt-get install -y -qq apt-transport-https software-properties-common
    wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
    echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list
    apt-get update -qq
    apt-get install -y -qq grafana
fi

# Configure Grafana to listen on 127.0.0.1 (nginx will proxy)
sed -i 's/;http_addr =/http_addr = 127.0.0.1/' /etc/grafana/grafana.ini 2>/dev/null || true

systemctl enable grafana-server
systemctl restart grafana-server
echo "Grafana started on :3000"

# Nginx proxy for Grafana
if ! grep -q "grafana" /etc/nginx/conf.d/*.conf 2>/dev/null; then
    cat > /etc/nginx/conf.d/grafana.conf <<EOF
server {
    listen 443 ssl;
    server_name grafana.178.104.181.132.nip.io;

    ssl_certificate /etc/letsencrypt/live/178.104.181.132.nip.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/178.104.181.132.nip.io/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}

server {
    listen 80;
    server_name grafana.178.104.181.132.nip.io;
    return 301 https://\$host\$request_uri;
}
EOF
    nginx -t && systemctl reload nginx
    echo "Grafana nginx proxy configured"
fi

# Setup Grafana datasource + dashboard via API
sleep 5
GRAFANA_USER="admin"
GRAFANA_PASS="admin"

# Add Prometheus datasource
curl -s -u "${GRAFANA_USER}:${GRAFANA_PASS}" http://127.0.0.1:3000/api/datasources \
    -X POST -H "Content-Type: application/json" \
    -d '{"name":"Prometheus","type":"prometheus","url":"http://127.0.0.1:9090","access":"proxy"}' || true

# Create Nami dashboard
DASHBOARD_JSON='{
  "dashboard": {
    "title": "Nami Core",
    "tags": ["nami"],
    "panels": [
      {"title":"Request Rate","type":"stat","gridPos":{"h":4,"w":6,"x":0,"y":0},"targets":[{"expr":"rate(nami_core_requests_total[5m])"}]},
      {"title":"Dispatch Rate","type":"stat","gridPos":{"h":4,"w":6,"x":6,"y":0},"targets":[{"expr":"rate(nami_core_dispatch_total[5m])"}]},
      {"title":"Error Rate","type":"stat","gridPos":{"h":4,"w":6,"x":12,"y":0},"targets":[{"expr":"rate(nami_core_dispatch_errors_total[5m])"}]},
      {"title":"Workers","type":"stat","gridPos":{"h":4,"w":6,"x":18,"y":0},"targets":[{"expr":"nami_core_workers_count"}]},
      {"title":"Avg Latency (ms)","type":"graph","gridPos":{"h":8,"w":12,"x":0,"y":4},"targets":[{"expr":"nami_core_dispatch_latency_avg_ms"}]},
      {"title":"P95 Latency (ms)","type":"graph","gridPos":{"h":8,"w":12,"x":12,"y":4},"targets":[{"expr":"nami_core_dispatch_latency_p95_ms"}]}
    ],
    "refresh": "10s"
  },
  "overwrite": true
}'

curl -s -u "${GRAFANA_USER}:${GRAFANA_PASS}" http://127.0.0.1:3000/api/dashboards/db \
    -X POST -H "Content-Type: application/json" \
    -d "$DASHBOARD_JSON" || true

echo ""
echo "=== Monitoring Setup Complete ==="
echo "Prometheus: http://127.0.0.1:9090"
echo "Grafana:    https://grafana.178.104.181.132.nip.io"
echo "Default Grafana login: admin / admin"
echo "Dashboard: Nami Core (auto-created)"
