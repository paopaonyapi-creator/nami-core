from __future__ import annotations

from typing import Any


def score(actual: Any, expected: Any, case: dict[str, Any] | None = None) -> dict[str, Any]:
    rubric = (case or {}).get("rubric") or {}
    required = rubric.get("must_include") or expected.get("must_include") if isinstance(expected, dict) else []
    forbidden = rubric.get("must_not_include") or expected.get("must_not_include") if isinstance(expected, dict) else []
    text = actual if isinstance(actual, str) else str(actual)
    lowered = text.lower()
    required_hits = sum(1 for item in required if str(item).lower() in lowered)
    forbidden_hits = sum(1 for item in forbidden if str(item).lower() in lowered)
    total = max(len(required) + len(forbidden), 1)
    value = (required_hits + (len(forbidden) - forbidden_hits)) / total
    passed = required_hits == len(required) and forbidden_hits == 0
    return {
        "score": round(value, 3),
        "passed": passed,
        "reason": f"deterministic rubric required={required_hits}/{len(required)} forbidden_hits={forbidden_hits}",
    }
