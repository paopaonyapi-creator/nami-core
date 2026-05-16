"""Tests for D18 + D15 wiring inside MCPBridge.invoke."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nami_core.mcp.audit import MCPAuditDAO  # noqa: F401 — types only
from nami_core.mcp.bridge import MCPBridge
from nami_core.mcp.registry import MCPRegistry, parse_server_spec
from nami_core.mcp.sandbox import Sandbox
from nami_core.mcp.types import MCPRequest, MCPResponse


@dataclass
class _AuditSpy:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def record(self, request, response, status, error=None) -> bool:
        self.rows.append(
            {
                "server": request.server,
                "tool": request.tool,
                "status": status,
                "error": error,
                "ok": response.ok if response else False,
            }
        )
        return True


@dataclass
class _CountingSandbox(Sandbox):
    response: MCPResponse = field(default_factory=lambda: MCPResponse(ok=True, output={"x": 1}, sandboxed=True))
    calls: int = 0

    def execute(self, spec, request):
        self.calls += 1
        return self.response


def _registry() -> MCPRegistry:
    spec = parse_server_spec(
        "fs",
        {
            "name": "fs",
            "command": "fs-server",
            "allowed_paths": ["/opt/nami/work"],
            "scopes": [{"tool": "read", "roles": ["agent"]}, {"tool": "write", "roles": ["agent"]}],
        },
    )
    reg = MCPRegistry()
    reg.register(spec)
    return reg


# ── D18 wiring ─────────────────────────────────────────────────────────


def test_d18_path_outside_root_short_circuits_before_sandbox() -> None:
    audit = _AuditSpy()
    sandbox = _CountingSandbox()
    bridge = MCPBridge(registry=_registry(), sandbox=sandbox, audit=audit)
    request = MCPRequest(
        server="fs",
        tool="read",
        args={"path": "/etc/passwd"},
        role="agent",
        trace_id="t1",
    )

    response = bridge.invoke(request)

    assert response.ok is False
    assert sandbox.calls == 0
    assert audit.rows[0]["status"] == "denied"
    assert "outside allowed roots" in (audit.rows[0]["error"] or "")


def test_d18_traversal_marker_audits_as_escape() -> None:
    audit = _AuditSpy()
    sandbox = _CountingSandbox()
    bridge = MCPBridge(registry=_registry(), sandbox=sandbox, audit=audit)
    request = MCPRequest(
        server="fs",
        tool="read",
        args={"path": "/opt/nami/work/../../etc/passwd"},
        role="agent",
        trace_id="t1",
    )

    response = bridge.invoke(request)

    assert response.ok is False
    assert sandbox.calls == 0
    assert audit.rows[0]["status"] == "escape"


def test_d18_inside_root_passes_to_sandbox() -> None:
    audit = _AuditSpy()
    sandbox = _CountingSandbox()
    bridge = MCPBridge(registry=_registry(), sandbox=sandbox, audit=audit)
    request = MCPRequest(
        server="fs",
        tool="read",
        args={"path": "/opt/nami/work/x.txt"},
        role="agent",
        trace_id="t1",
    )

    response = bridge.invoke(request)

    assert response.ok is True
    assert sandbox.calls == 1
    assert audit.rows[0]["status"] == "ok"


# ── D15 wiring ─────────────────────────────────────────────────────────


def test_d15_tracker_records_ok_outcome() -> None:
    bridge = MCPBridge(registry=_registry(), sandbox=_CountingSandbox())
    request = MCPRequest(server="fs", tool="read", args={}, role="agent", trace_id="t")

    bridge.invoke(request)

    assert bridge.timeout_tracker.streak("fs") == 0


def test_d15_tracker_increments_on_timeout() -> None:
    sandbox = _CountingSandbox(response=MCPResponse(ok=False, error="execution timeout after 30s"))
    bridge = MCPBridge(registry=_registry(), sandbox=sandbox)
    request = MCPRequest(server="fs", tool="read", args={}, role="agent", trace_id="t")

    for _ in range(3):
        bridge.invoke(request)

    assert bridge.timeout_tracker.streak("fs") == 3
    det = bridge.timeout_tracker.check("fs")
    assert det is not None
    assert det.pattern == "D15"
    assert "fs" in det.metadata["server"]


def test_d15_tracker_resets_after_ok_outcome() -> None:
    timeout_resp = MCPResponse(ok=False, error="execution timeout after 30s")
    ok_resp = MCPResponse(ok=True, output={"x": 1}, sandboxed=True)
    sandbox = _CountingSandbox(response=timeout_resp)
    bridge = MCPBridge(registry=_registry(), sandbox=sandbox)
    request = MCPRequest(server="fs", tool="read", args={}, role="agent", trace_id="t")

    bridge.invoke(request)
    bridge.invoke(request)
    assert bridge.timeout_tracker.streak("fs") == 2

    sandbox.response = ok_resp
    bridge.invoke(request)
    assert bridge.timeout_tracker.streak("fs") == 0
