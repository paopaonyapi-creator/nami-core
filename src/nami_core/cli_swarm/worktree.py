"""Phase 32 — worktree manager (L8.2 fresh worktree per job).

Subprocess-based git wrapper. Pure boundary: every method takes a repo_root
and a job_id, returns a path or status. Test backend (`FakeGit`) implements
the same interface and stores state in dicts.
"""

from __future__ import annotations

import logging
import os
import posixpath
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("nami_core.cli_swarm.worktree")


class GitBackend(Protocol):
    def create_worktree(self, repo_root: str, worktree_path: str, branch: str) -> str: ...
    def remove_worktree(self, repo_root: str, worktree_path: str) -> bool: ...
    def list_worktrees(self, repo_root: str) -> list[str]: ...


class SubprocessGit:
    """Real backend. Calls `git worktree`."""

    def create_worktree(self, repo_root: str, worktree_path: str, branch: str) -> str:
        Path(worktree_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "-C", repo_root, "worktree", "add", "-b", branch, worktree_path, "HEAD"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return worktree_path

    def remove_worktree(self, repo_root: str, worktree_path: str) -> bool:
        try:
            subprocess.run(
                ["git", "-C", repo_root, "worktree", "remove", "--force", worktree_path],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            logger.warning("git worktree remove failed: %s", exc.stderr)
            if Path(worktree_path).exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
            return False
        return True

    def list_worktrees(self, repo_root: str) -> list[str]:
        try:
            out = subprocess.run(
                ["git", "-C", repo_root, "worktree", "list", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        except subprocess.CalledProcessError:
            return []
        paths: list[str] = []
        for line in out.splitlines():
            if line.startswith("worktree "):
                paths.append(line[len("worktree "):])
        return paths


@dataclass
class FakeGit:
    """In-memory git for tests. Mirrors SubprocessGit's interface."""

    worktrees: dict[str, set[str]] = field(default_factory=dict)
    fail_create: bool = False
    fail_remove: bool = False

    def create_worktree(self, repo_root: str, worktree_path: str, branch: str) -> str:
        if self.fail_create:
            raise RuntimeError("git worktree add failed")
        self.worktrees.setdefault(repo_root, set()).add(worktree_path)
        return worktree_path

    def remove_worktree(self, repo_root: str, worktree_path: str) -> bool:
        if self.fail_remove:
            return False
        entries = self.worktrees.get(repo_root, set())
        if worktree_path in entries:
            entries.discard(worktree_path)
            return True
        return False

    def list_worktrees(self, repo_root: str) -> list[str]:
        return sorted(self.worktrees.get(repo_root, set()))


class WorktreeManager:
    def __init__(
        self,
        repo_root: str,
        worktree_root: str = "/var/nami/worktrees",
        backend: GitBackend | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.worktree_root = worktree_root
        self.backend = backend or SubprocessGit()

    def path_for(self, job_id: str) -> str:
        return posixpath.join(self.worktree_root, job_id)

    def branch_for(self, job_id: str) -> str:
        return f"swarm/{job_id}"

    def create(self, job_id: str) -> str:
        path = self.path_for(job_id)
        return self.backend.create_worktree(self.repo_root, path, self.branch_for(job_id))

    def remove(self, job_id: str) -> bool:
        path = self.path_for(job_id)
        return self.backend.remove_worktree(self.repo_root, path)

    def list_active(self) -> list[str]:
        return self.backend.list_worktrees(self.repo_root)


__all__ = ["GitBackend", "SubprocessGit", "FakeGit", "WorktreeManager"]
