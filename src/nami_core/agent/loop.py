"""Agent loop — Phase 27 PR-B.

LangGraph-compatible state-graph: plan -> act -> observe -> (loop|done).

T1 implementation is a manual loop with the same node shape as
LangGraph. When the codebase upgrades to LangGraph runtime, only the
driver in `run_agent` changes; nodes (`plan_node`, `act_node`,
`observe_node`) keep their (state) -> state signature.

Single-dispatch contract (RUNTIME §6): planning calls go through a
`Planner` protocol. The default in-process planner uses
`nami_core.inference_gateway.InferenceGateway`. Tests pass fake planners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from nami_core.agent.budget import (
    BudgetExceeded,
    RecursionBudget,
    enforce_budget,
)
from nami_core.agent.state import AgentState, AgentStep
from nami_core.agent.tools import ToolRegistry, default_registry


@dataclass
class PlanDecision:
    """Result of one planning step."""

    action: str  # "tool" | "done"
    reasoning: str = ""
    tool: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    final_answer: str | None = None
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


class Planner(Protocol):
    def plan(self, state: AgentState) -> PlanDecision: ...


@dataclass
class LoopOutcome:
    state: AgentState
    halted: bool
    halt_reason: str | None
    final_answer: str | None


def plan_node(state: AgentState, planner: Planner) -> AgentState:
    decision = planner.plan(state)
    step = AgentStep(
        kind="plan",
        content=decision.reasoning,
        tool=decision.tool,
        tool_args=dict(decision.tool_args),
        cost_usd=decision.cost_usd,
        tokens_in=decision.tokens_in,
        tokens_out=decision.tokens_out,
    )
    state.add_step(step)

    if decision.action == "done":
        state.done = True
        state.final_answer = decision.final_answer or ""
    elif decision.action != "tool":
        state.done = True
        state.halt_reason = f"unknown_plan_action:{decision.action}"
    return state


def act_node(state: AgentState, registry: ToolRegistry) -> AgentState:
    last_plan = _last_plan_step(state)
    if last_plan is None or last_plan.tool is None:
        state.done = True
        state.halt_reason = "act_without_plan"
        return state

    result = registry.invoke(last_plan.tool, last_plan.tool_args)
    step = AgentStep(
        kind="act",
        content=f"tool={last_plan.tool}",
        tool=last_plan.tool,
        tool_args=dict(last_plan.tool_args),
        tool_result={"ok": result.ok, "output": result.output, "error": result.error},
        error=result.error,
    )
    state.add_step(step)
    return state


def observe_node(state: AgentState) -> AgentState:
    last_act = _last_step_of(state, "act")
    if last_act is None:
        return state
    summary = (
        f"tool={last_act.tool} ok={last_act.tool_result and last_act.tool_result.get('ok')}"
        if last_act.tool_result
        else f"tool={last_act.tool} no_result"
    )
    state.messages.append({"role": "tool", "content": summary})
    state.add_step(AgentStep(kind="observe", content=summary))
    return state


@dataclass
class AgentLoop:
    planner: Planner
    registry: ToolRegistry = field(default_factory=default_registry)
    budget: RecursionBudget = field(default_factory=RecursionBudget)
    on_halt: Callable[[AgentState, str], None] | None = None

    def run(self, state: AgentState) -> LoopOutcome:
        try:
            while not state.done:
                enforce_budget(state, self.budget)
                state = plan_node(state, self.planner)
                if state.done:
                    break
                enforce_budget(state, self.budget)
                state = act_node(state, self.registry)
                if state.done:
                    break
                state = observe_node(state)
        except BudgetExceeded as exc:
            state.done = True
            state.halt_reason = str(exc)
            state.add_step(
                AgentStep(
                    kind="halt",
                    content=str(exc),
                    error=f"budget_exceeded:{exc.axis}",
                )
            )
            if self.on_halt is not None:
                self.on_halt(state, str(exc))
        return LoopOutcome(
            state=state,
            halted=state.halt_reason is not None,
            halt_reason=state.halt_reason,
            final_answer=state.final_answer,
        )


def run_agent(
    state: AgentState,
    planner: Planner,
    registry: ToolRegistry | None = None,
    budget: RecursionBudget | None = None,
) -> LoopOutcome:
    return AgentLoop(
        planner=planner,
        registry=registry or default_registry(),
        budget=budget or RecursionBudget(),
    ).run(state)


def _last_plan_step(state: AgentState) -> AgentStep | None:
    return _last_step_of(state, "plan")


def _last_step_of(state: AgentState, kind: str) -> AgentStep | None:
    for step in reversed(state.steps):
        if step.kind == kind:
            return step
    return None


__all__ = [
    "AgentLoop",
    "LoopOutcome",
    "PlanDecision",
    "Planner",
    "act_node",
    "observe_node",
    "plan_node",
    "run_agent",
]
