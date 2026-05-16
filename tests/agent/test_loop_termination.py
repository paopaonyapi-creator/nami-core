"""Phase 27 PR-B: agent loop termination tests.

Validates the RUNTIME §7 happy-path: plan -> act -> observe -> done.
Uses a fake planner so tests are offline + deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nami_core.agent import (
    AgentLoop,
    AgentState,
    PlanDecision,
    RecursionBudget,
    ToolRegistry,
    default_registry,
)
from nami_core.agent.loop import Planner


@dataclass
class ScriptedPlanner:
    """Returns scripted PlanDecisions in order. Cycles on the last entry."""

    decisions: list[PlanDecision] = field(default_factory=list)
    _calls: int = 0

    def plan(self, state: AgentState) -> PlanDecision:
        idx = min(self._calls, len(self.decisions) - 1)
        self._calls += 1
        return self.decisions[idx]


def _state(goal: str = "say hi") -> AgentState:
    return AgentState(
        job_id="job-1",
        trace_id="00-aaaa-bbbb-01",
        parent_id=None,
        goal=goal,
    )


def test_loop_terminates_on_done() -> None:
    planner = ScriptedPlanner(
        decisions=[PlanDecision(action="done", final_answer="hi", reasoning="trivial")]
    )
    outcome = AgentLoop(planner=planner).run(_state())
    assert outcome.halted is False
    assert outcome.final_answer == "hi"
    assert outcome.state.done is True
    assert [s.kind for s in outcome.state.steps] == ["plan"]


def test_loop_runs_one_tool_then_done() -> None:
    planner = ScriptedPlanner(
        decisions=[
            PlanDecision(action="tool", tool="echo", tool_args={"x": 1}, reasoning="invoke"),
            PlanDecision(action="done", final_answer="ok", reasoning="wrap up"),
        ]
    )
    outcome = AgentLoop(planner=planner).run(_state())
    assert outcome.halted is False
    assert outcome.final_answer == "ok"
    kinds = [s.kind for s in outcome.state.steps]
    assert kinds == ["plan", "act", "observe", "plan"]
    act_step = outcome.state.steps[1]
    assert act_step.tool == "echo"
    assert act_step.tool_result is not None
    assert act_step.tool_result["ok"] is True
    assert act_step.tool_result["output"] == {"echo": {"x": 1}}


def test_unknown_tool_raises_keyerror() -> None:
    import pytest

    planner = ScriptedPlanner(
        decisions=[
            PlanDecision(action="tool", tool="nonexistent", tool_args={}, reasoning="bad"),
        ]
    )
    with pytest.raises(KeyError):
        AgentLoop(planner=planner).run(_state())


def test_three_step_toy_task_end_to_end() -> None:
    """Toy 3-step task validation per CODEX_EXECUTION_PLAN.md Phase 27 §validation #1."""
    planner = ScriptedPlanner(
        decisions=[
            PlanDecision(action="tool", tool="echo", tool_args={"step": "search"}, reasoning="search"),
            PlanDecision(action="tool", tool="echo", tool_args={"step": "summarize"}, reasoning="summarize"),
            PlanDecision(action="tool", tool="echo", tool_args={"step": "save"}, reasoning="save"),
            PlanDecision(action="done", final_answer="done", reasoning="wrap"),
        ]
    )
    outcome = AgentLoop(planner=planner).run(_state(goal="search-summarize-save"))
    assert outcome.halted is False
    assert outcome.final_answer == "done"
    act_steps = [s for s in outcome.state.steps if s.kind == "act"]
    assert [s.tool_args["step"] for s in act_steps] == ["search", "summarize", "save"]


def test_custom_registry_overrides_default() -> None:
    from nami_core.agent.tools import Tool, ToolResult

    reg = ToolRegistry()
    reg.register(Tool(name="upper", description="uppercase", fn=lambda a: ToolResult(ok=True, output={"r": a.get("s", "").upper()})))

    planner = ScriptedPlanner(
        decisions=[
            PlanDecision(action="tool", tool="upper", tool_args={"s": "hi"}, reasoning="x"),
            PlanDecision(action="done", final_answer="HI", reasoning="x"),
        ]
    )
    outcome = AgentLoop(planner=planner, registry=reg).run(_state())
    act = outcome.state.steps[1]
    assert act.tool_result is not None
    assert act.tool_result["output"] == {"r": "HI"}


def test_default_registry_has_echo() -> None:
    reg = default_registry()
    assert "echo" in reg.names()
    res = reg.invoke("echo", {"k": "v"})
    assert res.ok and res.output == {"echo": {"k": "v"}}
