"""MCP server registry — Phase 28.

Loads declarative server specs from YAML and enforces capability scopes
per GOVERNANCE §5. Acts as the single source of truth for "which roles
may invoke which tools on which MCP servers".
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from nami_core.mcp.types import (
    CapabilityDenied,
    CapabilityScope,
    MCPServerSpec,
    ServerNotFound,
)

logger = logging.getLogger("nami_core.mcp.registry")


def _default_servers_dir() -> Path:
    return Path(os.environ.get("NAMI_MCP_SERVERS_DIR", "config/mcp_servers"))


def _parse_scopes(raw: Any) -> tuple[CapabilityScope, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError("scopes must be a list")
    scopes: list[CapabilityScope] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each scope must be a mapping")
        tool = item.get("tool")
        if not isinstance(tool, str) or not tool:
            raise ValueError("scope.tool required")
        roles_raw = item.get("roles") or []
        if not isinstance(roles_raw, list) or not all(isinstance(r, str) for r in roles_raw):
            raise ValueError("scope.roles must be a list of strings")
        constraints = item.get("constraints") or {}
        if not isinstance(constraints, dict):
            raise ValueError("scope.constraints must be a mapping")
        scopes.append(
            CapabilityScope(
                server=str(item.get("server") or ""),
                tool=tool,
                roles=tuple(roles_raw),
                constraints=dict(constraints),
            )
        )
    return tuple(scopes)


def parse_server_spec(name: str, raw: dict[str, Any]) -> MCPServerSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"server spec for {name} must be a mapping")
    cmd = raw.get("command")
    if isinstance(cmd, str):
        command = [cmd]
    elif isinstance(cmd, list) and all(isinstance(c, str) for c in cmd):
        command = list(cmd)
    else:
        raise ValueError(f"{name}.command must be a string or list of strings")
    args_raw = raw.get("args") or []
    if not isinstance(args_raw, list) or not all(isinstance(a, str) for a in args_raw):
        raise ValueError(f"{name}.args must be a list of strings")
    env_raw = raw.get("env") or {}
    if not isinstance(env_raw, dict):
        raise ValueError(f"{name}.env must be a mapping")
    paths_raw = raw.get("allowed_paths") or []
    if not isinstance(paths_raw, list) or not all(isinstance(p, str) for p in paths_raw):
        raise ValueError(f"{name}.allowed_paths must be a list of strings")
    scopes = _parse_scopes(raw.get("scopes"))
    # Normalize each scope's server field to this spec name for consistency.
    scopes = tuple(
        CapabilityScope(server=name, tool=s.tool, roles=s.roles, constraints=dict(s.constraints))
        for s in scopes
    )
    return MCPServerSpec(
        name=name,
        command=command,
        args=list(args_raw),
        env={str(k): str(v) for k, v in env_raw.items()},
        working_dir=str(raw["working_dir"]) if raw.get("working_dir") else None,
        allowed_paths=tuple(paths_raw),
        network=bool(raw.get("network", False)),
        timeout_seconds=int(raw.get("timeout_seconds", 30)),
        scopes=scopes,
    )


class MCPRegistry:
    def __init__(self) -> None:
        self._servers: dict[str, MCPServerSpec] = {}

    def register(self, spec: MCPServerSpec) -> None:
        if spec.name in self._servers:
            raise ValueError(f"MCP server already registered: {spec.name}")
        self._servers[spec.name] = spec

    def get(self, name: str) -> MCPServerSpec:
        if name not in self._servers:
            raise ServerNotFound(f"unknown MCP server: {name}")
        return self._servers[name]

    def names(self) -> list[str]:
        return sorted(self._servers.keys())

    def load_from_directory(self, directory: str | Path | None = None) -> int:
        path = Path(directory) if directory else _default_servers_dir()
        if not path.exists():
            logger.info("MCP servers dir not found: %s", path)
            return 0
        count = 0
        for yaml_path in sorted(path.glob("*.yaml")):
            with yaml_path.open(encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
            if not isinstance(raw, dict):
                raise ValueError(f"{yaml_path}: top-level must be a mapping")
            name = str(raw.get("name") or yaml_path.stem)
            spec = parse_server_spec(name, raw)
            self.register(spec)
            count += 1
        return count

    def authorize(self, server: str, tool: str, role: str) -> CapabilityScope:
        """Returns the matching scope or raises `CapabilityDenied`."""
        spec = self.get(server)
        scope = spec.scope_for(tool)
        if scope is None:
            raise CapabilityDenied(f"no scope defined: {server}.{tool}")
        if not scope.allows(role):
            raise CapabilityDenied(
                f"role '{role}' denied for {server}.{tool}; allowed: {scope.roles}"
            )
        return scope


__all__ = ["MCPRegistry", "parse_server_spec"]
