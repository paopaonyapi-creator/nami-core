"""Runtime API v2 tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from nami_core.app import create_app
from nami_core.hermes import Hermes
from nami_core.runtime_v2 import RuntimeEvent, RuntimeJobStore, ToolRegistry
from nami_harness.runtime import HarnessContext, HarnessResult, HarnessRuntime


class _MockScheduler:
    def status(self):
        return {"running": True, "jobs": 0}


def _client() -> TestClient:
    hermes = Hermes()
    runtime = MagicMock(spec=HarnessRuntime)
    ctx = HarnessContext(agent="hermes", action="health", estimated_cost=0, correlation_id="")
    runtime.run.return_value = HarnessResult(context=ctx, output={"status": "ok"}, passed_quality=True)
    hermes.register("status", runtime, lambda payload: {"status": "ok"}, actions={"health"})
    return TestClient(create_app(hermes=hermes, scheduler=_MockScheduler(), api_key="test-key"))




def _client_with_actions(actions: set[str]) -> TestClient:
    hermes = Hermes()
    runtime = MagicMock(spec=HarnessRuntime)
    ctx = HarnessContext(agent="hermes", action="health", estimated_cost=0, correlation_id="")
    runtime.run.return_value = HarnessResult(context=ctx, output={"status": "ok"}, passed_quality=True)
    hermes.register("status", runtime, lambda payload: {"status": "ok"}, actions=actions)
    return TestClient(create_app(hermes=hermes, scheduler=_MockScheduler(), api_key="test-key"))

def test_runtime_health():
    client = _client()
    response = client.get("/runtime/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "nami-runtime-v2"
    assert data["tools"] == 1


def test_runtime_tools_lists_registered_worker_actions():
    client = _client()
    response = client.get("/runtime/tools")
    assert response.status_code == 200
    tools = response.json()["tools"]
    assert tools[0]["name"] == "status.health"
    assert tools[0]["permission_level"] == "read_only"
    assert tools[0]["read_only"] is True


def test_runtime_tool_invoke_creates_completed_job():
    client = _client()
    response = client.post("/runtime/tools/invoke", json={"worker": "status", "action": "health", "payload": {}})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["job"]["status"] == "completed"
    assert data["job"]["requested_action"] == "status.health"

    jobs = client.get("/runtime/jobs").json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["status"] == "completed"
    assert [entry["event"] for entry in jobs[0]["audit_entries"]] == ["tool.started", "tool.completed"]
    assert jobs[0]["audit_entries"][1]["ok"] is True


def test_runtime_events_test_stream_returns_ready_event():
    client = _client()
    response = client.get("/runtime/events?test=true")
    assert response.status_code == 200
    assert "runtime.ready" in response.text


def test_runtime_events_include_buffered_job_updates():
    client = _client()
    invoke = client.post("/runtime/tools/invoke", json={"worker": "status", "action": "health", "payload": {}})
    assert invoke.status_code == 200

    response = client.get("/runtime/events?test=true")
    assert response.status_code == 200
    assert "tool.started" in response.text
    assert "job.completed" in response.text


def test_runtime_job_store_persists_jobs(tmp_path):
    storage_path = tmp_path / "runtime_jobs.json"
    store = RuntimeJobStore(str(storage_path))
    job = store.create("status.health", "{}")
    job.status = "completed"
    job.result = {"ok": True}
    job.progress_events.append(RuntimeEvent(type="job.completed", job_id=job.id, data={"ok": True}))
    store.save(job)

    reloaded = RuntimeJobStore(str(storage_path))
    loaded = reloaded.get(job.id)
    assert loaded is not None
    assert loaded.status == "completed"
    assert loaded.result == {"ok": True}
    assert loaded.progress_events[0].type == "job.completed"

def test_runtime_jobs_survive_app_recreate_with_storage_file(tmp_path, monkeypatch):
    storage_path = tmp_path / "runtime_jobs.json"
    monkeypatch.setenv("NAMI_RUNTIME_JOBS_FILE", str(storage_path))

    client = _client()
    response = client.post("/runtime/tools/invoke", json={"worker": "status", "action": "health", "payload": {}})
    assert response.status_code == 200
    job_id = response.json()["job"]["id"]

    recreated = _client()
    jobs = recreated.get("/runtime/jobs").json()["jobs"]
    assert [job["id"] for job in jobs] == [job_id]
    assert jobs[0]["status"] == "completed"

def test_tool_registry_classifies_policy_levels():
    hermes = Hermes()
    runtime = MagicMock(spec=HarnessRuntime)
    hermes.register("status", runtime, lambda payload: payload, actions={"health", "send", "delete"})

    registry = ToolRegistry.from_hermes(hermes)

    assert registry.get("status.health").permission_level == "read_only"
    assert registry.get("status.health").read_only is True
    assert registry.get("status.send").permission_level == "mutating"
    assert registry.get("status.send").read_only is False
    assert registry.get("status.delete").permission_level == "dangerous"
    assert registry.get("status.delete").read_only is False


def test_runtime_tool_invoke_requires_approval_for_mutating_action():
    client = _client_with_actions({"send"})
    response = client.post("/runtime/tools/invoke", json={"worker": "status", "action": "send", "payload": {}})
    assert response.status_code == 403
    assert response.json()["detail"] == "approval required"


def test_runtime_tool_invoke_denies_dangerous_action():
    client = _client_with_actions({"delete"})
    response = client.post("/runtime/tools/invoke", json={"worker": "status", "action": "delete", "payload": {}})
    assert response.status_code == 403
    assert response.json()["detail"] == "tool denied by policy"


def test_runtime_tool_invoke_runs_mutating_action_after_approval():
    client = _client_with_actions({"send"})
    response = client.post(
        "/runtime/tools/invoke",
        headers={"Authorization": "Bearer test-key"},
        json={"worker": "status", "action": "send", "payload": {}, "approved": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["job"]["status"] == "completed"
    assert data["job"]["requested_action"] == "status.send"

def test_runtime_mcp_servers_lists_configured_servers(tmp_path, monkeypatch):
    config_file = tmp_path / "mcp.yaml"
    config_file.write_text(
        """
servers:
  - name: local_tools
    transport: stdio
    command: node
    args:
      - server.js
    tool_prefix: mcp.local
    permission_level: protected_read
  - name: remote_search
    transport: sse
    url: http://127.0.0.1:8001/sse
    enabled: false
    permission_level: read_only
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NAMI_MCP_CONFIG_FILE", str(config_file))

    client = _client()
    response = client.get("/runtime/mcp/servers")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["enabled_count"] == 1
    assert data["enabled"] == ["local_tools"]
    assert data["servers"][0]["name"] == "local_tools"
    assert data["servers"][0]["tool_namespace"] == "mcp.local"
    assert data["servers"][0]["permission_level"] == "protected_read"
    assert data["servers"][1]["enabled"] is False

def test_runtime_mcp_tools_reports_remote_servers_without_stdio_connection(tmp_path, monkeypatch):
    config_file = tmp_path / "mcp.yaml"
    config_file.write_text(
        """
servers:
  - name: remote_search
    transport: sse
    url: http://127.0.0.1:8001/sse
    tool_prefix: mcp.remote
    permission_level: read_only
  - name: disabled_search
    transport: sse
    url: http://127.0.0.1:8002/sse
    enabled: false
    permission_level: read_only
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NAMI_MCP_CONFIG_FILE", str(config_file))

    client = _client()
    response = client.get("/runtime/mcp/tools")

    assert response.status_code == 200
    data = response.json()
    assert data["discovery_status"] == "error"
    assert data["tool_count"] == 0
    assert data["tools"] == []
    assert data["servers"][0]["server"] == "remote_search"
    assert data["servers"][0]["tool_namespace"] == "mcp.remote"
    assert data["servers"][0]["status"] == "error"
    assert data["servers"][0]["status_detail"]
    assert data["servers"][1]["enabled"] is False
    assert data["servers"][1]["status_detail"] == "server disabled in config"

def test_runtime_mcp_stdio_discovers_and_invokes_tools(tmp_path, monkeypatch):
    server_script = tmp_path / "mock_mcp_server.py"
    server_script.write_text(
        """
import json
import sys

for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get("method")
    if "id" not in msg:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "mock", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "Echo payload", "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": msg.get("params", {}).get("arguments", {}).get("value", "")}], "isError": False}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
""",
        encoding="utf-8",
    )
    config_file = tmp_path / "mcp.yaml"
    config_file.write_text(
        f"""
servers:
  - name: local_tools
    transport: stdio
    command: {sys.executable}
    args:
      - {server_script}
    tool_prefix: mcp.local
    permission_level: read_only
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NAMI_MCP_CONFIG_FILE", str(config_file))

    with _client() as client:
        tools_response = client.get("/runtime/mcp/tools")
        assert tools_response.status_code == 200
        tools_data = tools_response.json()
        assert tools_data["discovery_status"] == "connected"
        assert tools_data["tool_count"] == 1
        assert tools_data["tools"][0]["name"] == "mcp.local.echo"
        assert tools_data["tools"][0]["permission_level"] == "read_only"
        assert tools_data["servers"][0]["status"] == "connected"

        invoke_response = client.post("/runtime/mcp/tools/invoke", json={"tool": "mcp.local.echo", "payload": {"value": "hello"}})
        assert invoke_response.status_code == 200
        invoke_data = invoke_response.json()
        assert invoke_data["ok"] is True
        assert invoke_data["job"]["status"] == "completed"
        assert invoke_data["job"]["requested_action"] == "mcp.local.echo"
        assert invoke_data["output"]["content"][0]["text"] == "hello"


def test_runtime_mcp_stdio_protected_tool_requires_api_key(tmp_path, monkeypatch):
    server_script = tmp_path / "mock_mcp_server.py"
    server_script.write_text(
        """
import json
import sys

for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    method = msg.get("method")
    if method == "tools/list":
        result = {"tools": [{"name": "read_secret", "description": "Read", "inputSchema": {"type": "object"}}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
""",
        encoding="utf-8",
    )
    config_file = tmp_path / "mcp.yaml"
    config_file.write_text(
        f"""
servers:
  - name: protected_tools
    transport: stdio
    command: {sys.executable}
    args:
      - {server_script}
    tool_prefix: mcp.protected
    permission_level: protected_read
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NAMI_MCP_CONFIG_FILE", str(config_file))

    with _client() as client:
        response = client.post("/runtime/mcp/tools/invoke", json={"tool": "mcp.protected.read_secret", "payload": {}})
        assert response.status_code == 401
        assert response.json()["detail"] == "api key required"


def test_runtime_mcp_sse_discovers_and_invokes_tools(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import json
    import threading

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            msg = json.loads(self.rfile.read(length).decode("utf-8"))
            method = msg.get("method")
            if method == "tools/list":
                result = {"tools": [{"name": "search", "description": "Search", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}}]}
            elif method == "tools/call":
                result = {"content": [{"type": "text", "text": msg.get("params", {}).get("arguments", {}).get("query", "")}], "isError": False}
            else:
                result = {}
            body = "data: " + json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}) + "\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config_file = tmp_path / "mcp.yaml"
    config_file.write_text(
        f"""
servers:
  - name: remote_search
    transport: sse
    url: http://127.0.0.1:{server.server_port}/sse
    tool_prefix: mcp.remote
    permission_level: read_only
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NAMI_MCP_CONFIG_FILE", str(config_file))

    try:
        with _client() as client:
            tools_response = client.get("/runtime/mcp/tools")
            assert tools_response.status_code == 200
            tools_data = tools_response.json()
            assert tools_data["discovery_status"] == "connected"
            assert tools_data["tools"][0]["name"] == "mcp.remote.search"
            assert tools_data["servers"][0]["status"] == "connected"

            invoke_response = client.post("/runtime/mcp/tools/invoke", json={"tool": "mcp.remote.search", "payload": {"query": "nami"}})
            assert invoke_response.status_code == 200
            assert invoke_response.json()["output"]["content"][0]["text"] == "nami"
    finally:
        server.shutdown()
        server.server_close()




def test_runtime_mcp_websocket_discovers_tools(tmp_path, monkeypatch):
    import asyncio
    import json
    import threading

    import websockets

    async def handler(socket):
        async for raw in socket:
            msg = json.loads(raw)
            if "id" not in msg:
                continue
            method = msg.get("method")
            if method == "tools/list":
                result = {"tools": [{"name": "ping", "description": "Ping", "inputSchema": {"type": "object"}}]}
            elif method == "tools/call":
                result = {"content": [{"type": "text", "text": "pong"}], "isError": False}
            else:
                result = {}
            await socket.send(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}))

    loop = asyncio.new_event_loop()
    ready = threading.Event()
    holder = {}

    async def start_server():
        server = await websockets.serve(handler, "127.0.0.1", 0)
        holder["server"] = server
        holder["port"] = server.sockets[0].getsockname()[1]
        ready.set()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_server())
        loop.run_forever()
        server = holder.get("server")
        if server is not None:
            server.close()
            loop.run_until_complete(server.wait_closed())
        loop.close()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    assert ready.wait(5)

    config_file = tmp_path / "mcp.yaml"
    config_file.write_text(
        f"""
servers:
  - name: ws_tools
    transport: websocket
    url: ws://127.0.0.1:{holder["port"]}
    tool_prefix: mcp.ws
    permission_level: read_only
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("NAMI_MCP_CONFIG_FILE", str(config_file))

    try:
        with _client() as client:
            tools_response = client.get("/runtime/mcp/tools")
            assert tools_response.status_code == 200
            tools_data = tools_response.json()
            assert tools_data["discovery_status"] == "connected"
            assert tools_data["tools"][0]["name"] == "mcp.ws.ping"

            invoke_response = client.post("/runtime/mcp/tools/invoke", json={"tool": "mcp.ws.ping", "payload": {}})
            assert invoke_response.status_code == 200
            assert invoke_response.json()["output"]["content"][0]["text"] == "pong"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(5)
