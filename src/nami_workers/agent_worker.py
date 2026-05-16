"""Agent worker — wires Phase 27 PR-B agent loop into the queue.

Worker contract (RUNTIME §5): callable `agent_worker(payload) -> dict`
loaded by `QueueWorker._register_worker` via `nami_workers.agent_worker`
when `NAMI_WORKER=agent`. Dispatcher splits `task_kind=agent.run` and
calls Hermes with worker="agent", action="run".

Actions:
  - run:  execute the loop against `payload.goal` until done or budget breach

Single-dispatch contract (RUNTIME §6): any real LLM planner MUST route
through `nami_core.inference_gateway`. The default planner here is an
`EchoPlanner` stub so the worker is exercisable without API keys; the
real `InferencePlanner` lands in a follow-up commit once model lineup
is confirmed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from nami_core.agent import (
    AgentLoop,
    AgentState,
    PlanDecision,
    RecursionBudget,
    default_registry,
)

logger = logging.getLogger("nami_workers.agent")


@dataclass
class EchoPlanner:
    """Stub planner: one echo invocation, then done. Useful for smoke."""

    _called: int = 0

    def plan(self, state: AgentState) -> PlanDecision:
        self._called += 1
        if self._called == 1:
            return PlanDecision(
                action="tool",
                tool="echo",
                tool_args={"goal": state.goal},
                reasoning="stub-planner: echo the goal",
            )
        return PlanDecision(
            action="done",
            final_answer=f"acknowledged: {state.goal}",
            reasoning="stub-planner: terminate",
        )


def agent_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch entry point invoked by `QueueWorker._execute_task`."""
    action = payload.get("action", "run")
    if action == "run":
        return _run(payload)
    return {"error": f"unknown action: {action}"}


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    goal = payload.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return {"error": "goal required (non-empty string)"}

    state = AgentState(
        job_id=str(payload.get("job_id") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        parent_id=payload.get("parent_id"),
        goal=goal,
    )

    initial_depth = int(payload.get("depth", 0) or 0)
    state.depth = initial_depth

    loop = AgentLoop(
        planner=EchoPlanner(),
        registry=default_registry(),
        budget=RecursionBudget(),
    )
    outcome = loop.run(state)

    return {
        "ok": not outcome.halted,
        "final_answer": outcome.final_answer,
        "halted": outcome.halted,
        "halt_reason": outcome.halt_reason,
        "steps": outcome.state.to_dict()["steps"],
        "iters": outcome.state.iters,
        "depth": outcome.state.depth,
        "tokens_used": outcome.state.tokens_in_total + outcome.state.tokens_out_total,
        "cost_usd": outcome.state.cost_usd_total,
    }


__all__ = ["EchoPlanner", "agent_worker"]
