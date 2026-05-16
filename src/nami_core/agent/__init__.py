"""Agent loop — Phase 27 PR-B.

Single-dispatch contract: every model call routes through
`nami_core.inference_gateway.InferenceGateway`. No HTTP layer in T1
(see CODEX_EXECUTION_PLAN.md Phase 27 ADR 2026-05-16).
"""

from __future__ import annotations

from nami_core.agent.budget import (
    BudgetExceeded,
    RecursionBudget,
    enforce_budget,
)
from nami_core.agent.dao import AgentTracesDAO
from nami_core.agent.loop import AgentLoop, LoopOutcome, PlanDecision, Planner, run_agent
from nami_core.agent.planner import DEFAULT_SYSTEM_PROMPT, InferencePlanner
from nami_core.agent.state import AgentState, AgentStep
from nami_core.agent.tools import Tool, ToolRegistry, ToolResult, default_registry

__all__ = [
    "AgentLoop",
    "AgentState",
    "AgentStep",
    "AgentTracesDAO",
    "BudgetExceeded",
    "DEFAULT_SYSTEM_PROMPT",
    "InferencePlanner",
    "LoopOutcome",
    "PlanDecision",
    "Planner",
    "RecursionBudget",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "default_registry",
    "enforce_budget",
    "run_agent",
]
