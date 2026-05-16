"""Agent tool registry — Phase 27 PR-B.

Stub MCP bridge. Real sandboxed MCP arrives in Phase 28
(see CODEX_EXECUTION_PLAN.md). The registry contract here is what
Phase 28's `nami_core.mcp` will plug into without changing call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

ToolFn = Callable[[dict[str, Any]], "ToolResult"]


@dataclass
class ToolResult:
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class Tool:
    name: str
    description: str
    fn: ToolFn

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        try:
            return self.fn(args)
        except Exception as exc:  # noqa: BLE001 — boundary catch for tool failures
            return ToolResult(ok=False, error=str(exc))


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def invoke(self, name: str, args: dict[str, Any]) -> ToolResult:
        return self.get(name).invoke(args)


def default_registry() -> ToolRegistry:
    """Stub registry with a no-op `echo` tool.

    Phase 28 replaces this with the sandboxed MCP bridge that loads
    `filesystem`, `git`, and `web_fetch` per GOVERNANCE §5 capability
    scopes.
    """
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="echo",
            description="Returns its input verbatim. Stub for testing.",
            fn=lambda args: ToolResult(ok=True, output={"echo": args}),
        )
    )
    return reg


__all__ = ["Tool", "ToolFn", "ToolRegistry", "ToolResult", "default_registry"]
