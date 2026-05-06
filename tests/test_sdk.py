"""Tests for Nami SDK — sync client and WS listener."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch, MagicMock

import pytest

from nami_sdk.client import NamiClient
from nami_sdk.async_client import NamiAsyncClient, NamiWSListener


# === Sync NamiClient ===

class TestNamiClient:
    def setup_method(self) -> None:
        self.client = NamiClient(base_url="http://localhost:8092", api_key="test-key")

    def _mock_urlopen(self, data):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_headers_no_key(self) -> None:
        c = NamiClient(base_url="http://localhost:8092")
        assert "Authorization" not in c._headers()

    def test_headers_with_key(self) -> None:
        assert self.client._headers()["Authorization"] == "Bearer test-key"

    def test_health(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"status": "ok", "workers": []})):
            assert self.client.health()["status"] == "ok"

    def test_workers(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"workers": [{"name": "test"}]})):
            assert len(self.client.workers()) == 1

    def test_dispatch(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"ok": True})):
            assert self.client.dispatch("default", "echo")["ok"] is True

    def test_webhook(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"ok": True})):
            assert self.client.webhook("test", "ping")["ok"] is True

    def test_audit(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"entries": []})):
            assert "entries" in self.client.audit()

    def test_rotate_key(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"ok": True, "new_key": "abc"})):
            assert self.client.rotate_key("new-abc")["ok"] is True

    def test_scheduler_run_now(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"ok": True})):
            assert self.client.scheduler_run_now("status:health")["ok"] is True

    def test_cron_schedule(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"ok": True, "job_id": 1})):
            assert self.client.cron_schedule("default", "echo", "2099-01-01T00:00:00")["ok"] is True

    def test_cron_list(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"ok": True, "jobs": []})):
            assert self.client.cron_list()["ok"] is True

    def test_cron_cancel(self) -> None:
        with patch("nami_sdk.client.urlopen", return_value=self._mock_urlopen({"ok": True})):
            assert self.client.cron_cancel(1)["ok"] is True

    def test_prometheus_metrics(self) -> None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"nami_dispatch_total 5\n"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("nami_sdk.client.urlopen", return_value=mock_resp):
            assert "nami_dispatch_total" in self.client.prometheus_metrics()

    def test_post_error_handling(self) -> None:
        from urllib.error import HTTPError
        mock_err = HTTPError("http://test", 429, "Too Many Requests", {}, None)
        mock_err.read = lambda: b'{"detail":"rate limited"}'
        with patch("nami_sdk.client.urlopen", side_effect=mock_err):
            assert self.client.dispatch("default", "echo")["status"] == 429


# === Async NamiAsyncClient ===

class TestNamiAsyncClient:
    def test_init(self) -> None:
        try:
            client = NamiAsyncClient(base_url="http://localhost:8092", api_key="test")
            assert client.base_url == "http://localhost:8092"
        except ImportError:
            pytest.skip("httpx not installed")

    def test_async_health(self) -> None:
        try:
            client = NamiAsyncClient(base_url="http://localhost:8092", api_key="test")
        except ImportError:
            pytest.skip("httpx not installed")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "get", return_value=mock_response):
            result = asyncio.run(client.health())
            assert result["status"] == "ok"
            asyncio.run(client.close())

    def test_async_dispatch(self) -> None:
        try:
            client = NamiAsyncClient(base_url="http://localhost:8092", api_key="test")
        except ImportError:
            pytest.skip("httpx not installed")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "post", return_value=mock_response):
            result = asyncio.run(client.dispatch("default", "echo"))
            assert result["ok"] is True
            asyncio.run(client.close())


# === WS Listener ===

class TestNamiWSListener:
    def test_listener_init(self) -> None:
        listener = NamiWSListener(
            base_url="ws://localhost:8092/ws",
            on_dispatch=lambda d: None,
            on_webhook=lambda d: None,
        )
        assert listener.base_url == "ws://localhost:8092/ws"
        assert listener.on_dispatch is not None
        assert listener._retry_delay == 3.0

    def test_listener_stop(self) -> None:
        listener = NamiWSListener()
        listener.stop()
        assert listener._running is False
