"""Minimal MCP client support for Nami Core."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Protocol

from nami_core.mcp_config import McpConfig, McpServerConfig
from nami_core.runtime_v2 import PolicyCategory, ToolMetadata


class McpClientError(RuntimeError):
    pass


@dataclass
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    server: str
    namespaced_name: str
    permission_level: PolicyCategory
    read_only: bool

    def to_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self.namespaced_name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema={"type": "object", "additionalProperties": True},
            permission_level=self.permission_level,
            timeout_seconds=30,
            audit_category="mcp_tool_call",
            read_only=self.read_only,
            worker="mcp",
            action=self.namespaced_name,
        )

    def to_dict(self) -> dict[str, Any]:
        data = self.to_metadata().to_dict()
        data.update({"server": self.server, "mcp_name": self.name})
        return data


@dataclass
class McpServerRuntime:
    server: McpServerConfig
    status: str = "configured"
    status_detail: str = "configured; connection not opened"
    tools: list[McpTool] = field(default_factory=list)
    last_checked_at: str | None = None
    failure_count: int = 0
    next_retry_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server": self.server.name,
            "tool_namespace": self.server.to_tool_namespace(),
            "enabled": self.server.enabled,
            "status": self.status,
            "status_detail": self.status_detail,
            "last_checked_at": self.last_checked_at,
            "failure_count": self.failure_count,
            "next_retry_at": self.next_retry_at,
            "tools": [tool.to_dict() for tool in self.tools],
            "tool_count": len(self.tools),
        }


class McpSession(Protocol):
    server: McpServerConfig

    async def start(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def list_tools(self) -> list[dict[str, Any]]:
        ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


class StdioMcpSession:
    def __init__(self, server: McpServerConfig) -> None:
        self.server = server
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._process is not None:
            return
        if not self.server.command:
            raise McpClientError(f"stdio MCP server requires command: {self.server.name}")
        env = os.environ.copy()
        env.update(self.server.env)
        self._process = await asyncio.create_subprocess_exec(
            self.server.command,
            *self.server.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "nami-core", "version": "0.13.0"}})
        await self.notify("notifications/initialized", {})

    async def close(self) -> None:
        if self._process is None:
            return
        process = self._process
        self._process = None
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise McpClientError(f"MCP server is not connected: {self.server.name}")
        async with self._lock:
            request_id = self._next_id
            self._next_id += 1
            payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
            self._process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            await self._process.stdin.drain()
            while True:
                line = await asyncio.wait_for(self._process.stdout.readline(), timeout=10)
                if not line:
                    raise McpClientError(f"MCP server closed stdout: {self.server.name}")
                response = json.loads(line.decode("utf-8"))
                if response.get("id") != request_id:
                    continue
                if "error" in response:
                    raise McpClientError(str(response["error"]))
                return response.get("result", {})

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._process is None or self._process.stdin is None:
            raise McpClientError(f"MCP server is not connected: {self.server.name}")
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        await self._process.stdin.drain()

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self.request("tools/list")
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self.request("tools/call", {"name": name, "arguments": arguments})


class HttpMcpSession:
    def __init__(self, server: McpServerConfig) -> None:
        self.server = server
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "nami-core", "version": "0.13.0"}})

    async def close(self) -> None:
        return

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self.server.url:
            raise McpClientError(f"{self.server.transport} MCP server requires url: {self.server.name}")
        async with self._lock:
            request_id = self._next_id
            self._next_id += 1
            payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
            return await asyncio.to_thread(self._post_json, payload)

    def _post_json(self, payload: dict[str, Any]) -> Any:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.server.url or "", data=data, headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise McpClientError(str(exc)) from exc
        parsed = self._parse_response(body)
        if parsed.get("id") != payload["id"]:
            raise McpClientError(f"MCP response id mismatch from {self.server.name}")
        if "error" in parsed:
            raise McpClientError(str(parsed["error"]))
        return parsed.get("result", {})

    def _parse_response(self, body: str) -> dict[str, Any]:
        stripped = body.strip()
        if stripped.startswith("data:"):
            events = [line[5:].strip() for line in stripped.splitlines() if line.startswith("data:")]
            stripped = events[-1] if events else "{}"
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise McpClientError(f"invalid MCP response from {self.server.name}")
        return parsed

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self.request("tools/list")
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self.request("tools/call", {"name": name, "arguments": arguments})


class WebSocketMcpSession:
    def __init__(self, server: McpServerConfig) -> None:
        self.server = server
        self._socket: Any | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._socket is not None:
            return
        if not self.server.url:
            raise McpClientError(f"websocket MCP server requires url: {self.server.name}")
        try:
            import websockets
        except ImportError as exc:
            raise McpClientError("websocket MCP transport requires the websockets package") from exc
        self._socket = await websockets.connect(self.server.url)
        await self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "nami-core", "version": "0.13.0"}})
        await self.notify("notifications/initialized", {})

    async def close(self) -> None:
        if self._socket is None:
            return
        socket = self._socket
        self._socket = None
        await socket.close()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._socket is None:
            raise McpClientError(f"MCP server is not connected: {self.server.name}")
        async with self._lock:
            request_id = self._next_id
            self._next_id += 1
            payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
            await self._socket.send(json.dumps(payload, ensure_ascii=False))
            while True:
                response = json.loads(await asyncio.wait_for(self._socket.recv(), timeout=10))
                if response.get("id") != request_id:
                    continue
                if "error" in response:
                    raise McpClientError(str(response["error"]))
                return response.get("result", {})

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._socket is None:
            raise McpClientError(f"MCP server is not connected: {self.server.name}")
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        await self._socket.send(json.dumps(payload, ensure_ascii=False))

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self.request("tools/list")
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self.request("tools/call", {"name": name, "arguments": arguments})


class McpClientManager:
    def __init__(self, config: McpConfig) -> None:
        self.config = config
        self._sessions: dict[str, McpSession] = {}
        self._servers: dict[str, McpServerRuntime] = {server.name: McpServerRuntime(server=server, status=server.status(), status_detail=server.status_detail()) for server in config.servers}
        self._tools: dict[str, McpTool] = {}

    async def close(self) -> None:
        await asyncio.gather(*(session.close() for session in self._sessions.values()), return_exceptions=True)
        self._sessions.clear()

    async def reconnect(self, server_name: str) -> McpServerRuntime:
        runtime = self._servers.get(server_name)
        if runtime is None:
            raise McpClientError(f"MCP server not configured: {server_name}")
        session = self._sessions.pop(server_name, None)
        if session is not None:
            await session.close()
        self._tools = {name: tool for name, tool in self._tools.items() if tool.server != server_name}
        runtime.status = runtime.server.status()
        runtime.status_detail = "reconnect requested"
        runtime.tools = []
        runtime.next_retry_at = None
        await self.discover(server_name)
        return runtime

    async def discover(self, server_name: str | None = None) -> None:
        servers = [server for server in self.config.servers if server_name is None or server.name == server_name]
        for server in servers:
            runtime = self._servers[server.name]
            runtime.tools = []
            runtime.last_checked_at = datetime.now(timezone.utc).isoformat()
            if not server.enabled:
                runtime.status = "disabled"
                runtime.status_detail = "server disabled in config"
                runtime.next_retry_at = None
                continue
            try:
                session = self._sessions.get(server.name)
                if session is None:
                    if server.transport == "stdio":
                        session = StdioMcpSession(server)
                    elif server.transport == "sse":
                        session = HttpMcpSession(server)
                    elif server.transport == "websocket":
                        session = WebSocketMcpSession(server)
                    else:
                        raise McpClientError(f"unsupported MCP transport: {server.transport}")
                    self._sessions[server.name] = session
                await session.start()
                discovered = []
                for item in await session.list_tools():
                    name = str(item.get("name", ""))
                    if not name:
                        continue
                    permission_level = server.permission_level
                    read_only = permission_level in {"read_only", "protected_read"}
                    tool = McpTool(
                        name=name,
                        description=str(item.get("description") or f"MCP tool '{name}' from server '{server.name}'."),
                        input_schema=item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else {"type": "object", "additionalProperties": True},
                        server=server.name,
                        namespaced_name=f"{server.to_tool_namespace()}.{name}",
                        permission_level=permission_level,  # type: ignore[arg-type]
                        read_only=read_only,
                    )
                    self._tools[tool.namespaced_name] = tool
                    discovered.append(tool)
                runtime.tools = discovered
                runtime.status = "connected"
                runtime.status_detail = f"connected; {len(discovered)} tools discovered"
                runtime.failure_count = 0
                runtime.next_retry_at = None
            except Exception as exc:
                runtime.status = "error"
                runtime.status_detail = str(exc)
                runtime.failure_count += 1
                retry_delay = min(300, 2 ** min(runtime.failure_count, 8))
                runtime.next_retry_at = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + retry_delay, timezone.utc).isoformat()

    def servers(self) -> list[McpServerRuntime]:
        return [self._servers[server.name] for server in self.config.servers]

    def tools(self) -> list[McpTool]:
        return sorted(self._tools.values(), key=lambda tool: tool.namespaced_name)

    def get_tool(self, namespaced_name: str) -> McpTool | None:
        return self._tools.get(namespaced_name)

    async def call_tool(self, namespaced_name: str, arguments: dict[str, Any]) -> Any:
        tool = self.get_tool(namespaced_name)
        if tool is None:
            await self.discover()
            tool = self.get_tool(namespaced_name)
        if tool is None:
            raise McpClientError(f"MCP tool not registered: {namespaced_name}")
        session = self._sessions.get(tool.server)
        if session is None:
            raise McpClientError(f"MCP server is not connected: {tool.server}")
        return await session.call_tool(tool.name, arguments)
