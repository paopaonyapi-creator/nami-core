#!/usr/bin/env python3
"""Setup Grafana datasource and dashboard."""
import urllib.request, json, base64, sys

GRAFANA = "http://127.0.0.1:3030"
AUTH = base64.b64encode(b"admin:nami2026").decode()

def api(method, path, data=None):
    url = f"{GRAFANA}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Basic {AUTH}",
    }, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

# Add Prometheus datasource
print("Adding Prometheus datasource...")
code, resp = api("POST", "/api/datasources", {
    "name": "Prometheus",
    "type": "prometheus",
    "url": "http://127.0.0.1:9090",
    "access": "proxy",
    "isDefault": True,
})
print(f"  Datasource: {code} - {resp.get('message', resp.get('id', 'ok'))}")

# Create Nami Core dashboard
print("Creating Nami Core dashboard...")
dashboard = {
    "dashboard": {
        "title": "Nami Core",
        "tags": ["nami"],
        "timezone": "browser",
        "refresh": "10s",
        "panels": [
            {
                "id": 1, "title": "Request Rate", "type": "stat",
                "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
                "targets": [{"expr": "rate(nami_core_requests_total[5m])", "refId": "A"}],
            },
            {
                "id": 2, "title": "Dispatch Rate", "type": "stat",
                "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
                "targets": [{"expr": "rate(nami_core_dispatch_total[5m])", "refId": "A"}],
            },
            {
                "id": 3, "title": "Error Rate", "type": "stat",
                "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
                "targets": [{"expr": "rate(nami_core_dispatch_errors_total[5m])", "refId": "A"}],
            },
            {
                "id": 4, "title": "Workers", "type": "stat",
                "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
                "targets": [{"expr": "nami_core_workers_count", "refId": "A"}],
            },
            {
                "id": 5, "title": "Avg Latency (ms)", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
                "targets": [{"expr": "nami_core_dispatch_latency_avg_ms", "refId": "A"}],
            },
            {
                "id": 6, "title": "P95 Latency (ms)", "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
                "targets": [{"expr": "nami_core_dispatch_latency_p95_ms", "refId": "A"}],
            },
        ],
    },
    "overwrite": True,
}
code, resp = api("POST", "/api/dashboards/db", dashboard)
print(f"  Dashboard: {code} - {resp.get('message', resp.get('id', 'ok'))}")

print("\nDone! Grafana URL: https://grafana.178.104.181.132.nip.io")
