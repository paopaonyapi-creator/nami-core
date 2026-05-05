from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .brakes import BudgetGuard, CircuitBreaker, FileKillSwitch
from .quality import QualityGate
from .rails import RailPolicy
from .sensors import JsonlSensor

Task = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class HarnessContext:
    agent: str
    action: str
    estimated_cost: float = 0.0
    correlation_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class HarnessResult:
    context: HarnessContext
    output: dict[str, Any]
    passed_quality: bool


@dataclass
class HarnessRuntime:
    rails: RailPolicy
    quality: QualityGate
    sensor: JsonlSensor | None = None
    kill_switch: FileKillSwitch | None = None
    circuit_breaker: CircuitBreaker | None = None
    budget_guard: BudgetGuard | None = None

    def run(self, context: HarnessContext, payload: dict[str, Any], task: Task) -> HarnessResult:
        self._record("harness.task.requested", context, {"payload_keys": sorted(payload.keys())})
        self.rails.assert_allowed(agent=context.agent, action=context.action)
        self._assert_brakes_open(context)
        self._record("harness.task.started", context, {"agent": context.agent, "action": context.action})

        try:
            output = task(payload)
            self.quality.assert_passes(output)
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            if self.budget_guard:
                self.budget_guard.record_spend(context.estimated_cost)
            self._record("harness.task.completed", context, {"output_keys": sorted(output.keys())})
            return HarnessResult(context=context, output=output, passed_quality=True)
        except Exception as error:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            self._record("harness.task.failed", context, {"error_type": type(error).__name__, "error": str(error)})
            raise

    def _assert_brakes_open(self, context: HarnessContext) -> None:
        if self.kill_switch:
            self.kill_switch.assert_open()
        if self.circuit_breaker:
            self.circuit_breaker.assert_closed()
        if self.budget_guard:
            self.budget_guard.assert_within_budget(context.estimated_cost)

    def _record(self, event_type: str, context: HarnessContext, payload: dict[str, Any]) -> None:
        if not self.sensor:
            return
        event_payload = {
            "correlation_id": context.correlation_id,
            "agent": context.agent,
            "action": context.action,
            **payload,
        }
        status = "error" if event_type.endswith(".failed") else "success" if event_type.endswith(".completed") else "info"
        self.sensor.record(
            event_type,
            event_payload,
            status=status,
            agent=context.agent,
            action=context.action,
            correlation_id=context.correlation_id,
        )
