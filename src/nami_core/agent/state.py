"""Agent state — Phase 27 PR-B.

`AgentState` is the canonical typed container threaded through every
node in the loop. Designed to be LangGraph-compatible (plain dataclass
with `dict` round-trip) without requiring LangGraph at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


StepKind = Literal["plan", "act", "observe", "halt"]


@dataclass
class AgentStep:
    kind: StepKind
    content: str
    tool: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: dict[str, Any] | None = None
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None


@dataclass
class AgentState:
    """Mutable state passed between agent nodes.

    Fields mirror RUNTIME §7 (agent loop ABC) and SAFETY §3 (recursion
    budget). `depth` and `iters` are tracked here so budget enforcement
    can read a single source of truth.
    """

    job_id: str
    trace_id: str
    parent_id: str | None
    goal: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    depth: int = 0
    iters: int = 0
    cost_usd_total: float = 0.0
    tokens_in_total: int = 0
    tokens_out_total: int = 0
    rag_chunks: list[str] = field(default_factory=list)
    done: bool = False
    final_answer: str | None = None
    halt_reason: str | None = None

    def add_step(self, step: AgentStep) -> None:
        self.steps.append(step)
        self.iters += 1
        self.cost_usd_total += step.cost_usd
        self.tokens_in_total += step.tokens_in
        self.tokens_out_total += step.tokens_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "goal": self.goal,
            "depth": self.depth,
            "iters": self.iters,
            "cost_usd_total": self.cost_usd_total,
            "tokens_in_total": self.tokens_in_total,
            "tokens_out_total": self.tokens_out_total,
            "rag_chunks": list(self.rag_chunks),
            "done": self.done,
            "final_answer": self.final_answer,
            "halt_reason": self.halt_reason,
            "steps": [
                {
                    "kind": s.kind,
                    "content": s.content,
                    "tool": s.tool,
                    "tool_args": s.tool_args,
                    "tool_result": s.tool_result,
                    "cost_usd": s.cost_usd,
                    "tokens_in": s.tokens_in,
                    "tokens_out": s.tokens_out,
                    "error": s.error,
                }
                for s in self.steps
            ],
        }


__all__ = ["AgentState", "AgentStep", "StepKind"]
