"""MCPBridge — Phase 28.

Orchestrates one MCP invocation: capability check (registry) → path
validation (sandbox) → subprocess execution → audit row. Returns an
`MCPResponse` regardless of failure mode so callers (the agent loop
tool registry) get a uniform shape.

Phase 28 §validation contract:
  - Path traversal → status="escape", audit row written
  - Capability denied → status="denied", audit row written
  - Subprocess timeout → status="timeout", audit row written
  - All success/failure paths emit one mcp_calls row (audit
    completeness: SELECT count(*) WHERE trace_id IS NULL = 0)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nami_core.agent.tools import Tool, ToolResult
from nami_core.mcp.audit import MCPAuditDAO
from nami_core.mcp.registry import MCPRegistry
from nami_core.mcp.safety_wrap import MCPTimeoutTracker, check_file_access
from nami_core.mcp.sandbox import Sandbox, default_sandbox
from nami_core.mcp.types import (
    CapabilityDenied,
    MCPRequest,
    MCPResponse,
    MCPServerSpec,
    SandboxEscape,
    ServerNotFound,
)

logger = logging.getLogger("nami_core.mcp.bridge")


@dataclass
class MCPBridge:
    registry: MCPRegistry
    sandbox: Sandbox = field(default_factory=default_sandbox)
    audit: MCPAuditDAO | None = None
    timeout_tracker: MCPTimeoutTracker = field(default_factory=MCPTimeoutTracker)

    def invoke(self, request: MCPRequest) -> MCPResponse:
        # 1. Capability check (server existence + scope authorization).
        try:
            self.registry.authorize(request.server, request.tool, request.role)
        except ServerNotFound as exc:
            response = MCPResponse(ok=False, error=str(exc))
            self._audit(request, response, "error", str(exc))
            return response
        except CapabilityDenied as exc:
            response = MCPResponse(ok=False, error=str(exc))
            self._audit(request, response, "denied", str(exc))
            return response

        spec = self.registry.get(request.server)

        # 2. D18 pre-flight: refuse path-shaped args outside allowed roots.
        # Sandbox enforces this at the OS layer too; this surfaces it as
        # an audit row before subprocess spawn. Traversal reason maps to
        # 'escape' to preserve the Phase 28 audit-status contract; other
        # reasons (path outside allowed roots, no roots configured) map
        # to 'denied'.
        d18_detections = check_file_access(request, spec)
        if d18_detections:
            first = d18_detections[0]
            d18_reason = first.metadata.get("reason")
            audit_status = "escape" if d18_reason == "traversal" else "denied"
            response = MCPResponse(ok=False, error=first.reason)
            self._audit(request, response, audit_status, first.reason)
            return response

        # 3. Sandbox-level path validation + subprocess execution.
        try:
            response = self.sandbox.execute(spec, request)
        except SandboxEscape as exc:
            response = MCPResponse(ok=False, error=str(exc))
            self._audit(request, response, "escape", str(exc))
            self.timeout_tracker.record(request.server, "escape")
            return response
        except Exception as exc:  # noqa: BLE001 — unknown sandbox failure
            response = MCPResponse(ok=False, error=str(exc))
            self._audit(request, response, "error", str(exc))
            self.timeout_tracker.record(request.server, "error")
            return response

        # 4. Map response → audit status.
        if response.ok:
            status = "ok"
            err = None
        elif response.error and "timeout" in response.error.lower():
            status = "timeout"
            err = response.error
        else:
            status = "error"
            err = response.error
        self._audit(request, response, status, err)
        # 5. D15: feed outcome to per-server timeout tracker. Caller
        # inspects `bridge.timeout_tracker.unhealthy_servers()` periodically.
        self.timeout_tracker.record(request.server, status)
        return response

    def _audit(
        self,
        request: MCPRequest,
        response: MCPResponse,
        status: str,
        error: str | None,
    ) -> None:
        if self.audit is None:
            return
        self.audit.record(request, response, status, error)


def mcp_tool(bridge: MCPBridge, server: str, tool: str, role: str = "agent") -> Tool:
    """Adapt an MCP server.tool into the agent.tools.Tool interface.

    Lets the agent loop call MCP servers without knowing about the
    bridge plumbing — the existing `ToolRegistry.invoke(name, args)`
    contract is preserved.
    """

    def _fn(args: dict[str, Any]) -> ToolResult:
        request = MCPRequest(
            server=server,
            tool=tool,
            args=args or {},
            role=role,
            trace_id=str(args.pop("__trace_id__", "")) if isinstance(args, dict) else "",
            job_id=str(args.pop("__job_id__", "")) if isinstance(args, dict) else "",
        )
        response = bridge.invoke(request)
        return ToolResult(
            ok=response.ok,
            output=response.output,
            error=response.error,
        )

    return Tool(
        name=f"{server}.{tool}",
        description=f"MCP tool {server}.{tool} (role={role})",
        fn=_fn,
    )


__all__ = ["MCPBridge", "mcp_tool"]
