from __future__ import annotations

from typing import Any


def score(actual: Any, expected: Any, case: dict[str, Any] | None = None) -> dict[str, Any]:
    passed = actual == expected
    return {"score": 1.0 if passed else 0.0, "passed": passed, "reason": "exact match" if passed else "actual did not equal expected"}
