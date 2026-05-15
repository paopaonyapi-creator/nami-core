"""ULID generation utilities (no external dependency)."""

from __future__ import annotations

import os
import time

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_base32(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_CROCKFORD32[rem])
    return "".join(reversed(chars)).rjust(length, "0")


def generate_ulid(timestamp_ms: int | None = None) -> str:
    """Generate a 26-character ULID using timestamp + randomness."""
    ts_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    ts_encoded = _encode_base32(ts_ms, 10)
    random_bits = int.from_bytes(os.urandom(10), "big")
    rand_encoded = _encode_base32(random_bits, 16)
    return f"{ts_encoded}{rand_encoded}"


__all__ = ["generate_ulid"]
