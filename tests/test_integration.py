"""Integration tests — full API round-trip via TestClient with mock Hermes."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from nami_core.app import create_app
from nami_core.hermes import Hermes
from nami_harness.runtime import HarnessRuntime, HarnessResult, HarnessContext


def _make_app():
    """Build a real app with Hermes + workers + mock scheduler."""
    from nami_core.scheduler import build_core
    hermes, scheduler = build_core(config_dir="config")
    return create_app(hermes=hermes, scheduler=scheduler, api_key="test-integration-key")


@pytest.fixture(scope="module")
def client():
    app = _make_app()
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer test-integration-key"}


# === Health & Info ===

def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert len(d["workers"]) >= 18

def test_workers_endpoint(client):
    r = client.get("/workers")
    assert r.status_code == 200
    names = [w["name"] for w in r.json()["workers"]]
    assert "email" in names
    assert "relay" in names
    assert "pipeline" in names

def test_scheduler_endpoint(client):
    r = client.get("/scheduler")
    assert r.status_code == 200
    assert "jobs" in r.json()

def test_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    d = r.json()
    assert "nami_core_dispatch_total" in d or "uptime_seconds" in d

def test_prometheus_metrics_endpoint(client):
    r = client.get("/metrics/prometheus")
    assert r.status_code == 200
    assert "nami_" in r.text


# === Dispatch ===

def test_dispatch_default_echo(client):
    r = client.post("/dispatch", json={"worker": "default", "action": "echo", "payload": {"msg": "hello"}}, headers=AUTH)
    assert r.status_code == 200

def test_dispatch_no_auth(client):
    r = client.post("/dispatch", json={"worker": "default", "action": "echo", "payload": {}})
    assert r.status_code in (401, 403)

def test_dispatch_wrong_auth(client):
    r = client.post("/dispatch", json={"worker": "default", "action": "echo", "payload": {}}, headers={"Authorization": "Bearer wrong-key"})
    assert r.status_code in (401, 403)


# === Pipeline Worker Integration ===

def test_dispatch_pipeline_transform(client):
    r = client.post("/dispatch", json={"worker": "pipeline", "action": "transform", "payload": {"data": {"a": 1}, "steps": [{"op": "add", "field": "b", "value": 2}]}}, headers=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True or "result" in d

def test_dispatch_pipeline_aggregate(client):
    r = client.post("/dispatch", json={"worker": "pipeline", "action": "aggregate", "payload": {"data": [10, 20, 30], "operation": "avg"}}, headers=AUTH)
    assert r.status_code == 200

def test_dispatch_pipeline_export(client):
    r = client.post("/dispatch", json={"worker": "pipeline", "action": "export", "payload": {"data": {"key": "val"}, "format": "json"}}, headers=AUTH)
    assert r.status_code == 200


# === Relay Worker Integration ===

def test_dispatch_relay_register(client):
    r = client.post("/dispatch", json={"worker": "relay", "action": "register", "payload": {"url": "http://example.com/hook", "event": "dispatch"}}, headers=AUTH)
    assert r.status_code == 200


# === Email Worker Integration ===

def test_dispatch_email_templates(client):
    r = client.post("/dispatch", json={"worker": "email", "action": "templates", "payload": {"action": "templates"}}, headers=AUTH)
    assert r.status_code == 200
    d = r.json()
    # Hermes wraps output: {ok, output: {...}}
    out = d.get("output", d)
    assert "templates" in out or d.get("ok") is True


# === Audit ===

def test_audit_endpoint(client):
    r = client.get("/audit", headers=AUTH)
    assert r.status_code == 200
    assert "entries" in r.json()

def test_audit_no_auth(client):
    """Audit trail is public read (no auth) for dashboard."""
    r = client.get("/audit")
    assert r.status_code == 200
    assert "entries" in r.json()


# === Webhook ===

def test_webhook_endpoint(client):
    r = client.post("/webhook", json={"source": "test", "event": "ping", "data": {"ts": 123}})
    assert r.status_code == 200


# === WebSocket ===

def test_websocket_connect(client):
    with client.websocket_connect("/ws"):
        pass


# === OpenAPI ===

def test_openapi_spec(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    d = r.json()
    assert "/dispatch" in d["paths"]
    assert "/audit" in d["paths"]
    assert "/rotate-key" in d["paths"]
