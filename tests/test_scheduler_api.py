"""Integration tests for nami-core FastAPI application."""
import json
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from nami_harness.runtime import HarnessRuntime, HarnessResult, HarnessContext

from nami_core.app import create_app, Metrics
from nami_core.hermes import Hermes


class _MockScheduler:
    def status(self):
        return {"running": True, "jobs": 6, "last_runs": {}}


class TestFastAPIApp(unittest.TestCase):
    """Test the FastAPI HTTP + WebSocket endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.hermes = Hermes()
        mock_runtime = MagicMock(spec=HarnessRuntime)
        mock_ctx = HarnessContext(agent="hermes", action="echo", estimated_cost=0, correlation_id="")
        mock_runtime.run.return_value = HarnessResult(context=mock_ctx, output={"echo": "pong"}, passed_quality=True)
        cls.hermes.register("test", mock_runtime, lambda p: {"echo": p})

        cls.scheduler = _MockScheduler()
        cls.app = create_app(hermes=cls.hermes, scheduler=cls.scheduler, api_key="test-key-123")
        cls.client = TestClient(cls.app)

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "nami-core")
        self.assertIn("test", data["workers"])

    def test_workers_endpoint(self):
        resp = self.client.get("/workers")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(any(w["name"] == "test" for w in data["workers"]))

    def test_scheduler_endpoint(self):
        resp = self.client.get("/scheduler")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["running"])
        self.assertEqual(data["jobs"], 6)

    def test_metrics_endpoint(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("nami_core_requests_total", data)
        self.assertIn("nami_core_workers_count", data)

    def test_prometheus_metrics_endpoint(self):
        resp = self.client.get("/metrics/prometheus")
        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertIn("# TYPE nami_core_requests_total counter", text)
        self.assertIn("nami_core_workers_count", text)
        # SAFETY §7.3: nami_safety_detection_total must be exposed even when
        # no detector has fired yet (stable schema for scrapers).
        self.assertIn("# TYPE nami_safety_detection_total counter", text)
        self.assertIn("nami_safety_detection_total", text)

    def test_dispatch_no_auth_returns_401(self):
        resp = self.client.post("/dispatch", json={"worker": "test", "action": "echo"})
        self.assertEqual(resp.status_code, 401)

    def test_dispatch_with_auth_returns_200(self):
        resp = self.client.post("/dispatch",
            json={"worker": "test", "action": "echo", "payload": {"msg": "hi"}},
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("latency_ms", data)

    def test_dispatch_missing_worker_returns_422(self):
        resp = self.client.post("/dispatch",
            json={"action": "echo"},
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(resp.status_code, 422)

    def test_dispatch_unknown_worker_returns_404(self):
        resp = self.client.post("/dispatch",
            json={"worker": "nonexistent", "action": "echo"},
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(resp.status_code, 404)

    def test_webhook_endpoint(self):
        resp = self.client.post("/webhook", json={"source": "ci", "event": "deploy"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["source"], "ci")
        self.assertEqual(data["event"], "deploy")

    def test_openapi_spec(self):
        resp = self.client.get("/openapi.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("paths", data)
        self.assertIn("/health", data["paths"])
        self.assertIn("/dispatch", data["paths"])

    def test_docs_page(self):
        resp = self.client.get("/docs")
        self.assertEqual(resp.status_code, 200)

    def test_rotate_key(self):
        resp = self.client.post("/rotate-key",
            json={"new_key": "new-key-456"},
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])

        # Old key should no longer work
        resp2 = self.client.post("/dispatch",
            json={"worker": "test", "action": "echo"},
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(resp2.status_code, 401)

        # New key should work
        resp3 = self.client.post("/dispatch",
            json={"worker": "test", "action": "echo"},
            headers={"Authorization": "Bearer new-key-456"})
        self.assertEqual(resp3.status_code, 200)

    def test_audit_trail(self):
        # Dispatch first to create audit entry
        self.client.post("/dispatch",
            json={"worker": "test", "action": "echo"},
            headers={"Authorization": "Bearer test-key-123"})
        resp = self.client.get("/audit",
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("entries", data)

    def test_audit_is_public_read(self):
        """Audit trail is public read (no auth) for dashboard."""
        resp = self.client.get("/audit")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("entries", resp.json())

    def test_rate_limit_on_dispatch(self):
        # Reset rate limiter by creating fresh app
        fresh_app = create_app(hermes=self.hermes, scheduler=self.scheduler, api_key="test-key-123")
        fresh_client = TestClient(fresh_app)
        hit_429 = False
        for i in range(70):
            resp = fresh_client.post("/dispatch",
                json={"worker": "test", "action": "echo"},
                headers={"Authorization": "Bearer test-key-123"})
            if resp.status_code == 429:
                hit_429 = True
                break
        self.assertTrue(hit_429, "Expected 429 rate limit after 60+ dispatches")

    def test_websocket_connect(self):
        with self.client.websocket_connect("/ws") as ws:
            # Just verify connection works
            pass  # Connection established successfully


if __name__ == "__main__":
    unittest.main()
