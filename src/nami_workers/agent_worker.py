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

SAFETY §7 wiring: by default the loop runs `ALL_DETECTORS` via
`DetectorRunner` for D1/D2/D4/D6/D9/D12/D17 enforcement. Set
`NAMI_AGENT_SAFETY=0` to disable for local debugging only — production
should always leave it on. Construction failures fall back to the
no-detectors path so a misbehaving safety module cannot brick the
worker.

Environment knobs:
  - NAMI_AGENT_PLANNER     "inference" (default) | "echo"
  - NAMI_AGENT_MODEL       passed to InferencePlanner (default per planner.py)
  - NAMI_AGENT_PERSIST     "1" enables agent_traces persistence (default off)
  - NAMI_AGENT_SAFETY      "0" disables DetectorRunner wiring (default on)
  - NAMI_AGENT_CTX_WINDOW  int model context window for D12 (default 0 = off)
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
    # `_build_task_payload` injects the full action name (e.g. "agent.run").
    # Hermes also injects bare action ("run") via Hermes.dispatch.
    # Accept both shapes by stripping any "<worker>." prefix.
    raw = str(payload.get("action") or "run")
    action = raw.split(".", 1)[1] if "." in raw else raw
    if action == "run":
        return _run(payload)
    return {"error": f"unknown action: {raw}"}


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


def _select_safety_runner():
    """Build a DetectorRunner with all SAFETY §7 detectors.

    Best-effort: returns `None` if the env disables it, the safety module
    fails to import, or the runner cannot be constructed. The agent loop
    treats `None` as "no detectors", preserving prior behaviour.
    """
    if os.environ.get("NAMI_AGENT_SAFETY", "1") == "0":
        return None
    try:
        from nami_core.safety.detectors import ALL_DETECTORS
        from nami_core.safety.runner import DetectorRunner

        return DetectorRunner(list(ALL_DETECTORS))
    except Exception as exc:  # noqa: BLE001 — safety wiring failures must not brick worker
        logger.warning(
            "DetectorRunner init failed (%s); agent loop will run without safety detectors",
            exc,
        )
        return None


def _select_token_estimator():
    """Pick the prompt-token estimator for D12 (prompt-size explosion)."""
    try:
        from nami_core.agent.tokens import estimate_state_prompt_tokens

        return estimate_state_prompt_tokens
    except Exception as exc:  # noqa: BLE001
        logger.debug("token estimator unavailable (%s); D12 will be inert", exc)
        return None


def _model_context_window() -> int:
    raw = os.environ.get("NAMI_AGENT_CTX_WINDOW", "0")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


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
        safety_runner=_select_safety_runner(),
        model_context_window=_model_context_window(),
        prompt_token_estimator=_select_token_estimator(),
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
