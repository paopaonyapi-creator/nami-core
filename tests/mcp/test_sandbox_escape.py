"""Phase 28 §validation #1: sandbox path-traversal rejection."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from nami_core.mcp import (
    BubblewrapSandbox,
    MCPRequest,
    MCPServerSpec,
    NoOpSandbox,
    SandboxEscape,
    default_sandbox,
    validate_path_args,
)


def _spec(allowed_paths=("/tmp",)) -> MCPServerSpec:
    return MCPServerSpec(
        name="fs",
        command=["fs-server"],
        allowed_paths=allowed_paths,
    )


def test_validate_no_path_args_passes() -> None:
    validate_path_args(_spec(), {"query": "x"})


def test_validate_dotdot_rejected() -> None:
    with pytest.raises(SandboxEscape, match=r"\.\."):
        validate_path_args(_spec(), {"path": "../../etc/passwd"})


def test_validate_nested_dotdot_in_paths_list_rejected() -> None:
    with pytest.raises(SandboxEscape, match=r"\.\."):
        validate_path_args(_spec(), {"paths": ["a/b", "../escape"]})


def test_validate_dotdot_in_working_dir_rejected() -> None:
    with pytest.raises(SandboxEscape, match=r"\.\."):
        validate_path_args(_spec(), {"working_dir": "../"})


def test_validate_nul_byte_rejected() -> None:
    with pytest.raises(SandboxEscape, match="NUL"):
        validate_path_args(_spec(), {"path": "ok\x00inject"})


def test_validate_path_with_no_allowed_paths_rejected() -> None:
    spec = _spec(allowed_paths=())
    with pytest.raises(SandboxEscape, match="no allowed_paths"):
        validate_path_args(spec, {"path": "anything"})


def test_validate_absolute_path_outside_allowed_rejected(tmp_path: Path) -> None:
    spec = _spec(allowed_paths=(str(tmp_path),))
    other = tmp_path.parent
    with pytest.raises(SandboxEscape, match="outside"):
        validate_path_args(spec, {"path": str(other)})


def test_validate_absolute_path_inside_allowed_passes(tmp_path: Path) -> None:
    spec = _spec(allowed_paths=(str(tmp_path),))
    inside = tmp_path / "subdir" / "file.txt"
    validate_path_args(spec, {"path": str(inside)})


def test_validate_relative_path_resolves_under_first_allowed(tmp_path: Path) -> None:
    spec = _spec(allowed_paths=(str(tmp_path),))
    validate_path_args(spec, {"path": "child/file"})


def test_validate_backslash_path_dotdot_rejected() -> None:
    with pytest.raises(SandboxEscape, match=r"\.\."):
        validate_path_args(_spec(), {"path": r"..\..\etc\passwd"})


# ── NoOpSandbox prod refusal ───────────────────────────────────────────


def test_noop_sandbox_refuses_prod() -> None:
    prev = os.environ.get("NAMI_ENV")
    os.environ["NAMI_ENV"] = "prod"
    try:
        sandbox = NoOpSandbox(allow_prod=False)
        spec = _spec()
        request = MCPRequest(server="fs", tool="read", args={"path": "/tmp/x"}, role="agent")
        with pytest.raises(SandboxEscape, match="refused in prod"):
            sandbox.execute(spec, request)
    finally:
        if prev is None:
            os.environ.pop("NAMI_ENV", None)
        else:
            os.environ["NAMI_ENV"] = prev


def test_noop_sandbox_allow_prod_flag_overrides() -> None:
    """allow_prod=True bypasses the prod guard but still enforces path rules."""
    prev = os.environ.get("NAMI_ENV")
    os.environ["NAMI_ENV"] = "prod"
    try:
        sandbox = NoOpSandbox(allow_prod=True)
        spec = _spec()
        request = MCPRequest(server="fs", tool="read", args={"path": "../etc/passwd"}, role="agent")
        with pytest.raises(SandboxEscape, match=r"\.\."):
            sandbox.execute(spec, request)
    finally:
        if prev is None:
            os.environ.pop("NAMI_ENV", None)
        else:
            os.environ["NAMI_ENV"] = prev


def test_noop_sandbox_dev_runs_subprocess(tmp_path: Path) -> None:
    """No NAMI_ENV → NoOp executes; with a non-existent command, response is ok=False."""
    prev = os.environ.pop("NAMI_ENV", None)
    try:
        spec = MCPServerSpec(
            name="ghost",
            command=["this-command-definitely-does-not-exist-zzz"],
            allowed_paths=(str(tmp_path),),
            timeout_seconds=2,
        )
        request = MCPRequest(server="ghost", tool="ping", args={"path": "x"}, role="agent")
        response = NoOpSandbox().execute(spec, request)
        assert response.ok is False
        assert response.sandboxed is False
    finally:
        if prev is not None:
            os.environ["NAMI_ENV"] = prev


# ── BubblewrapSandbox platform guard ──────────────────────────────────


@pytest.mark.skipif(sys.platform == "linux", reason="Linux-specific path tested elsewhere")
def test_bubblewrap_refuses_non_linux() -> None:
    spec = _spec()
    request = MCPRequest(server="fs", tool="read", args={"path": "/tmp/x"}, role="agent")
    with pytest.raises(SandboxEscape, match="Linux"):
        BubblewrapSandbox().execute(spec, request)


@pytest.mark.skipif(sys.platform != "linux", reason="bubblewrap requires Linux")
def test_bubblewrap_missing_bwrap_raises() -> None:
    spec = _spec()
    request = MCPRequest(server="fs", tool="read", args={"path": "/tmp/x"}, role="agent")
    sandbox = BubblewrapSandbox(bwrap_path="/bin/this-bwrap-does-not-exist-zzz")
    # bwrap_path is None means autodetect; we explicitly point at a fake path.
    # Actual execution will fall through to FileNotFoundError handling, but
    # since `bwrap_path` is set, the explicit path is used. This test will
    # actually try to subprocess.run that path which doesn't exist → ok=False.
    response = sandbox.execute(spec, request)
    assert response.ok is False


# ── default_sandbox selection ─────────────────────────────────────────


def test_default_sandbox_picks_noop_when_no_bwrap() -> None:
    sandbox = default_sandbox()
    # On Windows / macOS / Linux without bwrap → NoOp
    if sys.platform != "linux":
        assert isinstance(sandbox, NoOpSandbox)
