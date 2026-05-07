"""Tests for MCP config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from nami_core.mcp_config import load_mcp_config


def test_load_mcp_config_with_stdio_and_sse_servers(tmp_path: Path) -> None:
    config_file = tmp_path / "mcp.yaml"
    config_file.write_text(
        """
servers:
  - name: local_tools
    transport: stdio
    command: node
    args:
      - server.js
    env:
      MODE: test
    tool_prefix: mcp.local
  - name: search
    transport: sse
    url: http://127.0.0.1:8001/sse
    enabled: false
    permission_level: read_only
""",
        encoding="utf-8",
    )

    config = load_mcp_config(config_file)

    assert len(config.servers) == 2
    assert config.servers[0].name == "local_tools"
    assert config.servers[0].transport == "stdio"
    assert config.servers[0].command == "node"
    assert config.servers[0].args == ["server.js"]
    assert config.servers[0].env == {"MODE": "test"}
    assert config.servers[0].to_tool_namespace() == "mcp.local"
    assert config.servers[1].transport == "sse"
    assert config.servers[1].url == "http://127.0.0.1:8001/sse"
    assert config.servers[1].enabled is False
    assert [server.name for server in config.enabled_servers()] == ["local_tools"]


def test_mcp_config_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_mcp_config("/not/a/real/mcp.yaml")


def test_mcp_config_requires_command_for_stdio(tmp_path: Path) -> None:
    config_file = tmp_path / "mcp.yaml"
    config_file.write_text("servers:\n  - name: broken\n    transport: stdio\n", encoding="utf-8")

    with pytest.raises(ValueError, match="requires command"):
        load_mcp_config(config_file)


def test_mcp_config_requires_url_for_remote_transport(tmp_path: Path) -> None:
    config_file = tmp_path / "mcp.yaml"
    config_file.write_text("servers:\n  - name: broken\n    transport: websocket\n", encoding="utf-8")

    with pytest.raises(ValueError, match="requires url"):
        load_mcp_config(config_file)