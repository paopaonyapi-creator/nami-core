"""Phase 32 — SwarmManager end-to-end tests with Fake backends."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

from nami_core.cli_swarm.adapter import CLIAdapter
from nami_core.cli_swarm.manager import SwarmCapacityError, SwarmManager
from nami_core.cli_swarm.stream import InMemoryPublisher
from nami_core.cli_swarm.tmux import FakeTmux
from nami_core.cli_swarm.types import SwarmConfig
from nami_core.cli_swarm.worktree import FakeGit, WorktreeManager


def _now_factory(start: datetime) -> "Iterator[datetime] | callable":
    state = {"t": start}

    def now() -> datetime:
        return state["t"]

    def advance(seconds: int) -> None:
        state["t"] = state["t"] + timedelta(seconds=seconds)

    now.advance = advance  # type: ignore[attr-defined]
    return now


def _build(**overrides) -> tuple[SwarmManager, FakeTmux, InMemoryPublisher, FakeGit]:
    git = FakeGit()
    tmux = FakeTmux()
    pub = InMemoryPublisher()
    cfg = SwarmConfig(max_concurrent=overrides.pop("max_concurrent", 2))
    now = overrides.pop("now", None)
    wt = WorktreeManager(repo_root="/repo", worktree_root=cfg.worktree_root, backend=git)
    m = SwarmManager(
        repo_root="/repo", config=cfg, worktrees=wt, tmux=tmux, publisher=pub,
        now=now or (lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)),
    )
    return m, tmux, pub, git


def test_start_creates_worktree_tmux_and_publishes_started() -> None:
    m, tmux, pub, git = _build()
    handle = m.start(job_id="j1", adapter="shell", task="echo hi")
    assert handle.session_id == "cli-shell-j1"
    assert handle.adapter == "shell"
    assert "/var/nami/worktrees/j1" in git.worktrees["/repo"]
    assert "cli-shell-j1" in tmux.list_sessions()
    events = pub.streams["nami:cli:cli-shell-j1"]
    assert events[0]["kind"] == "lifecycle"
    assert "started" in events[0]["body"]


def test_start_duplicate_session_rejected() -> None:
    m, _, _, _ = _build()
    m.start(job_id="j1", adapter="shell", task="x")
    with pytest.raises(ValueError):
        m.start(job_id="j1", adapter="shell", task="x")


def test_capacity_cap_enforced() -> None:
    m, _, _, _ = _build(max_concurrent=1)
    m.start(job_id="j1", adapter="shell", task="x")
    with pytest.raises(SwarmCapacityError):
        m.start(job_id="j2", adapter="shell", task="y")


def test_tmux_failure_rolls_back_worktree() -> None:
    git = FakeGit()
    tmux = FakeTmux(fail_new=True)
    wt = WorktreeManager(repo_root="/repo", backend=git)
    m = SwarmManager(repo_root="/repo", worktrees=wt, tmux=tmux, publisher=InMemoryPublisher())

    with pytest.raises(RuntimeError, match="tmux new_session failed"):
        m.start(job_id="j1", adapter="shell", task="x")

    assert "/var/nami/worktrees/j1" not in git.worktrees.get("/repo", set())


def test_poll_publishes_stdout_delta() -> None:
    m, tmux, pub, _ = _build()
    m.start(job_id="j1", adapter="shell", task="x")
    tmux.emit("cli-shell-j1", "compiling...\n")

    status = m.poll("cli-shell-j1")
    assert status == "running"
    stream = pub.streams["nami:cli:cli-shell-j1"]
    stdout_events = [e for e in stream if e["kind"] == "stdout"]
    assert stdout_events[-1]["body"] == "compiling...\n"


def test_poll_detects_done() -> None:
    m, tmux, _, _ = _build()
    m.start(job_id="j1", adapter="shell", task="x")
    tmux.emit("cli-shell-j1", "All tasks completed.\n")
    assert m.poll("cli-shell-j1") == "done"


def test_poll_unknown_session_raises() -> None:
    m, _, _, _ = _build()
    with pytest.raises(KeyError):
        m.poll("ghost")


def test_wall_clock_expiry_marks_failed_and_kills_tmux() -> None:
    """L8.3 — wall-clock cap enforced."""
    base = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
    now = _now_factory(base)
    m, tmux, pub, _ = _build(now=now)
    m.start(job_id="j1", adapter="shell", task="x", wall_clock_seconds=60)

    now.advance(120)  # past deadline
    assert m.poll("cli-shell-j1") == "failed"
    assert "cli-shell-j1" not in tmux.list_sessions()

    events = pub.streams["nami:cli:cli-shell-j1"]
    assert any("expired" in e["body"] for e in events if e["kind"] == "lifecycle")


def test_stop_removes_session_worktree_and_publishes() -> None:
    m, tmux, pub, git = _build()
    m.start(job_id="j1", adapter="shell", task="x")
    assert m.stop("cli-shell-j1") is True
    assert "cli-shell-j1" not in tmux.list_sessions()
    assert "/var/nami/worktrees/j1" not in git.worktrees.get("/repo", set())
    events = pub.streams["nami:cli:cli-shell-j1"]
    assert any("stopped" in e["body"] for e in events if e["kind"] == "lifecycle")


def test_stop_unknown_returns_false() -> None:
    m, _, _, _ = _build()
    assert m.stop("ghost") is False


def test_list_sessions_returns_handles() -> None:
    m, _, _, _ = _build()
    m.start(job_id="j1", adapter="shell", task="x")
    m.start(job_id="j2", adapter="codex", task="y")
    sids = {h.session_id for h in m.list_sessions()}
    assert sids == {"cli-shell-j1", "cli-codex-j2"}


def test_poll_terminal_status_is_idempotent() -> None:
    m, tmux, _, _ = _build()
    m.start(job_id="j1", adapter="shell", task="x")
    tmux.emit("cli-shell-j1", "done\n")
    assert m.poll("cli-shell-j1") == "done"
    # second poll returns cached status, no error if pane changes underneath
    assert m.poll("cli-shell-j1") == "done"


def test_custom_adapter_instance_accepted() -> None:
    class Spy(CLIAdapter):
        name = "spy"
        seen: list[str] = []

        def build_command(self, repo_path: str, task: str) -> list[str]:
            Spy.seen.append(task)
            return ["echo", task]

        def parse_completion(self, output: str) -> str:  # type: ignore[override]
            return "running"

    m, _, _, _ = _build()
    handle = m.start(job_id="j1", adapter=Spy(), task="hello")
    assert handle.adapter == "spy"
    assert Spy.seen == ["hello"]
