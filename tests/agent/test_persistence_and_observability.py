"""Phase 27 PR-B follow-up: persistence + observability tests.

Validates:
  - AgentLoop calls traces_dao.insert_step for every emitted step
  - cost_span / record_cost_metric receive `role="agent"` accumulations
  - DAO failures don't crash the loop (best-effort persistence)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nami_core.agent import (
    AgentLoop,
    AgentState,
    AgentStep,
    PlanDecision,
    RecursionBudget,
)
from nami_core.runtime.obs.cost_span import (
    cost_metrics_prometheus_lines,
    reset_cost_metrics,
)


@dataclass
class FakeTracesDAO:
    """Captures insert_step calls; no Postgres required."""

    inserts: list[tuple[AgentState, AgentStep, int]] = field(default_factory=list)
    raise_on_insert: bool = False

    def insert_step(self, state: AgentState, step: AgentStep, step_index: int) -> bool:
        if self.raise_on_insert:
            raise RuntimeError("simulated DB failure")
        self.inserts.append((state, step, step_index))
        return True


@dataclass
class ScriptedPlanner:
    decisions: list[PlanDecision] = field(default_factory=list)
    _calls: int = 0

    def plan(self, state: AgentState) -> PlanDecision:
        idx = min(self._calls, len(self.decisions) - 1)
        self._calls += 1
        return self.decisions[idx]


def _state() -> AgentState:
    return AgentState(
        job_id="job-d1",
        trace_id="00-aaaa-bbbb-01",
        parent_id=None,
        goal="dao test",
    )


# ─── persistence ───────────────────────────────────────────────────────


def test_dao_receives_each_step() -> None:
    dao = FakeTracesDAO()
    planner = ScriptedPlanner(
        decisions=[
            PlanDecision(action="tool", tool="echo", tool_args={"a": 1}, reasoning="x", cost_usd=0.01),
            PlanDecision(action="done", final_answer="ok", reasoning="y", cost_usd=0.005),
        ]
    )
    AgentLoop(planner=planner, traces_dao=dao).run(_state())

    kinds = [step.kind for _, step, _ in dao.inserts]
    assert kinds == ["plan", "act", "observe", "plan"]
    indices = [idx for _, _, idx in dao.inserts]
    assert indices == [0, 1, 2, 3]


def test_dao_failure_does_not_crash_loop() -> None:
    """Best-effort persistence per RUNTIME §9 SLO note.

    The loop swallows DB errors (logged as warnings via DAO impl) — but
    our FakeTracesDAO raises, so the loop should propagate the error
    OR the DAO should swallow internally. Real AgentTracesDAO swallows
    inside insert_step. Fake here lets the exception escape; test
    documents that AgentLoop relies on the DAO contract to swallow.
    """
    import pytest

    dao = FakeTracesDAO(raise_on_insert=True)
    planner = ScriptedPlanner(
        decisions=[PlanDecision(action="done", final_answer="ok", reasoning="x")]
    )
    # FakeTracesDAO raises -> error escapes. This pins the contract:
    # production DAOs must catch internally.
    with pytest.raises(RuntimeError, match="simulated DB failure"):
        AgentLoop(planner=planner, traces_dao=dao).run(_state())


def test_real_dao_insert_step_swallows_db_failure() -> None:
    """AgentTracesDAO.insert_step returns False on connect failure, never raises."""
    from nami_core.agent.dao import AgentTracesDAO

    state = _state()
    step = AgentStep(kind="plan", content="x")
    # Unreachable DB; connect_timeout=1 keeps the test fast on Windows.
    dao = AgentTracesDAO(
        dsn="postgresql://nobody:nobody@127.0.0.1:65535/nodb?connect_timeout=1"
    )
    assert dao.insert_step(state, step, 0) is False


def test_loop_without_dao_runs_normally() -> None:
    planner = ScriptedPlanner(
        decisions=[PlanDecision(action="done", final_answer="ok", reasoning="x")]
    )
    outcome = AgentLoop(planner=planner, traces_dao=None).run(_state())
    assert outcome.halted is False
    assert outcome.final_answer == "ok"


# ─── OTel cost recording ───────────────────────────────────────────────


def test_loop_records_cost_metric_for_agent_role() -> None:
    reset_cost_metrics()
    planner = ScriptedPlanner(
        decisions=[
            PlanDecision(
                action="tool",
                tool="echo",
                tool_args={},
                reasoning="x",
                cost_usd=0.123,
                tokens_in=100,
                tokens_out=50,
            ),
            PlanDecision(
                action="done",
                final_answer="ok",
                reasoning="y",
                cost_usd=0.077,
                tokens_in=30,
                tokens_out=20,
            ),
        ]
    )
    AgentLoop(planner=planner).run(_state())

    lines = "\n".join(cost_metrics_prometheus_lines())
    assert 'nami_cost_usd_total{role="agent"}' in lines
    # 0.123 + 0.077 = 0.200, allow rounding
    assert 'nami_cost_usd_total{role="agent"} 0.2' in lines
    assert 'nami_tokens_in_total{role="agent"} 130' in lines
    assert 'nami_tokens_out_total{role="agent"} 70' in lines


def test_loop_skips_cost_record_when_zero() -> None:
    reset_cost_metrics()
    planner = ScriptedPlanner(
        decisions=[PlanDecision(action="done", final_answer="ok", reasoning="x")]
    )
    AgentLoop(planner=planner).run(_state())
    lines = "\n".join(cost_metrics_prometheus_lines())
    # When all steps are zero-cost, no agent role should appear (the
    # role-key is only registered after a non-zero record_cost_metric).
    assert 'nami_cost_usd_total{role="agent"}' not in lines


def test_budget_halt_records_halt_step_to_dao() -> None:
    dao = FakeTracesDAO()
    planner = ScriptedPlanner(
        decisions=[
            PlanDecision(
                action="tool",
                tool="echo",
                tool_args={},
                reasoning="overspend",
                cost_usd=10.0,  # > $5 cap
            )
        ]
    )
    outcome = AgentLoop(planner=planner, traces_dao=dao, budget=RecursionBudget()).run(_state())
    assert outcome.halted is True
    halt_inserts = [step for _, step, _ in dao.inserts if step.kind == "halt"]
    assert len(halt_inserts) == 1
    assert halt_inserts[0].error == "budget_exceeded:cost_usd"


# ─── env-driven worker selection (light sanity, no real gateway) ───────


def test_worker_falls_back_to_echo_when_planner_env_set() -> None:
    import os

    from nami_workers.agent_worker import EchoPlanner, _select_planner

    prev = os.environ.get("NAMI_AGENT_PLANNER")
    os.environ["NAMI_AGENT_PLANNER"] = "echo"
    try:
        planner = _select_planner()
        assert isinstance(planner, EchoPlanner)
    finally:
        if prev is None:
            os.environ.pop("NAMI_AGENT_PLANNER", None)
        else:
            os.environ["NAMI_AGENT_PLANNER"] = prev


def test_worker_persist_disabled_returns_none_dao() -> None:
    import os

    from nami_workers.agent_worker import _select_traces_dao

    prev = os.environ.get("NAMI_AGENT_PERSIST")
    os.environ.pop("NAMI_AGENT_PERSIST", None)
    try:
        assert _select_traces_dao() is None
    finally:
        if prev is not None:
            os.environ["NAMI_AGENT_PERSIST"] = prev
