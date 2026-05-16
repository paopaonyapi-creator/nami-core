"""Phase 32 — CLI swarm shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


CompletionStatus = Literal["running", "awaiting_input", "done", "failed"]


@dataclass
class SpawnResult:
    """Returned by `CLIAdapter.spawn` and surfaced by `SwarmManager.start`."""

    session_id: str
    adapter: str
    worktree_path: str
    started_at: datetime
    pid: int | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class SessionHandle:
    """Live session metadata tracked by SwarmManager."""

    session_id: str
    job_id: str
    adapter: str
    worktree_path: str
    started_at: datetime
    deadline: datetime
    status: CompletionStatus = "running"
    last_output: str = ""

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= self.deadline


@dataclass
class SwarmConfig:
    """Top-level knobs for SwarmManager. Defaults match RUNTIME §8."""

    worktree_root: str = "/var/nami/worktrees"
    wall_clock_seconds: int = 15 * 60
    max_concurrent: int = 4
    redis_stream_prefix: str = "nami:cli"


__all__ = ["CompletionStatus", "SpawnResult", "SessionHandle", "SwarmConfig"]
