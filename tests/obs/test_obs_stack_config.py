from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_grafana_datasources_are_provisioned():
    config = yaml.safe_load((ROOT / "obs/grafana/provisioning/datasources/datasources.yml").read_text(encoding="utf-8"))
    datasources = {item["uid"]: item for item in config["datasources"]}

    assert datasources["prometheus"]["url"] == "http://prometheus:9090"
    assert datasources["loki"]["url"] == "http://loki:3100"
    assert datasources["tempo"]["url"] == "http://tempo:3200"
    assert datasources["prometheus"]["isDefault"] is True


def test_grafana_dashboard_provider_points_to_mounted_dashboard_dir():
    config = yaml.safe_load((ROOT / "obs/grafana/provisioning/dashboards/dashboards.yml").read_text(encoding="utf-8"))
    provider = config["providers"][0]

    assert provider["type"] == "file"
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"


def test_obs_compose_binds_external_ports_to_loopback_and_mounts_provisioning():
    config = yaml.safe_load((ROOT / "docker-compose.obs.yml").read_text(encoding="utf-8"))
    services = config["services"]

    for service in ("prometheus", "loki", "tempo", "grafana"):
        for port in services[service].get("ports", []):
            assert str(port).startswith("127.0.0.1:")

    grafana_volumes = services["grafana"]["volumes"]
    assert "./obs/grafana/provisioning:/etc/grafana/provisioning:ro" in grafana_volumes


def test_dashboards_reference_provisioned_prometheus_metrics():
    expected_metrics = {
        "nami_core_dispatch_total",
        "nami_core_dispatch_errors_total",
        "nami_core_dispatch_latency_avg_ms",
        "nami_core_dispatch_latency_p95_ms",
        "nami_core_workers_count",
        "nami_core_scheduler_running",
        "nami_core_scheduler_jobs",
        "nami_bridge_calls_total",
        "nami_cost_usd_total",
        "nami_tokens_in_total",
        "nami_tokens_out_total",
        "nami_cost_spans_total",
    }
    dashboards = sorted((ROOT / "obs/grafana/dashboards").glob("*.json"))
    assert dashboards

    observed = set()
    for path in dashboards:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        for panel in dashboard.get("panels", []):
            assert panel.get("datasource", {}).get("uid") == "prometheus"
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                for metric in expected_metrics:
                    if metric in expr:
                        observed.add(metric)

    assert "nami_cost_usd_total" in observed
    assert "nami_core_dispatch_total" in observed
    assert observed <= expected_metrics
