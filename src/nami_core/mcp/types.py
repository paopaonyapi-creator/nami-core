"""MCP types — Phase 28.

Cross-platform contract types for sandboxed MCP server invocation per
EVOLUTION §2.3 + GOVERNANCE §5 capability scopes.

The actual subprocess sandboxing (bubblewrap on Linux) lives in
`nami_core.mcp.sandbox`. These types are pure data and import-safe
on Windows / macOS / Linux alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CapabilityScope:
    """One capability granted to a role for an MCP server.

    Maps to GOVERNANCE §5: `role` × `tool` × `verb` × optional path/host
    constraints. A scope is the smallest unit of permission.
    """

    server: str          # e.g. "filesystem"
    tool: str            # e.g. "read"
    roles: tuple[str, ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)

    def allows(self, role: str) -> bool:
        if not self.roles:
            return False
        return role in self.roles or "*" in self.roles


@dataclass(frozen=True)
class MCPServerSpec:
    """Declarative server config loaded from `servers/<name>.yaml`."""

    name: str
    command: list[str]
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    working_dir: str | None = None
    allowed_paths: tuple[str, ...] = ()
    network: bool = False                            # default deny network access
    timeout_seconds: int = 30
    scopes: tuple[CapabilityScope, ...] = ()

    def scope_for(self, tool: str) -> CapabilityScope | None:
        for scope in self.scopes:
            if scope.tool == tool:
                return scope
        return None


@dataclass
class MCPRequest:
    """One invocation of an MCP tool."""

    server: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    role: str = "agent"
    trace_id: str = ""
    job_id: str = ""


@dataclass
class MCPResponse:
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 0
    sandboxed: bool = False


class MCPError(RuntimeError):
    """Base class for MCP failures (capability denial, sandbox escape, etc.)."""


class CapabilityDenied(MCPError):
    """Role lacks the capability scope to invoke this tool."""


class SandboxEscape(MCPError):
    """Argument validation rejected a request that would escape the sandbox."""


class ServerNotFound(MCPError):
    """No registered server matches the request."""


__all__ = [
    "CapabilityDenied",
    "CapabilityScope",
    "MCPError",
    "MCPRequest",
    "MCPResponse",
    "MCPServerSpec",
    "SandboxEscape",
    "ServerNotFound",
]
