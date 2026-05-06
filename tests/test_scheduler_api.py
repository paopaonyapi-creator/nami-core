"""Integration tests for nami-core scheduler API."""
import json
import threading
import time
import unittest
from http.server import HTTPServer
from unittest.mock import MagicMock, patch

from nami_core.hermes import Hermes
from nami_core.scheduler import NamiAPIHandler, NamiScheduler


class _MockScheduler:
    def status(self):
        return {"running": True, "jobs": 6, "last_runs": {}}


class TestSchedulerAPI(unittest.TestCase):
    """Test the HTTP API endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.hermes = Hermes()
        # Register a simple test worker with mock runtime
        def test_worker(payload):
            return {"echo": payload}
        from nami_harness.runtime import HarnessRuntime, HarnessResult, HarnessContext
        mock_runtime = MagicMock(spec=HarnessRuntime)
        mock_ctx = HarnessContext(agent="hermes", action="echo", estimated_cost=0, correlation_id="")
        mock_runtime.run.return_value = HarnessResult(context=mock_ctx, output={"echo": "pong"}, passed_quality=True)
        cls.hermes.register("test", mock_runtime, test_worker)

        NamiAPIHandler.hermes = cls.hermes
        NamiAPIHandler.scheduler = _MockScheduler()
        NamiAPIHandler.api_key = "test-key-123"

        cls.server = HTTPServer(("127.0.0.1", 0), NamiAPIHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path):
        import urllib.request
        req = urllib.request.Request(self._url(path))
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path, data, headers=None):
        import urllib.request
        body = json.dumps(data).encode("utf-8")
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(self._url(path), data=body, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_health_endpoint(self):
        data = self._get("/health")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "nami-core")
        self.assertIn("test", data["workers"])

    def test_workers_endpoint(self):
        data = self._get("/workers")
        self.assertTrue(any(w["name"] == "test" for w in data["workers"]))

    def test_scheduler_endpoint(self):
        data = self._get("/scheduler")
        self.assertTrue(data["running"])
        self.assertEqual(data["jobs"], 6)

    def test_metrics_endpoint(self):
        data = self._get("/metrics")
        self.assertIn("nami_core_requests_total", data)
        self.assertIn("nami_core_workers_count", data)
        self.assertEqual(data["nami_core_workers_count"], 1)

    def test_dispatch_no_auth_returns_401(self):
        code, data = self._post("/dispatch", {"worker": "test", "action": "echo"})
        self.assertEqual(code, 401)
        self.assertEqual(data["error"], "unauthorized")

    def test_dispatch_with_auth_returns_200(self):
        code, data = self._post("/dispatch",
            {"worker": "test", "action": "echo", "payload": {"msg": "hi"}},
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertIn("latency_ms", data)

    def test_dispatch_missing_worker_returns_400(self):
        code, data = self._post("/dispatch",
            {"action": "echo"},
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(code, 400)

    def test_dispatch_unknown_worker_returns_404(self):
        code, data = self._post("/dispatch",
            {"worker": "nonexistent", "action": "echo"},
            headers={"Authorization": "Bearer test-key-123"})
        self.assertEqual(code, 404)

    def test_webhook_endpoint(self):
        code, data = self._post("/webhook", {"source": "ci", "event": "deploy"})
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["source"], "ci")
        self.assertEqual(data["event"], "deploy")

    def test_cors_options(self):
        import urllib.request
        req = urllib.request.Request(self._url("/dispatch"), method="OPTIONS")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")


if __name__ == "__main__":
    unittest.main()
