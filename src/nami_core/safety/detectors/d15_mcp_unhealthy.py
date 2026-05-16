"""D15 — MCP server unhealthy: 3 consecutive timeouts to a single MCP server."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


_TIMEOUT_THRESHOLD = 3


def detect(ctx: DetectorContext) -> Detection | None:
    if ctx.mcp_consecutive_timeouts < _TIMEOUT_THRESHOLD:
        return None
    if ctx.mcp_server_name is None:
        return None
    return Detection(
        pattern="D15",
        action="alert",
        reason=f"MCP server {ctx.mcp_server_name!r} timed out {ctx.mcp_consecutive_timeouts} consecutive times — mark unhealthy",
        severity="medium",
        metadata={
            "server": ctx.mcp_server_name,
            "consecutive_timeouts": ctx.mcp_consecutive_timeouts,
        },
    )
