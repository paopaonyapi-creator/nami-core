"""Agent worker — wires Phase 27 PR-B agent loop into the queue.

Worker contract (RUNTIME §5): callable `agent_worker(payload) -> dict`
loaded by `QueueWorker._register_worker` via `nami_workers.agent_worker`
when `NAMI_WORKER=agent`. Dispatcher splits `task_kind=agent.run` and
calls Hermes with worker="agent", action="run".

Actions:
  - run:  execute the loop against `payload.goal` until done or budget breach

Single-dispatch contract (RUNTIME §6): the LLM-backed `InferencePlanner`
routes every model call through `nami_core.inference_gateway`. If the
gateway is unreachable / unconfigured, falls back to `EchoPlanner` so
the worker stays smoke-testable without API keys.

Environment knobs:
  - NAMI_AGENT_PLANNER     "inference" (default) | "echo"
  - NAMI_AGENT_MODEL       passed to InferencePlanner (default per planner.py)
  - NAMI_AGENT_PERSIST     "1" enables agent_traces persistence (default off)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from nami_core.agent import (
    AgentLoop,
    AgentState,
    AgentTracesDAO,
    InferencePlanner,
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


def _select_planner():
    mode = os.environ.get("NAMI_AGENT_PLANNER", "inference").lower()
    if mode == "echo":
        return EchoPlanner()
    try:
        return InferencePlanner()
    except Exception as exc:  # noqa: BLE001 — config errors fall back, never crash
        logger.warning("InferencePlanner init failed (%s); falling back to EchoPlanner", exc)
        return EchoPlanner()


def _select_traces_dao() -> AgentTracesDAO | None:
    if os.environ.get("NAMI_AGENT_PERSIST") != "1":
        return None
    try:
        return AgentTracesDAO()
    except Exception as exc:  # noqa: BLE001 — observability is best-effort
        logger.warning("AgentTracesDAO init failed (%s); persistence disabled", exc)
        return None


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
    state.depth = int(payload.get("depth", 0) or 0)

    loop = AgentLoop(
        planner=_select_planner(),
        registry=default_registry(),
        budget=RecursionBudget(),
        traces_dao=_select_traces_dao(),
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
