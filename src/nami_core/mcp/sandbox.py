"""MCP sandbox abstraction — Phase 28.

T1 sandboxing strategy (single VPS, no k8s):

  - On Linux with `bubblewrap` available → BubblewrapSandbox executes
    the MCP stdio server inside a bind-mount jail. Filesystem access
    is limited to `allowed_paths`; network is denied unless the spec
    sets `network: true`.

  - On Windows / macOS / dev hosts → NoOpSandbox is the default. It
    REFUSES to run when `NAMI_ENV=prod` (per SAFETY: no sandbox = no
    prod execution). For dev/CI it executes the subprocess directly
    so the rest of the MCP plumbing is testable cross-platform.

Path-traversal validation runs BEFORE the subprocess starts, regardless
of sandbox flavour. Phase 28 §validation #1 (`../../etc/passwd` →
rejected) is enforced at this layer.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from nami_core.mcp.types import (
    MCPRequest,
    MCPResponse,
    MCPServerSpec,
    SandboxEscape,
)

logger = logging.getLogger("nami_core.mcp.sandbox")


def validate_path_args(spec: MCPServerSpec, args: dict[str, Any]) -> None:
    """Reject any path arg that escapes the spec's allowed_paths.

    Validated keys: `path`, `paths` (list), and `working_dir`. The
    rule is: every supplied path must be (a) absolute or (b) a relative
    segment that does NOT contain `..` after normalization, AND must
    resolve underneath at least one entry in `spec.allowed_paths`.

    `..` in any input is always rejected without further evaluation
    (defense-in-depth: don't rely on resolve() being symlink-safe).
    """
    candidates: list[str] = []
    for key in ("path", "working_dir"):
        value = args.get(key)
        if isinstance(value, str):
            candidates.append(value)
    if isinstance(args.get("paths"), list):
        for item in args["paths"]:
            if isinstance(item, str):
                candidates.append(item)

    if not candidates:
        return

    if not spec.allowed_paths:
        raise SandboxEscape(
            f"{spec.name}: path argument supplied but no allowed_paths configured"
        )

    # Pre-screen: any '..' segment is fatal regardless of resolution.
    for raw in candidates:
        norm = raw.replace("\\", "/")
        parts = PurePosixPath(norm).parts
        if ".." in parts:
            raise SandboxEscape(f"{spec.name}: path contains '..': {raw!r}")
        if "\x00" in raw:
            raise SandboxEscape(f"{spec.name}: path contains NUL byte")

    allowed = [Path(p).resolve() for p in spec.allowed_paths]
    for raw in candidates:
        try:
            resolved = (Path(raw).resolve() if Path(raw).is_absolute()
                        else (allowed[0] / raw).resolve())
        except (OSError, RuntimeError) as exc:
            raise SandboxEscape(f"{spec.name}: path resolve failure: {exc}") from exc
        if not any(_is_under(resolved, root) for root in allowed):
            raise SandboxEscape(
                f"{spec.name}: path {raw!r} resolves outside allowed_paths"
            )


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass
class Sandbox:
    """Abstract sandbox interface."""

    def execute(self, spec: MCPServerSpec, request: MCPRequest) -> MCPResponse:
        raise NotImplementedError

    @property
    def kind(self) -> str:
        return type(self).__name__


@dataclass
class NoOpSandbox(Sandbox):
    """Dev / CI sandbox that runs the subprocess unconfined.

    Refuses to run when `NAMI_ENV=prod` to make the unsafe-by-default
    nature explicit at deployment time.
    """

    allow_prod: bool = False

    def execute(self, spec: MCPServerSpec, request: MCPRequest) -> MCPResponse:
        if not self.allow_prod and os.environ.get("NAMI_ENV") == "prod":
            raise SandboxEscape(
                "NoOpSandbox refused in prod; configure BubblewrapSandbox or "
                "set allow_prod=True explicitly (with audit ADR)"
            )
        validate_path_args(spec, request.args)
        return _run_subprocess(spec, request, sandboxed=False)


@dataclass
class BubblewrapSandbox(Sandbox):
    """Linux-only sandbox using `bwrap` to confine the MCP subprocess."""

    bwrap_path: str | None = None

    def execute(self, spec: MCPServerSpec, request: MCPRequest) -> MCPResponse:
        if sys.platform != "linux":
            raise SandboxEscape(
                f"BubblewrapSandbox requires Linux; current platform={sys.platform}"
            )
        bwrap = self.bwrap_path or shutil.which("bwrap")
        if not bwrap:
            raise SandboxEscape("bubblewrap (`bwrap`) not found on PATH")
        validate_path_args(spec, request.args)

        bwrap_cmd: list[str] = [
            bwrap,
            "--unshare-all",
            "--die-with-parent",
            "--proc", "/proc",
            "--dev", "/dev",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
        ]
        for path in spec.allowed_paths:
            bwrap_cmd.extend(["--bind", path, path])
        if spec.network:
            bwrap_cmd.append("--share-net")
        bwrap_cmd.append("--")
        bwrap_cmd.extend(spec.command + spec.args)
        return _run_command(bwrap_cmd, spec, request, sandboxed=True)


def _run_subprocess(spec: MCPServerSpec, request: MCPRequest, sandboxed: bool) -> MCPResponse:
    return _run_command(spec.command + spec.args, spec, request, sandboxed=sandboxed)


def _run_command(
    cmd: list[str],
    spec: MCPServerSpec,
    request: MCPRequest,
    *,
    sandboxed: bool,
) -> MCPResponse:
    payload = {"tool": request.tool, "args": request.args}
    started = time.monotonic()
    try:
        env = {**os.environ, **spec.env} if spec.env else None
        completed = subprocess.run(
            cmd,
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            timeout=spec.timeout_seconds,
            cwd=spec.working_dir,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        latency = int((time.monotonic() - started) * 1000)
        return MCPResponse(
            ok=False,
            error=f"timeout after {spec.timeout_seconds}s",
            latency_ms=latency,
            sandboxed=sandboxed,
        )
    except FileNotFoundError as exc:
        latency = int((time.monotonic() - started) * 1000)
        return MCPResponse(
            ok=False,
            error=f"command not found: {exc}",
            latency_ms=latency,
            sandboxed=sandboxed,
        )

    latency = int((time.monotonic() - started) * 1000)
    if completed.returncode != 0:
        return MCPResponse(
            ok=False,
            error=f"exit={completed.returncode}: {completed.stderr.decode('utf-8', 'replace')[:500]}",
            latency_ms=latency,
            sandboxed=sandboxed,
        )
    output_text = completed.stdout.decode("utf-8", errors="replace")
    try:
        output: dict[str, Any] = json.loads(output_text) if output_text.strip() else {}
        if not isinstance(output, dict):
            output = {"result": output}
    except json.JSONDecodeError:
        output = {"raw": output_text}
    return MCPResponse(ok=True, output=output, latency_ms=latency, sandboxed=sandboxed)


def default_sandbox() -> Sandbox:
    """Pick BubblewrapSandbox on Linux when `bwrap` is present, else NoOp."""
    if sys.platform == "linux" and shutil.which("bwrap"):
        return BubblewrapSandbox()
    return NoOpSandbox()


__all__ = [
    "BubblewrapSandbox",
    "NoOpSandbox",
    "Sandbox",
    "default_sandbox",
    "validate_path_args",
]
