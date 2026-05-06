"""Cache manager — Redis-backed caching with fallback to in-memory."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("nami_core.cache")

REDIS_URL = os.environ.get("NAMI_REDIS_URL", "")
CACHE_TTL = int(os.environ.get("NAMI_CACHE_TTL", "300"))  # 5 min default

# In-memory fallback
_memory_cache: dict[str, tuple[float, Any]] = {}
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL:
        return None
    try:
        import redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis connected: %s", REDIS_URL)
        return _redis_client
    except Exception as exc:
        logger.warning("Redis unavailable, using in-memory cache: %s", exc)
        _redis_client = None
        return None


def get(key: str) -> Any | None:
    """Get cached value by key."""
    r = _get_redis()
    if r:
        try:
            val = r.get(f"nami:{key}")
            if val:
                return json.loads(val)
        except Exception:
            pass
        return None

    # In-memory fallback
    entry = _memory_cache.get(key)
    if entry:
        ts, val = entry
        if time.time() - ts < CACHE_TTL:
            return val
        del _memory_cache[key]
    return None


def set(key: str, value: Any, ttl: int | None = None) -> None:
    """Set cached value with TTL."""
    ttl = ttl or CACHE_TTL
    r = _get_redis()
    if r:
        try:
            r.setex(f"nami:{key}", ttl, json.dumps(value, default=str))
            return
        except Exception:
            pass

    # In-memory fallback
    _memory_cache[key] = (time.time(), value)
    # Evict expired entries
    now = time.time()
    expired = [k for k, (ts, _) in _memory_cache.items() if now - ts > CACHE_TTL]
    for k in expired:
        del _memory_cache[k]


def delete(key: str) -> None:
    """Delete cached value."""
    r = _get_redis()
    if r:
        try:
            r.delete(f"nami:{key}")
        except Exception:
            pass
    _memory_cache.pop(key, None)


def flush() -> None:
    """Flush all nami cache entries."""
    r = _get_redis()
    if r:
        try:
            for key in r.scan_iter("nami:*"):
                r.delete(key)
        except Exception:
            pass
    _memory_cache.clear()


def stats() -> dict[str, Any]:
    """Get cache statistics."""
    r = _get_redis()
    if r:
        try:
            keys = list(r.scan_iter("nami:*"))
            return {"backend": "redis", "keys": len(keys), "connected": True}
        except Exception:
            pass
    return {"backend": "memory", "keys": len(_memory_cache), "connected": False}
