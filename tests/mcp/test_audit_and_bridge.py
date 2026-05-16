"""Phase 28 §validation #3: audit completeness + bridge integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from nami_core.mcp import (
    CapabilityDenied,
    MCPAuditDAO,
    MCPBridge,
    MCPRegistry,
    MCPRequest,
    MCPResponse,
    MCPServerSpec,
    NoOpSandbox,
    Sandbox,
    SandboxEscape,
    parse_server_spec,
    mcp_tool,
)
from nami_core.mcp.audit import _hash_payload


# ── audit DAO ──────────────────────────────────────────────────────────


def test_audit_hash_is_deterministic() -> None:
    a = _hash_payload({"a": 1, "b": [1, 2, 3]})
    b = _hash_payload({"b": [1, 2, 3], "a": 1})  # different key order
    assert a == b


def test_audit_hash_differs_for_different_payloads() -> None:
    assert _hash_payload({"a": 1}) != _hash_payload({"a": 2})


def test_audit_dao_record_invalid_status_rejected() -> None:
    dao = MCPAuditDAO(dsn="postgresql://u:p@127.0.0.1:65535/db?connect_timeout=1")
    request = MCPRequest(server="fs", tool="read", args={}, role="agent", trace_id="t")
    with pytest.raises(ValueError, match="invalid mcp status"):
        dao.record(request, MCPResponse(ok=True), "bogus", None)


def test_audit_dao_returns_false_on_db_failure() -> None:
    """Best-effort: connect failure → False, never raises."""
    dao = MCPAuditDAO(dsn="postgresql://u:p@127.0.0.1:65535/db?connect_timeout=1")
    request = MCPRequest(server="fs", tool="read", args={"k": 1}, role="agent", trace_id="t1")
    assert dao.record(request, MCPResponse(ok=True), "ok", None) is False


# ── Fakes for bridge tests ─────────────────────────────────────────────


@dataclass
class FakeAuditDAO:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        request: MCPRequest,
        response: MCPResponse | None,
        status: str,
        error: str | None = None,
    ) -> bool:
        self.rows.append(
            {
                "trace_id": request.trace_id,
                "server": request.server,
                "tool": request.tool,
                "role": request.role,
                "status": status,
                "error": error,
                "ok": response.ok if response else False,
                "sandboxed": response.sandboxed if response else False,
            }
        )
        return True


@dataclass
class FakeSandbox(Sandbox):
    response: MCPResponse = field(default_factory=lambda: MCPResponse(ok=True, output={"x": 1}, sandboxed=True))
    raise_escape: bool = False
    raise_other: Exception | None = None

    def execute(self, spec, request):
        if self.raise_escape:
            raise SandboxEscape("simulated path traversal")
        if self.raise_other is not None:
            raise self.raise_other
        return self.response


def _basic_registry() -> MCPRegistry:
    spec = parse_server_spec(
        "fs",
        {
            "name": "fs",
            "command": "fs-server",
            "allowed_paths": ["/tmp"],
            "scopes": [
                {"tool": "read", "roles": ["agent", "researcher"]},
                {"tool": "write", "roles": ["agent"]},
            ],
        },
    )
    reg = MCPRegistry()
    reg.register(spec)
    return reg


# ── Bridge: capability check ───────────────────────────────────────────


def test_bridge_audits_unknown_server_with_error_status() -> None:
    audit = FakeAuditDAO()
    bridge = MCPBridge(registry=MCPRegistry(), sandbox=FakeSandbox(), audit=audit)
    request = MCPRequest(server="ghost", tool="read", args={}, role="agent", trace_id="t")
    response = bridge.invoke(request)
    assert response.ok is False
    assert audit.rows == [
        {
            "trace_id": "t",
            "server": "ghost",
            "tool": "read",
            "role": "agent",
            "status": "error",
            "error": response.error,
            "ok": False,
            "sandboxed": False,
        }
    ]


def test_bridge_denies_unauthorized_role_and_audits() -> None:
    """Phase 28 §validation #4: git.push denied for researcher (here fs.write)."""
    audit = FakeAuditDAO()
    bridge = MCPBridge(registry=_basic_registry(), sandbox=FakeSandbox(), audit=audit)
    request = MCPRequest(server="fs", tool="write", args={}, role="researcher", trace_id="t-deny")
    response = bridge.invoke(request)
    assert response.ok is False
    assert "researcher" in (response.error or "")
    assert audit.rows[0]["status"] == "denied"


def test_bridge_records_escape_status_on_path_traversal() -> None:
    audit = FakeAuditDAO()
    sandbox = FakeSandbox(raise_escape=True)
    bridge = MCPBridge(registry=_basic_registry(), sandbox=sandbox, audit=audit)
    request = MCPRequest(
        server="fs",
        tool="read",
        args={"path": "../../etc/passwd"},
        role="agent",
        trace_id="t-escape",
    )
    response = bridge.invoke(request)
    assert response.ok is False
    assert audit.rows[0]["status"] == "escape"
    assert "traversal" in (audit.rows[0]["error"] or "").lower()


def test_bridge_records_ok_on_successful_invocation() -> None:
    audit = FakeAuditDAO()
    bridge = MCPBridge(registry=_basic_registry(), sandbox=FakeSandbox(), audit=audit)
    request = MCPRequest(server="fs", tool="read", args={}, role="agent", trace_id="t-ok")
    response = bridge.invoke(request)
    assert response.ok is True
    assert audit.rows[0]["status"] == "ok"
    assert audit.rows[0]["sandboxed"] is True


def test_bridge_records_timeout_when_sandbox_returns_timeout() -> None:
    audit = FakeAuditDAO()
    sandbox = FakeSandbox(response=MCPResponse(ok=False, error="timeout after 30s"))
    bridge = MCPBridge(registry=_basic_registry(), sandbox=sandbox, audit=audit)
    request = MCPRequest(server="fs", tool="read", args={}, role="agent", trace_id="t-timeout")
    bridge.invoke(request)
    assert audit.rows[0]["status"] == "timeout"


def test_bridge_records_error_on_unknown_sandbox_failure() -> None:
    audit = FakeAuditDAO()
    sandbox = FakeSandbox(raise_other=RuntimeError("kernel panic"))
    bridge = MCPBridge(registry=_basic_registry(), sandbox=sandbox, audit=audit)
    request = MCPRequest(server="fs", tool="read", args={}, role="agent", trace_id="t-err")
    response = bridge.invoke(request)
    assert response.ok is False
    assert audit.rows[0]["status"] == "error"
    assert "kernel panic" in (audit.rows[0]["error"] or "")


def test_bridge_audit_completeness_no_path_skips_audit() -> None:
    """Every invoke writes exactly one audit row (when audit configured)."""
    audit = FakeAuditDAO()
    bridge = MCPBridge(registry=_basic_registry(), sandbox=FakeSandbox(), audit=audit)
    bridge.invoke(MCPRequest(server="fs", tool="read", args={}, role="agent", trace_id="a"))
    bridge.invoke(MCPRequest(server="fs", tool="write", args={}, role="researcher", trace_id="b"))
    bridge.invoke(MCPRequest(server="ghost", tool="x", args={}, role="agent", trace_id="c"))
    assert len(audit.rows) == 3
    assert {r["trace_id"] for r in audit.rows} == {"a", "b", "c"}
    # All trace_ids non-null per audit-completeness contract.
    assert all(r["trace_id"] for r in audit.rows)


def test_bridge_works_without_audit() -> None:
    bridge = MCPBridge(registry=_basic_registry(), sandbox=FakeSandbox(), audit=None)
    response = bridge.invoke(MCPRequest(server="fs", tool="read", args={}, role="agent"))
    assert response.ok is True


# ── mcp_tool adapter (agent-loop integration) ─────────────────────────


def test_mcp_tool_adapts_into_tool_registry_interface() -> None:
    bridge = MCPBridge(registry=_basic_registry(), sandbox=FakeSandbox(), audit=None)
    tool = mcp_tool(bridge, "fs", "read", role="agent")
    assert tool.name == "fs.read"
    result = tool.invoke({"k": "v"})
    assert result.ok is True
    assert result.output == {"x": 1}


def test_mcp_tool_propagates_capability_denial() -> None:
    """Tool wrapper turns CapabilityDenied into ToolResult(ok=False, error=...)."""
    bridge = MCPBridge(registry=_basic_registry(), sandbox=FakeSandbox(), audit=None)
    tool = mcp_tool(bridge, "fs", "write", role="researcher")
    result = tool.invoke({})
    assert result.ok is False
    assert "researcher" in (result.error or "")


def test_mcp_tool_strips_meta_args_before_passing_to_sandbox() -> None:
    """`__trace_id__` / `__job_id__` from agent loop must NOT be passed to sandbox.

    Agent loop uses these to propagate trace context; they should be
    extracted into MCPRequest fields, not leaked as tool args.
    """
    captured: dict[str, Any] = {}

    @dataclass
    class CapturingSandbox(Sandbox):
        def execute(self, spec, request):
            captured["args"] = dict(request.args)
            captured["trace_id"] = request.trace_id
            captured["job_id"] = request.job_id
            return MCPResponse(ok=True)

    bridge = MCPBridge(registry=_basic_registry(), sandbox=CapturingSandbox(), audit=None)
    tool = mcp_tool(bridge, "fs", "read", role="agent")
    tool.invoke({"q": "x", "__trace_id__": "T-1", "__job_id__": "J-1"})
    assert captured["args"] == {"q": "x"}
    assert captured["trace_id"] == "T-1"
    assert captured["job_id"] == "J-1"
