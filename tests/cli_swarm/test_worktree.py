"""Phase 32 — worktree manager tests using FakeGit backend."""

from __future__ import annotations

import pytest

from nami_core.cli_swarm.worktree import FakeGit, WorktreeManager


def _mgr(**kwargs) -> WorktreeManager:
    backend = kwargs.pop("backend", FakeGit())
    return WorktreeManager(
        repo_root="/repo",
        worktree_root="/var/nami/worktrees",
        backend=backend,
        **kwargs,
    )


def test_path_and_branch_derivation() -> None:
    m = _mgr()
    assert m.path_for("job-1") == "/var/nami/worktrees/job-1"
    assert m.branch_for("job-1") == "swarm/job-1"


def test_create_records_worktree_in_backend() -> None:
    backend = FakeGit()
    m = _mgr(backend=backend)
    path = m.create("job-1")
    assert path == "/var/nami/worktrees/job-1"
    assert path in backend.worktrees["/repo"]


def test_remove_drops_recorded_worktree() -> None:
    backend = FakeGit()
    m = _mgr(backend=backend)
    m.create("job-1")
    assert m.remove("job-1") is True
    assert "/var/nami/worktrees/job-1" not in backend.worktrees["/repo"]


def test_remove_unknown_returns_false() -> None:
    m = _mgr()
    assert m.remove("ghost") is False


def test_list_active_round_trips() -> None:
    m = _mgr()
    m.create("a")
    m.create("b")
    assert m.list_active() == ["/var/nami/worktrees/a", "/var/nami/worktrees/b"]


def test_create_failure_propagates() -> None:
    m = _mgr(backend=FakeGit(fail_create=True))
    with pytest.raises(RuntimeError):
        m.create("job-1")


def test_remove_failure_returns_false() -> None:
    backend = FakeGit(fail_remove=True)
    m = _mgr(backend=backend)
    m.create("job-1")
    assert m.remove("job-1") is False
