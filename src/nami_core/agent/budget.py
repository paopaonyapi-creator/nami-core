"""Agent budget enforcement — Phase 27 PR-B.

Implements the recursion-budget contract from SAFETY §3:

- depth      <= 3       (parent->child agent spawn depth)
- fan_out    <= 5       (children spawned from one node)
- cost       <= $5      (USD per root tree)
- iters      <= 25      (total node executions, tree-wide)

Any breach raises `BudgetExceeded`. The agent loop catches this and
emits a `halt` step with `halt_reason` set so callers see the SAFETY
K1 signal (per SAFETY §4 kill-switch hierarchy).
"""

from __future__ import annotations

from dataclasses import dataclass

from nami_core.agent.state import AgentState


MAX_DEPTH = 3
MAX_FAN_OUT = 5
MAX_COST_USD = 5.0
MAX_ITERS = 25


class BudgetExceeded(RuntimeError):
    """Raised when any recursion-budget axis is breached.

    Maps to SAFETY K1 (per-job kill-switch). Caller is expected to mark
    the job failed and emit a `budget_exceeded` event.
    """

    def __init__(self, axis: str, value: float, cap: float) -> None:
        self.axis = axis
        self.value = value
        self.cap = cap
        super().__init__(f"budget_exceeded: {axis}={value} > cap={cap}")


@dataclass(frozen=True)
class RecursionBudget:
    max_depth: int = MAX_DEPTH
    max_fan_out: int = MAX_FAN_OUT
    max_cost_usd: float = MAX_COST_USD
    max_iters: int = MAX_ITERS


def enforce_budget(state: AgentState, budget: RecursionBudget | None = None) -> None:
    """Verify state is within budget. Raise `BudgetExceeded` on breach.

    Called once per loop iteration, before scheduling the next node.
    """
    b = budget or RecursionBudget()
    if state.depth > b.max_depth:
        raise BudgetExceeded("depth", state.depth, b.max_depth)
    if state.iters > b.max_iters:
        raise BudgetExceeded("iters", state.iters, b.max_iters)
    if state.cost_usd_total > b.max_cost_usd:
        raise BudgetExceeded("cost_usd", state.cost_usd_total, b.max_cost_usd)


def check_fan_out(children: int, budget: RecursionBudget | None = None) -> None:
    """Verify a single node's fan-out is within budget."""
    b = budget or RecursionBudget()
    if children > b.max_fan_out:
        raise BudgetExceeded("fan_out", children, b.max_fan_out)


__all__ = [
    "MAX_COST_USD",
    "MAX_DEPTH",
    "MAX_FAN_OUT",
    "MAX_ITERS",
    "BudgetExceeded",
    "RecursionBudget",
    "check_fan_out",
    "enforce_budget",
]
