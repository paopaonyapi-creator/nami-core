"""MCP configuration loader for Nami Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

McpTransport = Literal["stdio", "sse", "websocket"]


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    transport: McpTransport
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    tool_prefix: str | None = None
    permission_level: str = "protected_read"

    def to_tool_namespace(self) -> str:
        return self.tool_prefix or f"mcp.{self.name}"

    def status(self) -> str:
        return "configured" if self.enabled else "disabled"

    def status_detail(self) -> str:
        if not self.enabled:
            return "server disabled in config"
        return "configured; connection not opened by discovery"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": self.args,
            "url": self.url,
            "env": self.env,
            "enabled": self.enabled,
            "tool_prefix": self.tool_prefix,
            "tool_namespace": self.to_tool_namespace(),
            "permission_level": self.permission_level,
            "status": self.status(),
            "status_detail": self.status_detail(),
        }


@dataclass(frozen=True)
class McpConfig:
    servers: list[McpServerConfig] = field(default_factory=list)

    def enabled_servers(self) -> list[McpServerConfig]:
        return [server for server in self.servers if server.enabled]


def _as_string_dict(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("env must be a mapping")
    return {str(key): str(item) for key, item in value.items()}


def _load_server(raw: dict[str, Any]) -> McpServerConfig:
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("MCP server name is required")
    transport = raw.get("transport", "stdio")
    if transport not in {"stdio", "sse", "websocket"}:
        raise ValueError(f"unsupported MCP transport for {name}: {transport}")
    command = raw.get("command")
    url = raw.get("url")
    if transport == "stdio" and not command:
        raise ValueError(f"stdio MCP server requires command: {name}")
    if transport in {"sse", "websocket"} and not url:
        raise ValueError(f"{transport} MCP server requires url: {name}")
    args = raw.get("args", [])
    if not isinstance(args, list):
        raise ValueError(f"MCP server args must be a list: {name}")
    return McpServerConfig(
        name=name,
        transport=transport,
        command=command,
        args=[str(arg) for arg in args],
        url=url,
        env=_as_string_dict(raw.get("env")),
        enabled=bool(raw.get("enabled", True)),
        tool_prefix=raw.get("tool_prefix"),
        permission_level=str(raw.get("permission_level", "protected_read")),
    )


def load_mcp_config(path: str | Path) -> McpConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"MCP config not found: {path}")
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"MCP config must be a mapping: {path}")
    servers = raw.get("servers", [])
    if not isinstance(servers, list):
        raise ValueError("MCP config servers must be a list")
    return McpConfig(servers=[_load_server(server) for server in servers])
