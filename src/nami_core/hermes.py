"""Hermes — the brain / agentic workforce router.

Hermes receives tasks, decides which worker to dispatch them to,
and routes through the Harness runtime for safety and quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from nami_harness.runtime import HarnessContext, HarnessResult, HarnessRuntime

Task = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class WorkerEntry:
    name: str
    runtime: HarnessRuntime
    task: Task
    actions: set[str] = field(default_factory=set)


class Hermes:
    """Task router and dispatcher.

    Hermes owns the routing logic: given an agent and action,
    it finds the right worker, builds a HarnessContext, and
    runs the task through that worker's HarnessRuntime.
    """

    def __init__(self) -> None:
        self._workers: dict[str, WorkerEntry] = {}

    def register(
        self,
        name: str,
        runtime: HarnessRuntime,
        task: Task,
        actions: set[str] | None = None,
    ) -> None:
        if name in self._workers:
            raise ValueError(f"worker already registered: {name}")
        self._workers[name] = WorkerEntry(
            name=name,
            runtime=runtime,
            task=task,
            actions=actions or set(),
        )

    def dispatch(
        self,
        worker_name: str,
        action: str,
        payload: dict[str, Any],
        *,
        agent: str = "hermes",
        estimated_cost: float = 0.0,
        correlation_id: str | None = None,
    ) -> HarnessResult:
        if worker_name not in self._workers:
            raise ValueError(f"unknown worker: {worker_name}")

        entry = self._workers[worker_name]

        context = HarnessContext(
            agent=agent,
            action=action,
            estimated_cost=estimated_cost,
            correlation_id=correlation_id or "",
        )

        # Inject action into payload so worker tasks (which receive only the
        # payload dict) can route on it without relying on caller convention.
        # An explicit `action` already in payload wins (caller override).
        merged_payload: dict[str, Any] = {"action": action, **payload}

        return entry.runtime.run(context, merged_payload, entry.task)

    def list_workers(self) -> list[str]:
        return list(self._workers.keys())

    def worker_actions(self, name: str) -> set[str]:
        if name not in self._workers:
            raise ValueError(f"unknown worker: {name}")
        return self._workers[name].actions
