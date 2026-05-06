"""Tests for Redis pub/sub module."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from nami_core.pubsub import publish, start_subscriber, stop_subscriber, CHANNEL


class TestPubSubPublish:
    """Test publish function with and without Redis."""

    def test_publish_no_redis(self):
        """Publish should not error when Redis is unavailable."""
        with patch.dict(os.environ, {}, clear=True):
            # Force re-init
            import nami_core.pubsub as ps
            ps._redis_client = None
            publish("test", {"foo": "bar"})  # should not raise

    def test_publish_with_mock_redis(self):
        """Publish should call Redis when available."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.publish.return_value = 1
        import nami_core.pubsub as ps
        ps._redis_client = mock_redis
        publish("dispatch", {"worker": "test"})
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == CHANNEL
        payload = json.loads(call_args[0][1])
        assert payload["event"] == "dispatch"
        # Cleanup
        ps._redis_client = None


class TestPubSubSubscriber:
    """Test subscriber module-level functions."""

    def test_stop_subscriber_is_safe(self):
        """stop_subscriber should be safe to call even if never started."""
        stop_subscriber()  # should not raise

    def test_subscriber_module_import(self):
        """Module should import cleanly."""
        import nami_core.pubsub as ps
        assert hasattr(ps, "publish")
        assert hasattr(ps, "start_subscriber")
        assert hasattr(ps, "stop_subscriber")
        assert ps.CHANNEL == "nami:events"
