"""Agent loop — Phase 27 PR-B.

LangGraph-compatible state-graph: plan -> act -> observe -> (loop|done).

T1 implementation is a manual loop with the same node shape as
LangGraph. When the codebase upgrades to LangGraph runtime, only the
driver in `run_agent` changes; nodes (`plan_node`, `act_node`,
`observe_node`) keep their (state) -> state signature.

Single-dispatch contract (RUNTIME §6): planning calls go through a
`Planner` protocol. The default in-process planner uses
`nami_core.inference_gateway.InferenceGateway`. Tests pass fake planners.

OTel + persistence (Phase 27 PR-B follow-up):
  - Each node is wrapped in `cost_span(role="agent")` so spans appear
    under nami_cost_*_total{role="agent"} (RUNTIME §9).
  - Optional `traces_dao` persists each step to `agent_traces` table.
    Persistence is best-effort; failures don't abort the loop.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

from nami_core.agent.budget import (
    BudgetExceeded,
    RecursionBudget,
    enforce_budget,
)
from nami_core.agent.state import AgentState, AgentStep
from nami_core.agent.tools import ToolRegistry, default_registry
from nami_core.runtime.obs import cost_span, record_cost_metric
from nami_core.safety.runner import DetectorRunner
from nami_core.safety.types import DetectorContext, DetectorOutcome

if TYPE_CHECKING:
    from nami_core.agent.dao import AgentTracesDAO


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
    temperature: float = 0.0  # sampling temperature used (D19 input)


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
        temperature=decision.temperature,
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
    traces_dao: "AgentTracesDAO | None" = None
    on_halt: Callable[[AgentState, str], None] | None = None
    safety_runner: DetectorRunner | None = None
    agent_role: str = "agent"
    model_context_window: int = 0
    prompt_token_estimator: Callable[[AgentState], int] | None = None

    def run(self, state: AgentState) -> LoopOutcome:
        try:
            while not state.done:
                enforce_budget(state, self.budget)
                self._safety_pre_plan(state)
                self._step("nami.agent.plan", state, lambda s: plan_node(s, self.planner))
                if self._safety_halt(state, phase="post_plan"):
                    break
                if state.done:
                    break
                enforce_budget(state, self.budget)
                self._step("nami.agent.act", state, lambda s: act_node(s, self.registry))
                if self._safety_halt(state, phase="post_act"):
                    break
                if state.done:
                    break
                self._step("nami.agent.observe", state, observe_node)
        except BudgetExceeded as exc:
            state.done = True
            state.halt_reason = str(exc)
            halt_step = AgentStep(
                kind="halt",
                content=str(exc),
                error=f"budget_exceeded:{exc.axis}",
            )
            state.add_step(halt_step)
            self._persist(state, halt_step)
            self._record_cost(halt_step)
            if self.on_halt is not None:
                self.on_halt(state, str(exc))
        return LoopOutcome(
            state=state,
            halted=state.halt_reason is not None,
            halt_reason=state.halt_reason,
            final_answer=state.final_answer,
        )

    def _safety_pre_plan(self, state: AgentState) -> None:
        """Run pre-plan detectors (D6 filter RAG, D12 prompt size)."""
        if self.safety_runner is None:
            return
        prompt_tokens = self._estimate_prompt_tokens(state)
        if not state.rag_chunks and prompt_tokens <= 0:
            return
        outcome = self.safety_runner.run(
            self._build_safety_context(state, phase="pre_plan", prompt_tokens=prompt_tokens)
        )
        if outcome.filtered_chunks is not None:
            state.rag_chunks = list(outcome.filtered_chunks)

    def _estimate_prompt_tokens(self, state: AgentState) -> int:
        if self.prompt_token_estimator is None or self.model_context_window <= 0:
            return 0
        try:
            value = int(self.prompt_token_estimator(state))
        except Exception:  # noqa: BLE001 — estimator must never crash the loop
            return 0
        return max(0, value)

    def _safety_halt(self, state: AgentState, *, phase: str) -> bool:
        """Run safety detectors; emit halt step + return True if any reject/halt fires."""
        if self.safety_runner is None:
            return False
        ctx = self._build_safety_context(state, phase=phase)
        outcome = self.safety_runner.run(ctx)
        if not outcome.detections:
            return False
        terminal = [d for d in outcome.detections if d.action in ("reject", "halt_branch", "halt_action", "halt_role")]
        if not terminal:
            return False
        first = terminal[0]
        reason = f"safety:{first.pattern}:{first.action}"
        state.done = True
        state.halt_reason = reason
        halt_step = AgentStep(
            kind="halt",
            content=f"{first.pattern} ({phase}): {first.reason}",
            error=reason,
        )
        state.add_step(halt_step)
        self._persist(state, halt_step)
        if self.on_halt is not None:
            self.on_halt(state, reason)
        return True

    def _build_safety_context(
        self,
        state: AgentState,
        *,
        phase: str = "post_plan",
        prompt_tokens: int = 0,
    ) -> DetectorContext:
        if phase == "pre_plan":
            return DetectorContext(
                job_id=state.job_id,
                role=self.agent_role,
                iteration=state.iters,
                rag_chunks=list(state.rag_chunks),
                tool_registry=list(self.registry.names()),
                prompt_tokens=prompt_tokens,
                model_context_window=self.model_context_window,
            )

        plan_hashes: list[str] = []
        action_payloads: list[tuple[str, str]] = []
        roles: list[str] = []
        plan_costs: list[float] = []
        last_plan: dict[str, Any] | None = None
        last_temperature: float = 0.0
        last_tool_output: Any = None
        last_tool_output_schema: Any = None
        for step in state.steps:
            if step.kind == "plan":
                payload = {
                    "tool": step.tool,
                    "content": step.content,
                    "args": step.tool_args,
                }
                plan_hashes.append(_sha256_json(payload))
                last_plan = {"tool": step.tool, "args": step.tool_args, "content": step.content}
                roles.append(self.agent_role)
                if step.cost_usd:
                    plan_costs.append(float(step.cost_usd))
                last_temperature = float(step.temperature)
            elif step.kind == "act" and step.tool is not None:
                action_payloads.append((step.tool, _sha256_json(step.tool_args or {})))
                if step.tool_result is not None:
                    last_tool_output = step.tool_result.get("output")
                    try:
                        last_tool_output_schema = self.registry.output_schema(step.tool)
                    except KeyError:
                        last_tool_output_schema = None
        return DetectorContext(
            job_id=state.job_id,
            role=self.agent_role,
            iteration=state.iters,
            plan=last_plan,
            plan_hash_history=plan_hashes,
            action_payload_history=action_payloads,
            tool_registry=list(self.registry.names()),
            tool_output=last_tool_output if phase == "post_act" else None,
            tool_output_schema=last_tool_output_schema if phase == "post_act" else None,
            role_history=roles,
            iter_cost_history=plan_costs,
            iter_budget_total=float(self.budget.max_cost_usd),
            temperature=last_temperature,
        )

    def _step(self, span_name: str, state: AgentState, fn: Callable[[AgentState], AgentState]) -> None:
        steps_before = len(state.steps)
        with cost_span(
            span_name,
            role="agent",
            attributes={
                "agent.job_id": state.job_id,
                "agent.trace_id": state.trace_id,
                "agent.depth": state.depth,
                "agent.iters": state.iters,
            },
        ) as span:
            fn(state)
            new_steps = state.steps[steps_before:]
            for step in new_steps:
                if step.cost_usd:
                    span.set_attribute("cost.usd", step.cost_usd)
                if step.tokens_in:
                    span.set_attribute("tokens.in", step.tokens_in)
                if step.tokens_out:
                    span.set_attribute("tokens.out", step.tokens_out)
                if step.tool:
                    span.set_attribute("agent.tool", step.tool)
                if step.error:
                    span.set_attribute("agent.error", step.error)
                self._persist(state, step)
                self._record_cost(step)

    def _persist(self, state: AgentState, step: AgentStep) -> None:
        if self.traces_dao is None:
            return
        index = len(state.steps) - 1  # step is the last appended
        self.traces_dao.insert_step(state, step, index)

    @staticmethod
    def _record_cost(step: AgentStep) -> None:
        if step.cost_usd or step.tokens_in or step.tokens_out:
            record_cost_metric(
                "agent",
                "agent",
                cost_usd=step.cost_usd,
                tokens_in=step.tokens_in,
                tokens_out=step.tokens_out,
            )


def run_agent(
    state: AgentState,
    planner: Planner,
    registry: ToolRegistry | None = None,
    budget: RecursionBudget | None = None,
    traces_dao: "AgentTracesDAO | None" = None,
) -> LoopOutcome:
    return AgentLoop(
        planner=planner,
        registry=registry or default_registry(),
        budget=budget or RecursionBudget(),
        traces_dao=traces_dao,
    ).run(state)


def _last_plan_step(state: AgentState) -> AgentStep | None:
    return _last_step_of(state, "plan")


def _last_step_of(state: AgentState, kind: str) -> AgentStep | None:
    for step in reversed(state.steps):
        if step.kind == kind:
            return step
    return None


def _sha256_json(payload: Any) -> str:
    try:
        canonical = json.dumps(payload, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = repr(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
