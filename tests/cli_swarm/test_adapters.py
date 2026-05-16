"""Phase 32 — adapter tests (build_command + parse_completion)."""

from __future__ import annotations

import pytest

from nami_core.cli_swarm.adapter import heuristic_classify
from nami_core.cli_swarm.adapters import (
    AiderAdapter,
    ClaudeCodeAdapter,
    CodexAdapter,
    ShellAdapter,
    get_adapter,
)


def test_get_adapter_known() -> None:
    assert isinstance(get_adapter("claude-code"), ClaudeCodeAdapter)
    assert isinstance(get_adapter("codex"), CodexAdapter)
    assert isinstance(get_adapter("aider"), AiderAdapter)
    assert isinstance(get_adapter("shell"), ShellAdapter)


def test_get_adapter_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter("nope")


def test_claude_code_build_command_passes_cwd_and_task() -> None:
    argv = ClaudeCodeAdapter().build_command("/tmp/wt", "refactor auth")
    assert argv == ["claude", "--cwd", "/tmp/wt", "--print", "refactor auth"]


def test_codex_build_command_uses_exec() -> None:
    argv = CodexAdapter().build_command("/tmp/wt", "fix bug")
    assert argv[:3] == ["codex", "exec", "--cd"]
    assert "fix bug" in argv


def test_aider_build_command_no_auto_commits() -> None:
    argv = AiderAdapter().build_command("/tmp/wt", "add tests")
    assert "--no-auto-commits" in argv
    assert "--yes" in argv


def test_shell_build_command_quotes_repo_path() -> None:
    argv = ShellAdapter().build_command("/tmp/odd dir", "ls")
    assert argv[0] == "bash"
    assert "cd '/tmp/odd dir'" in argv[2]


# ── parse_completion / heuristic_classify ─────────────────────────────


def test_classify_empty_buffer_is_running() -> None:
    assert heuristic_classify("") == "running"


def test_classify_traceback_is_failed() -> None:
    assert heuristic_classify("Traceback (most recent call last):\n  ...") == "failed"


def test_classify_done_keyword() -> None:
    assert heuristic_classify("...\nAll tasks completed.") == "done"


def test_classify_awaiting_question_mark() -> None:
    assert heuristic_classify("Apply changes? ") == "awaiting_input"


def test_failure_beats_done() -> None:
    assert heuristic_classify("done\nerror occurred") == "failed"


def test_claude_rate_limit_detected() -> None:
    out = "anthropic API: rate limit exceeded"
    assert ClaudeCodeAdapter().parse_completion(out) == "failed"


def test_aider_applied_edit_is_done() -> None:
    assert AiderAdapter().parse_completion("...\nApplied edit to file.py") == "done"


def test_shell_running_when_buffer_growing() -> None:
    assert ShellAdapter().parse_completion("compiling...") == "running"


def test_tail_only_last_4kb_scanned() -> None:
    """Failures buried > 4KB back must NOT trigger 'failed'."""
    early_fail = "error\n" + ("x" * 5000)
    assert heuristic_classify(early_fail) == "running"


def test_codex_default_uses_heuristic() -> None:
    assert CodexAdapter().parse_completion("processing...") == "running"
    assert CodexAdapter().parse_completion("finished") == "done"
