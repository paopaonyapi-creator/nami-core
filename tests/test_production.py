"""Tests for cache module and new production endpoints."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest


# === Cache Module ===

def test_cache_memory_get_set() -> None:
    from nami_core.cache import set as cache_set, get as cache_get, _memory_cache
    _memory_cache.clear()
    cache_set("test_key", {"data": 123}, ttl=60)
    result = cache_get("test_key")
    assert result == {"data": 123}

def test_cache_memory_miss() -> None:
    from nami_core.cache import get as cache_get, _memory_cache
    _memory_cache.clear()
    assert cache_get("nonexistent") is None

def test_cache_memory_delete() -> None:
    from nami_core.cache import set as cache_set, get as cache_get, delete as cache_del, _memory_cache
    _memory_cache.clear()
    cache_set("del_key", "value", ttl=60)
    cache_del("del_key")
    assert cache_get("del_key") is None

def test_cache_memory_flush() -> None:
    from nami_core.cache import set as cache_set, flush as cache_flush, _memory_cache
    _memory_cache.clear()
    cache_set("k1", "v1", ttl=60)
    cache_set("k2", "v2", ttl=60)
    cache_flush()
    assert len(_memory_cache) == 0

def test_cache_stats_memory() -> None:
    from nami_core.cache import stats, _memory_cache, _redis_client
    _memory_cache.clear()
    # Force memory backend
    import nami_core.cache as mod
    old_client = mod._redis_client
    mod._redis_client = None
    try:
        s = stats()
        assert s["backend"] == "memory"
    finally:
        mod._redis_client = old_client

def test_cache_redis_fallback() -> None:
    from nami_core.cache import _get_redis
    # No REDIS_URL set → should return None
    os.environ.pop("NAMI_REDIS_URL", None)
    import nami_core.cache as mod
    mod._redis_client = None
    assert _get_redis() is None


# === Production Endpoints (via TestClient) ===

def test_cache_endpoint() -> None:
    from nami_core.app import create_app
    from nami_core.hermes import Hermes
    from nami_harness.runtime import HarnessRuntime, HarnessResult, HarnessContext
    from fastapi.testclient import TestClient

    hermes = Hermes()
    mock_runtime = MagicMock(spec=HarnessRuntime)
    mock_ctx = HarnessContext(agent="hermes", action="echo", estimated_cost=0, correlation_id="")
    mock_runtime.run.return_value = HarnessResult(context=mock_ctx, output={"echo": "pong"}, passed_quality=True)
    hermes.register("test", mock_runtime, lambda p: {"echo": p})

    app = create_app(hermes=hermes, scheduler=None, api_key="test-key")
    client = TestClient(app)

    r = client.get("/cache", headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200
    assert "backend" in r.json()

def test_cache_flush_endpoint() -> None:
    from nami_core.app import create_app
    from nami_core.hermes import Hermes
    from nami_harness.runtime import HarnessRuntime, HarnessResult, HarnessContext
    from fastapi.testclient import TestClient

    hermes = Hermes()
    mock_runtime = MagicMock(spec=HarnessRuntime)
    mock_ctx = HarnessContext(agent="hermes", action="echo", estimated_cost=0, correlation_id="")
    mock_runtime.run.return_value = HarnessResult(context=mock_ctx, output={"echo": "pong"}, passed_quality=True)
    hermes.register("test", mock_runtime, lambda p: {"echo": p})

    app = create_app(hermes=hermes, scheduler=None, api_key="test-key")
    client = TestClient(app)

    r = client.post("/cache/flush", headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

def test_reload_workers_endpoint() -> None:
    from nami_core.app import create_app
    from nami_core.hermes import Hermes
    from nami_harness.runtime import HarnessRuntime, HarnessResult, HarnessContext
    from fastapi.testclient import TestClient

    hermes = Hermes()
    mock_runtime = MagicMock(spec=HarnessRuntime)
    mock_ctx = HarnessContext(agent="hermes", action="echo", estimated_cost=0, correlation_id="")
    mock_runtime.run.return_value = HarnessResult(context=mock_ctx, output={"echo": "pong"}, passed_quality=True)
    hermes.register("test", mock_runtime, lambda p: {"echo": p})

    app = create_app(hermes=hermes, scheduler=None, api_key="test-key")
    client = TestClient(app)

    r = client.post("/reload-workers", headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
