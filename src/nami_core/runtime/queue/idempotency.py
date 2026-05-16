"""Idempotency helpers for async job dispatch."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_payload(payload: dict[str, Any]) -> str:
    """Return a deterministic JSON string for payload hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def idempotency_key(action: str, payload: dict[str, Any]) -> str:
    canonical = canonical_payload(payload)
    raw = f"{action}:{canonical}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


__all__ = ["canonical_payload", "idempotency_key"]
