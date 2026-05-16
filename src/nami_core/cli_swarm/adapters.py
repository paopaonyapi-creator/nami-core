"""Phase 32 — concrete adapters for the four supported CLIs."""

from __future__ import annotations

import shlex

from nami_core.cli_swarm.adapter import CLIAdapter, heuristic_classify
from nami_core.cli_swarm.types import CompletionStatus


class ClaudeCodeAdapter(CLIAdapter):
    name = "claude-code"

    def build_command(self, repo_path: str, task: str) -> list[str]:
        return ["claude", "--cwd", repo_path, "--print", task]

    def parse_completion(self, output: str) -> CompletionStatus:
        if "anthropic" in output.lower() and "rate" in output.lower():
            return "failed"
        return heuristic_classify(output)


class CodexAdapter(CLIAdapter):
    name = "codex"

    def build_command(self, repo_path: str, task: str) -> list[str]:
        return ["codex", "exec", "--cd", repo_path, task]

    def parse_completion(self, output: str) -> CompletionStatus:
        return heuristic_classify(output)


class AiderAdapter(CLIAdapter):
    name = "aider"

    def build_command(self, repo_path: str, task: str) -> list[str]:
        return [
            "aider",
            "--yes",
            "--no-auto-commits",
            "--message",
            task,
            "--git-dname",
            repo_path,
        ]

    def parse_completion(self, output: str) -> CompletionStatus:
        if "Applied edit" in output or "Commit OK" in output:
            return "done"
        return heuristic_classify(output)


class ShellAdapter(CLIAdapter):
    name = "shell"

    def build_command(self, repo_path: str, task: str) -> list[str]:
        return ["bash", "-lc", f"cd {shlex.quote(repo_path)} && {task}"]

    def parse_completion(self, output: str) -> CompletionStatus:
        return heuristic_classify(output)


ADAPTERS: dict[str, type[CLIAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "aider": AiderAdapter,
    "shell": ShellAdapter,
}


def get_adapter(name: str) -> CLIAdapter:
    if name not in ADAPTERS:
        raise KeyError(f"unknown adapter: {name!r} (have: {sorted(ADAPTERS)})")
    return ADAPTERS[name]()


__all__ = [
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "AiderAdapter",
    "ShellAdapter",
    "ADAPTERS",
    "get_adapter",
]
