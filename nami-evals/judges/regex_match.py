from __future__ import annotations

import re
from typing import Any


def score(actual: Any, expected: Any, case: dict[str, Any] | None = None) -> dict[str, Any]:
    text = actual if isinstance(actual, str) else str(actual)
    patterns = expected if isinstance(expected, list) else [expected]
    matched = 0
    for pattern in patterns:
        if re.search(str(pattern), text, flags=re.IGNORECASE | re.MULTILINE):
            matched += 1
    total = max(len(patterns), 1)
    value = matched / total
    return {"score": value, "passed": matched == total, "reason": f"matched {matched}/{total} regex patterns"}
