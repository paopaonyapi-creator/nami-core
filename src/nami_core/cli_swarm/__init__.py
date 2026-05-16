"""Phase 32 — CLI swarm module.

RUNTIME §8 LOCKED:
  - L8.1 — no CLI-to-CLI; cross-CLI work goes through orchestrator enqueue.
  - L8.2 — fresh git worktree per job at /var/nami/worktrees/{job_id}/.
  - L8.3 — 15-min wall-clock cap default (overridable per action).
  - L8.4 — LLM calls route through inference gateway (§6 L1.2).
  - L8.5 — stdout/stderr streamed to nami:cli:{session_id} Redis stream.
"""

from __future__ import annotations

from nami_core.cli_swarm.types import (
    CompletionStatus,
    SpawnResult,
    SessionHandle,
    SwarmConfig,
)

__all__ = ["CompletionStatus", "SpawnResult", "SessionHandle", "SwarmConfig"]
