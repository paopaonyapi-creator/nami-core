import json

import pytest

from nami_harness.brakes import BudgetGuard, CircuitBreaker, FileKillSwitch
from nami_harness.exceptions import BrakeEngaged, QualityGateFailed, RailDenied
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty
from nami_harness.rails import RailPolicy
from nami_harness.runtime import HarnessContext, HarnessRuntime
from nami_harness.sensors import JsonlSensor


def test_runtime_runs_task_through_all_harness_layers(tmp_path) -> None:
    runtime = HarnessRuntime(
        rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"summarize"}),
        quality=QualityGate([require_non_empty("answer")]),
        sensor=JsonlSensor(tmp_path / "events.jsonl"),
    )
    context = HarnessContext(agent="hermes", action="summarize", correlation_id="trace-1")

    result = runtime.run(context, {"input": "hello"}, lambda payload: {"answer": payload["input"].upper()})

    assert result.output == {"answer": "HELLO"}
    assert result.passed_quality is True
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [record["event_type"] for record in records] == [
        "harness.task.requested",
        "harness.task.started",
        "harness.task.completed",
    ]
    assert all(record["payload"]["correlation_id"] == "trace-1" for record in records)


def test_runtime_denies_agent_before_task_runs() -> None:
    runtime = HarnessRuntime(
        rails=RailPolicy(allowed_agents={"hermes"}),
        quality=QualityGate([require_non_empty("answer")]),
    )

    with pytest.raises(RailDenied):
        runtime.run(HarnessContext(agent="unknown", action="summarize"), {}, lambda payload: {"answer": "ok"})


def test_runtime_stops_when_kill_switch_is_engaged(tmp_path) -> None:
    kill_file = tmp_path / "kill"
    kill_file.write_text("stop", encoding="utf-8")
    runtime = HarnessRuntime(
        rails=RailPolicy(),
        quality=QualityGate([require_non_empty("answer")]),
        kill_switch=FileKillSwitch(kill_file),
    )

    with pytest.raises(BrakeEngaged):
        runtime.run(HarnessContext(agent="hermes", action="summarize"), {}, lambda payload: {"answer": "ok"})


def test_runtime_records_failure_and_opens_circuit_breaker(tmp_path) -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    runtime = HarnessRuntime(
        rails=RailPolicy(),
        quality=QualityGate([forbid_terms("secret")]),
        sensor=JsonlSensor(tmp_path / "events.jsonl"),
        circuit_breaker=breaker,
    )

    with pytest.raises(QualityGateFailed):
        runtime.run(HarnessContext(agent="hermes", action="draft"), {}, lambda payload: {"answer": "secret"})

    assert breaker.open() is True
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[-1]["event_type"] == "harness.task.failed"
    assert records[-1]["payload"]["error_type"] == "QualityGateFailed"


def test_runtime_records_stable_sensor_schema(tmp_path) -> None:
    runtime = HarnessRuntime(
        rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"summarize"}),
        quality=QualityGate([require_non_empty("answer")]),
        sensor=JsonlSensor(tmp_path / "events.jsonl"),
    )

    runtime.run(
        HarnessContext(agent="hermes", action="summarize", correlation_id="trace-1"),
        {"input": "hello"},
        lambda payload: {"answer": payload["input"]},
    )

    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[-1]["schema_version"] == "1.0"
    assert records[-1]["status"] == "success"
    assert records[-1]["agent"] == "hermes"
    assert records[-1]["action"] == "summarize"
    assert records[-1]["correlation_id"] == "trace-1"


def test_runtime_stops_when_budget_guard_would_exceed_budget() -> None:
    runtime = HarnessRuntime(
        rails=RailPolicy(),
        quality=QualityGate([require_non_empty("answer")]),
        budget_guard=BudgetGuard(max_cost=0.1),
    )

    with pytest.raises(BrakeEngaged):
        runtime.run(
            HarnessContext(agent="hermes", action="summarize", estimated_cost=0.2),
            {},
            lambda payload: {"answer": "ok"},
        )


def test_runtime_records_budget_spend_after_success() -> None:
    guard = BudgetGuard(max_cost=1.0)
    runtime = HarnessRuntime(
        rails=RailPolicy(),
        quality=QualityGate([require_non_empty("answer")]),
        budget_guard=guard,
    )

    runtime.run(
        HarnessContext(agent="hermes", action="summarize", estimated_cost=0.2),
        {},
        lambda payload: {"answer": "ok"},
    )

    assert guard.spent == 0.2
