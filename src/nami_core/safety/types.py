"""Phase 33 — safety detector shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ActionTaken = Literal[
    "none",            # detector did not fire
    "filter",          # context/output was sanitized
    "reject",          # input rejected, retry suggested
    "halt_branch",     # this loop branch must stop
    "halt_action",     # K2 — whole action must halt
    "halt_role",       # K3 — whole role must halt
    "alert",           # just log + metric; no behavioural change
    "truncate",        # prompt history truncated
    "force_reroll",    # caller should re-run with different params
]


@dataclass
class Detection:
    """One detector firing."""

    pattern: str            # D1, D2, ... matches SAFETY §7 IDs
    action: ActionTaken
    reason: str
    severity: Literal["low", "medium", "high"] = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectorContext:
    """Read-only snapshot fed to every detector.

    Carries just enough state for the 9 detectors in this phase. Future
    detectors that need more (e.g. heartbeat keys for D13) extend this
    rather than reaching into Redis directly — keeps detectors pure.
    """

    job_id: str
    role: str
    iteration: int
    plan: dict[str, Any] | None = None
    plan_hash_history: list[str] = field(default_factory=list)
    action_payload_history: list[tuple[str, str]] = field(default_factory=list)
    rag_chunks: list[str] = field(default_factory=list)
    tool_registry: list[str] = field(default_factory=list)
    tool_output: Any = None
    tool_output_schema: Any = None
    prompt_tokens: int = 0
    model_context_window: int = 0
    role_history: list[str] = field(default_factory=list)
    temperature: float = 0.0
    parent_payload: dict[str, Any] | None = None
    child_payload: dict[str, Any] | None = None


@dataclass
class DetectorOutcome:
    """Aggregated result from running all detectors for one transition."""

    detections: list[Detection]
    halt: bool = False
    filtered_chunks: list[str] | None = None

    def by_action(self, action: ActionTaken) -> list[Detection]:
        return [d for d in self.detections if d.action == action]


__all__ = ["ActionTaken", "Detection", "DetectorContext", "DetectorOutcome"]
