"""Phase 32 — SwarmManager: ties adapter + worktree + tmux + stream together.

Lifecycle:
  start(job_id, adapter, task)
    → create worktree
    → build adapter command
    → open tmux session
    → publish lifecycle 'started' to nami:cli:{session_id}
    → return SessionHandle

  poll(session_id)
    → capture pane
    → publish stdout delta (last_output → current diff)
    → ask adapter to classify
    → if expired (L8.3) → status='failed' + kill

  stop(session_id, *, remove_worktree=True)
    → kill tmux
    → drop worktree (L8.2 GC)
    → publish lifecycle 'stopped'

Concurrency is bounded by SwarmConfig.max_concurrent. Adding beyond cap
raises `SwarmCapacityError`. No CLI-to-CLI invocation (L8.1) — callers
must enqueue a new job through the orchestrator.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from nami_core.cli_swarm.adapter import CLIAdapter
from nami_core.cli_swarm.adapters import get_adapter
from nami_core.cli_swarm.stream import InMemoryPublisher, StreamPublisher, make_event
from nami_core.cli_swarm.tmux import FakeTmux, TmuxBackend
from nami_core.cli_swarm.types import CompletionStatus, SessionHandle, SwarmConfig
from nami_core.cli_swarm.worktree import FakeGit, WorktreeManager

logger = logging.getLogger("nami_core.cli_swarm.manager")


class SwarmCapacityError(RuntimeError):
    """Raised when starting a session would exceed SwarmConfig.max_concurrent."""


class SwarmManager:
    def __init__(
        self,
        *,
        repo_root: str,
        config: SwarmConfig | None = None,
        worktrees: WorktreeManager | None = None,
        tmux: TmuxBackend | None = None,
        publisher: StreamPublisher | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or SwarmConfig()
        self.worktrees = worktrees or WorktreeManager(
            repo_root=repo_root,
            worktree_root=self.config.worktree_root,
            backend=FakeGit(),
        )
        self.tmux: TmuxBackend = tmux or FakeTmux()
        self.publisher: StreamPublisher = publisher or InMemoryPublisher()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.sessions: dict[str, SessionHandle] = {}

    # ── helpers ────────────────────────────────────────────────────────

    def _session_id(self, adapter_name: str, job_id: str) -> str:
        return f"cli-{adapter_name}-{job_id}"

    def _stream_name(self, session_id: str) -> str:
        return f"{self.config.redis_stream_prefix}:{session_id}"

    def _publish(self, session_id: str, kind: str, body: str) -> None:
        self.publisher.publish(self._stream_name(session_id), make_event(session_id, kind, body))

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(
        self,
        *,
        job_id: str,
        adapter: str | CLIAdapter,
        task: str,
        wall_clock_seconds: int | None = None,
    ) -> SessionHandle:
        if len(self.sessions) >= self.config.max_concurrent:
            raise SwarmCapacityError(
                f"swarm full ({len(self.sessions)}/{self.config.max_concurrent})"
            )

        impl: CLIAdapter = adapter if isinstance(adapter, CLIAdapter) else get_adapter(adapter)
        session_id = self._session_id(impl.name, job_id)
        if session_id in self.sessions:
            raise ValueError(f"session already exists: {session_id}")

        worktree_path = self.worktrees.create(job_id)
        spawn = impl.spawn(session_id, worktree_path, task)
        argv = spawn.extra.get("argv", [])

        ok = self.tmux.new_session(session_id, cwd=worktree_path, argv=argv)
        if not ok:
            self.worktrees.remove(job_id)
            raise RuntimeError(f"tmux new_session failed for {session_id}")

        seconds = wall_clock_seconds or self.config.wall_clock_seconds
        now = self.now()
        handle = SessionHandle(
            session_id=session_id,
            job_id=job_id,
            adapter=impl.name,
            worktree_path=worktree_path,
            started_at=now,
            deadline=now + timedelta(seconds=seconds),
        )
        self.sessions[session_id] = handle
        self._publish(session_id, "lifecycle", f"started adapter={impl.name} job={job_id}")
        return handle

    def poll(self, session_id: str) -> CompletionStatus:
        handle = self.sessions.get(session_id)
        if handle is None:
            raise KeyError(f"unknown session: {session_id}")
        if handle.status in ("done", "failed"):
            return handle.status

        # L8.3 wall-clock enforcement.
        if handle.is_expired(self.now()):
            self._publish(session_id, "lifecycle", "expired (wall-clock cap)")
            self.tmux.kill_session(session_id)
            handle.status = "failed"
            return "failed"

        output = self.tmux.capture_pane(session_id)
        # Publish only the new tail (delta).
        if output != handle.last_output:
            delta = output[len(handle.last_output):] if output.startswith(handle.last_output) else output
            handle.last_output = output
            if delta:
                self._publish(session_id, "stdout", delta)

        impl = get_adapter(handle.adapter)
        status = impl.parse_completion(output)
        handle.status = status
        if status in ("done", "failed"):
            self._publish(session_id, "status", status)
        return status

    def stop(self, session_id: str, *, remove_worktree: bool = True) -> bool:
        handle = self.sessions.pop(session_id, None)
        if handle is None:
            return False
        self.tmux.kill_session(session_id)
        if remove_worktree:
            self.worktrees.remove(handle.job_id)
        self._publish(session_id, "lifecycle", "stopped")
        return True

    def list_sessions(self) -> list[SessionHandle]:
        return list(self.sessions.values())


__all__ = ["SwarmManager", "SwarmCapacityError"]
