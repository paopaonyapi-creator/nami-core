"""Runtime API v2 primitives for Nami Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

PolicyDecision = Literal["allow", "require_api_key", "require_approval", "deny"]
PolicyCategory = Literal["read_only", "protected_read", "mutating", "dangerous", "admin_only"]
JobStatus = Literal["queued", "running", "completed", "failed"]
_READ_ONLY_ACTIONS = {
    "aggregate",
    "fetch",
    "fetch_results",
    "get",
    "health",
    "health_check",
    "list",
    "query",
    "read",
    "search",
    "status",
    "templates",
    "worker_health",
}
_PROTECTED_READ_ACTIONS = {"audit", "cache", "db", "metrics"}
_MUTATING_ACTIONS = {
    "batch",
    "export",
    "flush",
    "notify",
    "register",
    "reload",
    "send",
    "transform",
    "update",
    "write",
}
_DANGEROUS_ACTIONS = {"delete", "restart", "rotate_key", "shell"}


def classify_tool_action(worker: str, action: str) -> tuple[PolicyCategory, bool]:
    action_key = action.lower().replace("-", "_")
    if action_key in _DANGEROUS_ACTIONS:
        return "dangerous", False
    if action_key in _MUTATING_ACTIONS:
        return "mutating", False
    if action_key in _PROTECTED_READ_ACTIONS:
        return "protected_read", True
    if action_key in _READ_ONLY_ACTIONS or action_key.startswith(("get_", "list_", "fetch_", "read_", "search_")):
        return "read_only", True
    return "protected_read", True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    timestamp: str = field(default_factory=utc_now)
    job_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "job_id": self.job_id,
            "data": self.data,
        }


@dataclass(frozen=True)
class ToolMetadata:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission_level: PolicyCategory
    timeout_seconds: int
    audit_category: str
    read_only: bool
    worker: str | None = None
    action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "permission_level": self.permission_level,
            "timeout_seconds": self.timeout_seconds,
            "audit_category": self.audit_category,
            "read_only": self.read_only,
            "worker": self.worker,
            "action": self.action,
        }


@dataclass
class RuntimeJob:
    id: str
    status: JobStatus
    created_at: str
    updated_at: str
    requested_action: str
    input_summary: str
    progress_events: list[RuntimeEvent] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    audit_entries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, requested_action: str, input_summary: str) -> "RuntimeJob":
        now = utc_now()
        return cls(
            id=f"job_{uuid4().hex[:12]}",
            status="queued",
            created_at=now,
            updated_at=now,
            requested_action=requested_action,
            input_summary=input_summary,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "requested_action": self.requested_action,
            "input_summary": self.input_summary,
            "progress_events": [event.to_dict() for event in self.progress_events],
            "result": self.result,
            "error": self.error,
            "audit_entries": self.audit_entries,
        }


class RuntimeJobStore:
    def __init__(self, storage_path: str | None = None) -> None:
        self._jobs: dict[str, RuntimeJob] = {}
        self._storage_path = Path(storage_path) if storage_path else None
        self._load()

    def create(self, requested_action: str, input_summary: str) -> RuntimeJob:
        job = RuntimeJob.create(requested_action, input_summary)
        self.save(job)
        return job

    def save(self, job: RuntimeJob) -> None:
        self._jobs[job.id] = job
        self._flush()

    def list(self) -> list[RuntimeJob]:
        return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def get(self, job_id: str) -> RuntimeJob | None:
        return self._jobs.get(job_id)

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        for item in data.get("jobs", []):
            events = [RuntimeEvent(**event) for event in item.get("progress_events", [])]
            item = {**item, "progress_events": events}
            self._jobs[item["id"]] = RuntimeJob(**item)

    def _flush(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"jobs": [job.to_dict() for job in self.list()]}
        self._storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}

    def register(self, tool: ToolMetadata) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list(self) -> list[ToolMetadata]:
        return sorted(self._tools.values(), key=lambda tool: tool.name)

    def get(self, name: str) -> ToolMetadata | None:
        return self._tools.get(name)

    @classmethod
    def from_hermes(cls, hermes: Any) -> "ToolRegistry":
        registry = cls()
        if hermes is None:
            return registry
        for worker in sorted(hermes.list_workers()):
            actions = sorted(hermes.worker_actions(worker))
            for action in actions:
                name = f"{worker}.{action}"
                permission_level, read_only = classify_tool_action(worker, action)
                registry.register(ToolMetadata(
                    name=name,
                    description=f"Dispatch Nami worker '{worker}' action '{action}'.",
                    input_schema={"type": "object", "additionalProperties": True},
                    output_schema={"type": "object", "additionalProperties": True},
                    permission_level=permission_level,
                    timeout_seconds=30,
                    audit_category="worker_dispatch",
                    read_only=read_only,
                    worker=worker,
                    action=action,
                ))
        return registry


class ExecutionPolicy:
    @staticmethod
    def decide(tool: ToolMetadata, authenticated: bool) -> PolicyDecision:
        if tool.permission_level == "read_only":
            return "allow"
        if tool.permission_level == "protected_read":
            return "allow" if authenticated else "require_api_key"
        if tool.permission_level == "mutating":
            return "require_approval"
        if tool.permission_level in {"dangerous", "admin_only"}:
            return "deny"
        return "deny"
