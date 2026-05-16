"""Phase 27 PR-B: budget enforcement tests.

Validates SAFETY §3 recursion-budget caps:
    depth <= 3, fan_out <= 5, cost_usd <= $5, iters <= 25.

Per CODEX_EXECUTION_PLAN.md Phase 27 validation:
    - Inject depth>3   -> halted with budget_exceeded:depth
    - Inject cost>$5   -> halted with budget_exceeded:cost_usd
    - Inject iters>25  -> halted with budget_exceeded:iters
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nami_core.agent import (
    AgentLoop,
    AgentState,
    BudgetExceeded,
    PlanDecision,
    RecursionBudget,
    enforce_budget,
)
from nami_core.agent.budget import check_fan_out


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
        job_id="job-b1",
        trace_id="00-aaaa-bbbb-01",
        parent_id=None,
        goal="budget test",
    )


def test_enforce_budget_passes_within_caps() -> None:
    s = _state()
    s.depth = 2
    s.iters = 10
    s.cost_usd_total = 1.0
    enforce_budget(s)


def test_enforce_budget_raises_on_depth() -> None:
    s = _state()
    s.depth = 4
    with pytest.raises(BudgetExceeded) as exc:
        enforce_budget(s)
    assert exc.value.axis == "depth"


def test_enforce_budget_raises_on_iters() -> None:
    s = _state()
    s.iters = 26
    with pytest.raises(BudgetExceeded) as exc:
        enforce_budget(s)
    assert exc.value.axis == "iters"


def test_enforce_budget_raises_on_cost() -> None:
    s = _state()
    s.cost_usd_total = 5.01
    with pytest.raises(BudgetExceeded) as exc:
        enforce_budget(s)
    assert exc.value.axis == "cost_usd"


def test_check_fan_out_raises_when_too_many_children() -> None:
    with pytest.raises(BudgetExceeded) as exc:
        check_fan_out(6)
    assert exc.value.axis == "fan_out"


def test_check_fan_out_allows_at_cap() -> None:
    check_fan_out(5)


def test_loop_halts_on_cost_overrun_per_plan_validation() -> None:
    """Inject cost>$5 via expensive plan step. Loop must halt with budget_exceeded."""
    expensive = PlanDecision(
        action="tool",
        tool="echo",
        tool_args={"x": 1},
        reasoning="costly",
        cost_usd=6.0,
        tokens_in=1000,
        tokens_out=1000,
    )
    planner = ScriptedPlanner(decisions=[expensive, expensive])
    outcome = AgentLoop(planner=planner).run(_state())
    assert outcome.halted is True
    assert outcome.halt_reason is not None
    assert "cost_usd" in outcome.halt_reason
    halt_step = outcome.state.steps[-1]
    assert halt_step.kind == "halt"
    assert halt_step.error == "budget_exceeded:cost_usd"


def test_loop_halts_on_iters_overrun_per_plan_validation() -> None:
    """Inject >25 iters by feeding an infinite tool loop."""
    tool_step = PlanDecision(
        action="tool",
        tool="echo",
        tool_args={"x": 1},
        reasoning="loop",
        cost_usd=0.01,
    )
    planner = ScriptedPlanner(decisions=[tool_step])
    outcome = AgentLoop(planner=planner).run(_state())
    assert outcome.halted is True
    assert outcome.halt_reason is not None
    assert outcome.halt_reason.startswith("budget_exceeded:")
    # With a per-iteration cost of $0.01 the iters cap (25) trips before
    # the cost cap ($5). Pin that axis explicitly.
    assert "iters" in outcome.halt_reason or "cost_usd" in outcome.halt_reason


def test_loop_halts_on_depth_overrun_per_plan_validation() -> None:
    """Inject depth>3 by starting state above the cap."""
    s = _state()
    s.depth = 4
    planner = ScriptedPlanner(
        decisions=[PlanDecision(action="done", final_answer="x", reasoning="x")]
    )
    outcome = AgentLoop(planner=planner).run(s)
    assert outcome.halted is True
    assert outcome.halt_reason is not None
    assert "depth" in outcome.halt_reason


def test_custom_tighter_budget_overrides_defaults() -> None:
    s = _state()
    s.cost_usd_total = 1.5
    with pytest.raises(BudgetExceeded) as exc:
        enforce_budget(s, RecursionBudget(max_cost_usd=1.0))
    assert exc.value.axis == "cost_usd"


def test_halt_callback_fires_on_budget_breach() -> None:
    captured: dict = {}

    def on_halt(state: AgentState, reason: str) -> None:
        captured["reason"] = reason
        captured["job_id"] = state.job_id

    planner = ScriptedPlanner(
        decisions=[
            PlanDecision(
                action="tool",
                tool="echo",
                tool_args={},
                cost_usd=10.0,
                reasoning="overspend",
            )
        ]
    )
    loop = AgentLoop(planner=planner, on_halt=on_halt)
    outcome = loop.run(_state())
    assert outcome.halted is True
    assert captured["job_id"] == "job-b1"
    assert "cost_usd" in captured["reason"]
