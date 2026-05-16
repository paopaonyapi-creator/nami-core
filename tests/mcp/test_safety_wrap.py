"""Tests for MCP safety wiring helpers (D18 + D15)."""

from __future__ import annotations

from nami_core.mcp.safety_wrap import (
    MCPTimeoutTracker,
    check_file_access,
)
from nami_core.mcp.types import MCPRequest, MCPServerSpec


def _spec(name: str = "filesystem", roots: tuple[str, ...] = ("/opt/nami/work",)) -> MCPServerSpec:
    return MCPServerSpec(
        name=name,
        command=["/usr/bin/true"],
        allowed_paths=roots,
    )


def _req(args: dict, *, server: str = "filesystem", tool: str = "read") -> MCPRequest:
    return MCPRequest(server=server, tool=tool, args=args, role="agent", trace_id="t1", job_id="j1")


# ── check_file_access (D18 wrapping) ───────────────────────────────────


def test_path_inside_allowed_root_passes() -> None:
    dets = check_file_access(_req({"path": "/opt/nami/work/x.txt"}), _spec())
    assert dets == []


def test_path_outside_allowed_root_flagged() -> None:
    dets = check_file_access(_req({"path": "/etc/passwd"}), _spec())
    assert len(dets) == 1
    assert dets[0].pattern == "D18"
    assert dets[0].metadata["server"] == "filesystem"
    assert dets[0].metadata["tool"] == "read"


def test_traversal_marker_flagged() -> None:
    dets = check_file_access(_req({"path": "/opt/nami/work/../../etc/passwd"}), _spec())
    assert len(dets) == 1
    assert dets[0].metadata["reason"] == "traversal"


def test_multiple_path_args_all_checked() -> None:
    dets = check_file_access(
        _req({"src": "/opt/nami/work/a", "dest": "/etc/shadow"}),
        _spec(),
    )
    assert len(dets) == 1
    assert dets[0].metadata["path"] == "/etc/shadow"


def test_suffix_path_args_picked_up() -> None:
    dets = check_file_access(_req({"output_path": "/var/log/leak"}), _spec())
    assert len(dets) == 1


def test_non_string_args_ignored() -> None:
    dets = check_file_access(_req({"path": 42, "file": None}), _spec())
    assert dets == []


def test_no_path_shaped_args_returns_empty() -> None:
    dets = check_file_access(_req({"query": "anything"}), _spec())
    assert dets == []


# ── MCPTimeoutTracker (D15) ────────────────────────────────────────────


def test_tracker_two_timeouts_no_alert() -> None:
    t = MCPTimeoutTracker()
    t.record("git", "timeout")
    t.record("git", "timeout")
    assert t.streak("git") == 2
    assert t.check("git") is None


def test_tracker_three_timeouts_alerts() -> None:
    t = MCPTimeoutTracker()
    for _ in range(3):
        t.record("filesystem", "timeout")
    det = t.check("filesystem")
    assert det is not None
    assert det.pattern == "D15"
    assert det.metadata["server"] == "filesystem"
    assert det.metadata["consecutive_timeouts"] == 3


def test_tracker_ok_resets_streak() -> None:
    t = MCPTimeoutTracker()
    for _ in range(3):
        t.record("git", "timeout")
    t.record("git", "ok")
    assert t.streak("git") == 0
    assert t.check("git") is None


def test_tracker_other_status_resets_streak() -> None:
    """Anything not 'timeout' resets — denied/escape/error are non-timeout outcomes."""
    t = MCPTimeoutTracker()
    t.record("s", "timeout")
    t.record("s", "timeout")
    t.record("s", "error")
    assert t.streak("s") == 0


def test_tracker_unhealthy_servers_filters() -> None:
    t = MCPTimeoutTracker()
    for _ in range(3):
        t.record("a", "timeout")
    for _ in range(2):
        t.record("b", "timeout")
    assert t.unhealthy_servers() == ["a"]


def test_tracker_per_server_independent() -> None:
    t = MCPTimeoutTracker()
    t.record("a", "timeout")
    t.record("b", "ok")
    t.record("a", "timeout")
    t.record("b", "timeout")
    assert t.streak("a") == 2
    assert t.streak("b") == 1


def test_tracker_explicit_reset() -> None:
    t = MCPTimeoutTracker()
    for _ in range(5):
        t.record("git", "timeout")
    t.reset("git")
    assert t.streak("git") == 0
    assert t.check("git") is None
