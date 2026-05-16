"""Shared types for the async job queue."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass(frozen=True)
class JobBudget:
    max_retries: int = 3
    max_seconds: int = 300
    max_tokens: int = 50_000


@dataclass(frozen=True)
class JobMessage:
    id: str
    action: str
    payload: dict[str, Any]
    idempotency_key: str
    trace_id: str
    parent_id: str | None
    budget: JobBudget
    enqueued_at: str
    attempt: int = 1

    def to_stream_fields(self) -> dict[str, str]:
        return {
            "id": self.id,
            "action": self.action,
            "payload": _dump_json(self.payload),
            "idempotency_key": self.idempotency_key,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id or "",
            "budget": _dump_json(asdict(self.budget)),
            "enqueued_at": self.enqueued_at,
            "attempt": str(self.attempt),
        }

    @classmethod
    def from_stream_fields(cls, fields: dict[str, str]) -> "JobMessage":
        return cls(
            id=fields["id"],
            action=fields["action"],
            payload=_load_json(fields.get("payload") or "{}"),
            idempotency_key=fields["idempotency_key"],
            trace_id=fields.get("trace_id") or "",
            parent_id=fields.get("parent_id") or None,
            budget=JobBudget(**_load_json(fields.get("budget") or "{}")),
            enqueued_at=fields.get("enqueued_at") or _utc_now(),
            attempt=int(fields.get("attempt") or 1),
        )


@dataclass(frozen=True)
class TaskInput:
    job_id: str
    action: str
    payload: dict[str, Any]
    trace_id: str
    parent_id: str | None
    budget: JobBudget
    attempt: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "action": self.action,
            "payload": self.payload,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "budget": asdict(self.budget),
            "attempt": self.attempt,
        }


@dataclass(frozen=True)
class TaskOutput:
    status: Literal["ok", "error"]
    result: dict[str, Any] | None = None
    error: str | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, default=str)


def _load_json(raw: str) -> dict[str, Any]:
    import json

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


__all__ = [
    "JobBudget",
    "JobMessage",
    "TaskInput",
    "TaskOutput",
]
