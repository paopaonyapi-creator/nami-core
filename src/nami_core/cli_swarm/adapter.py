"""Phase 32 — abstract CLI adapter (RUNTIME §8 LOCKED interface)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from nami_core.cli_swarm.types import CompletionStatus, SpawnResult


class CLIAdapter(ABC):
    """Adapter for one CLI tool. Subclasses MUST be pure (no side effects).

    `spawn` returns the shell command (and any prep instructions) that the
    tmux session manager will execute. The adapter does NOT directly invoke
    subprocess — separation keeps adapters testable without tmux/git.
    """

    name: str = "base"

    @abstractmethod
    def build_command(self, repo_path: str, task: str) -> list[str]:
        """Return argv to run in the new tmux session."""

    @abstractmethod
    def parse_completion(self, output: str) -> CompletionStatus:
        """Classify current pane buffer as running/awaiting_input/done/failed."""

    def spawn(self, session_id: str, repo_path: str, task: str) -> SpawnResult:
        """Default spawn wires `build_command` into a `SpawnResult` shell."""
        from datetime import datetime, timezone

        cmd = self.build_command(repo_path, task)
        return SpawnResult(
            session_id=session_id,
            adapter=self.name,
            worktree_path=repo_path,
            started_at=datetime.now(timezone.utc),
            extra={"argv": cmd, "task": task},
        )


_DONE_PATTERNS = (
    re.compile(r"\b(done|completed|finished|success)\b", re.IGNORECASE),
    re.compile(r"^\s*\$\s*$", re.MULTILINE),  # shell prompt back
)
_FAIL_PATTERNS = (
    re.compile(r"\b(error|failed|traceback|fatal)\b", re.IGNORECASE),
    re.compile(r"\bcommand not found\b", re.IGNORECASE),
)
_INPUT_PATTERNS = (
    re.compile(r"\?\s*$"),
    re.compile(r"\b(continue\?|proceed\?|y/n)\b", re.IGNORECASE),
    re.compile(r"\bawaiting\b", re.IGNORECASE),
)


def heuristic_classify(output: str) -> CompletionStatus:
    """Shared regex-based classifier used as a default by every adapter.

    Order: failure beats done beats awaiting beats running.
    """
    if not output:
        return "running"
    tail = output[-4096:]  # last 4KB only — pane buffers can be huge
    for pat in _FAIL_PATTERNS:
        if pat.search(tail):
            return "failed"
    for pat in _DONE_PATTERNS:
        if pat.search(tail):
            return "done"
    for pat in _INPUT_PATTERNS:
        if pat.search(tail):
            return "awaiting_input"
    return "running"


__all__ = ["CLIAdapter", "heuristic_classify"]
