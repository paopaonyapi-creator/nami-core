from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .exceptions import QualityGateFailed

QualityCheck = Callable[[dict[str, Any]], str | None]


def require_non_empty(field: str) -> QualityCheck:
    def check(payload: dict[str, Any]) -> str | None:
        value = payload.get(field)
        if value is None or value == "":
            return f"required field is empty: {field}"
        return None

    return check


def forbid_terms(*terms: str) -> QualityCheck:
    lowered_terms = tuple(term.lower() for term in terms)

    def check(payload: dict[str, Any]) -> str | None:
        text = "\n".join(str(value) for value in payload.values()).lower()
        for term in lowered_terms:
            if term in text:
                return f"forbidden term found: {term}"
        return None

    return check


@dataclass
class QualityGate:
    checks: list[QualityCheck]

    def validate(self, payload: dict[str, Any]) -> list[str]:
        failures: list[str] = []
        for check in self.checks:
            failure = check(payload)
            if failure:
                failures.append(failure)
        return failures

    def assert_passes(self, payload: dict[str, Any]) -> None:
        failures = self.validate(payload)
        if failures:
            raise QualityGateFailed("; ".join(failures))
