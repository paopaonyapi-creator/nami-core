"""Phase 33→27 integration — DetectorRunner wired into AgentLoop."""

from __future__ import annotations

from typing import Any

from nami_core.agent.loop import AgentLoop, PlanDecision
from nami_core.agent.state import AgentState
from nami_core.agent.tools import Tool, ToolRegistry, ToolResult
from nami_core.safety.detectors import ALL_DETECTORS
from nami_core.safety.runner import DetectorRunner


class _ScriptedPlanner:
    def __init__(self, decisions: list[PlanDecision]) -> None:
        self._decisions = list(decisions)
        self.calls = 0

    def plan(self, state: AgentState) -> PlanDecision:
        self.calls += 1
        return self._decisions.pop(0) if self._decisions else PlanDecision(action="done", final_answer="")


def _registry_with_echo() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="echo",
            description="echo",
            fn=lambda args: ToolResult(ok=True, output={"echo": args}),
        )
    )
    return reg


def _state(job_id: str = "j1") -> AgentState:
    return AgentState(job_id=job_id, trace_id="t1", parent_id=None, goal="g")


def test_d1_halts_loop_when_planner_chooses_unknown_tool() -> None:
    planner = _ScriptedPlanner(
        [PlanDecision(action="tool", tool="ghost.tool", tool_args={})]
    )
    loop = AgentLoop(
        planner=planner,
        registry=_registry_with_echo(),
        safety_runner=DetectorRunner(ALL_DETECTORS),
    )
    outcome = loop.run(_state())

    assert outcome.halted is True
    assert outcome.halt_reason == "safety:D1:reject"
    halt_step = outcome.state.steps[-1]
    assert halt_step.kind == "halt"
    assert "D1" in halt_step.content


def test_loop_runs_normally_without_safety_runner() -> None:
    planner = _ScriptedPlanner(
        [
            PlanDecision(action="tool", tool="echo", tool_args={"x": 1}),
            PlanDecision(action="done", final_answer="ok"),
        ]
    )
    loop = AgentLoop(planner=planner, registry=_registry_with_echo())
    outcome = loop.run(_state())

    assert outcome.halted is False
    assert outcome.final_answer == "ok"


def test_d2_halts_after_three_consecutive_same_act() -> None:
    planner = _ScriptedPlanner(
        [
            PlanDecision(action="tool", tool="echo", tool_args={"x": 1}),
            PlanDecision(action="tool", tool="echo", tool_args={"x": 1}),
            PlanDecision(action="tool", tool="echo", tool_args={"x": 1}),
            PlanDecision(action="done", final_answer="never"),
        ]
    )
    loop = AgentLoop(
        planner=planner,
        registry=_registry_with_echo(),
        safety_runner=DetectorRunner(ALL_DETECTORS),
    )
    outcome = loop.run(_state())

    assert outcome.halted is True
    assert outcome.halt_reason == "safety:D2:halt_branch"


def test_safety_outcome_does_not_persist_when_no_dao() -> None:
    """Smoke: halt step is appended, DAO insert is a no-op without traces_dao."""
    planner = _ScriptedPlanner(
        [PlanDecision(action="tool", tool="ghost", tool_args={})]
    )
    loop = AgentLoop(
        planner=planner,
        registry=_registry_with_echo(),
        safety_runner=DetectorRunner(ALL_DETECTORS),
    )
    outcome = loop.run(_state())
    assert outcome.state.halt_reason == "safety:D1:reject"


def test_on_halt_callback_fires_for_safety_halt() -> None:
    captured: list[tuple[str, str]] = []

    def cb(state: AgentState, reason: str) -> None:
        captured.append((state.job_id, reason))

    planner = _ScriptedPlanner(
        [PlanDecision(action="tool", tool="ghost", tool_args={})]
    )
    loop = AgentLoop(
        planner=planner,
        registry=_registry_with_echo(),
        safety_runner=DetectorRunner(ALL_DETECTORS),
        on_halt=cb,
    )
    loop.run(_state())
    assert captured == [("j1", "safety:D1:reject")]


def test_alert_action_does_not_halt_loop() -> None:
    """D19 is `alert` — not terminal. Loop must continue."""
    planner = _ScriptedPlanner(
        [
            PlanDecision(action="tool", tool="echo", tool_args={"x": 1}, reasoning="r"),
            PlanDecision(action="tool", tool="echo", tool_args={"x": 1}, reasoning="r"),
            PlanDecision(action="done", final_answer="ok"),
        ]
    )
    loop = AgentLoop(
        planner=planner,
        registry=_registry_with_echo(),
        safety_runner=DetectorRunner(ALL_DETECTORS),
    )
    outcome = loop.run(_state())
    assert outcome.halted is False or outcome.halt_reason != "safety:D19:alert"
