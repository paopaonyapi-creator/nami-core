"""Phase 28: registry + capability scope tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nami_core.mcp import (
    CapabilityDenied,
    MCPRegistry,
    MCPServerSpec,
    ServerNotFound,
    parse_server_spec,
)
from nami_core.mcp.types import CapabilityScope


def _spec_dict(**overrides):
    base = {
        "name": "fs",
        "command": "fs-server",
        "args": ["--root", "/tmp"],
        "allowed_paths": ["/tmp"],
        "network": False,
        "scopes": [
            {"tool": "read", "roles": ["agent", "researcher"]},
            {"tool": "write", "roles": ["agent"]},
            {"tool": "delete", "roles": [], "constraints": {"x": 1}},
        ],
    }
    base.update(overrides)
    return base


# ── parse ──────────────────────────────────────────────────────────────


def test_parse_server_spec_minimal() -> None:
    spec = parse_server_spec("fs", _spec_dict())
    assert spec.name == "fs"
    assert spec.command == ["fs-server"]
    assert spec.args == ["--root", "/tmp"]
    assert spec.allowed_paths == ("/tmp",)
    assert spec.network is False
    assert len(spec.scopes) == 3


def test_parse_server_spec_command_as_list() -> None:
    spec = parse_server_spec("g", _spec_dict(command=["npx", "-y", "@x/y"]))
    assert spec.command == ["npx", "-y", "@x/y"]


def test_parse_server_spec_invalid_command_type() -> None:
    with pytest.raises(ValueError, match="command"):
        parse_server_spec("x", _spec_dict(command=42))


def test_parse_server_spec_invalid_args_type() -> None:
    with pytest.raises(ValueError, match="args"):
        parse_server_spec("x", _spec_dict(args=[1, 2]))


def test_parse_server_spec_invalid_allowed_paths_type() -> None:
    with pytest.raises(ValueError, match="allowed_paths"):
        parse_server_spec("x", _spec_dict(allowed_paths=[1]))


def test_parse_server_spec_invalid_scope_missing_tool() -> None:
    with pytest.raises(ValueError, match="scope.tool"):
        parse_server_spec("x", _spec_dict(scopes=[{"roles": ["a"]}]))


def test_parse_server_spec_invalid_scope_roles() -> None:
    with pytest.raises(ValueError, match="scope.roles"):
        parse_server_spec("x", _spec_dict(scopes=[{"tool": "t", "roles": [1]}]))


def test_parse_server_spec_normalises_scope_server_field() -> None:
    spec = parse_server_spec("fs", _spec_dict())
    assert all(s.server == "fs" for s in spec.scopes)


# ── registry ──────────────────────────────────────────────────────────


def test_registry_register_and_get() -> None:
    reg = MCPRegistry()
    spec = parse_server_spec("fs", _spec_dict())
    reg.register(spec)
    assert reg.names() == ["fs"]
    assert reg.get("fs") is spec


def test_registry_double_register_rejected() -> None:
    reg = MCPRegistry()
    reg.register(parse_server_spec("fs", _spec_dict()))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(parse_server_spec("fs", _spec_dict()))


def test_registry_unknown_server_raises() -> None:
    reg = MCPRegistry()
    with pytest.raises(ServerNotFound):
        reg.get("nope")


def test_registry_loads_from_directory(tmp_path: Path) -> None:
    (tmp_path / "fs.yaml").write_text(yaml.safe_dump(_spec_dict(name="fs")), encoding="utf-8")
    (tmp_path / "git.yaml").write_text(
        yaml.safe_dump(
            _spec_dict(
                name="git",
                allowed_paths=["/repo"],
                scopes=[{"tool": "log", "roles": ["agent"]}],
            )
        ),
        encoding="utf-8",
    )
    reg = MCPRegistry()
    n = reg.load_from_directory(tmp_path)
    assert n == 2
    assert reg.names() == ["fs", "git"]


def test_registry_load_from_missing_dir_returns_zero(tmp_path: Path) -> None:
    reg = MCPRegistry()
    assert reg.load_from_directory(tmp_path / "nope") == 0


# ── authorization (Phase 28 §validation #4) ───────────────────────────


def test_authorize_allows_listed_role() -> None:
    reg = MCPRegistry()
    reg.register(parse_server_spec("fs", _spec_dict()))
    scope = reg.authorize("fs", "read", "researcher")
    assert isinstance(scope, CapabilityScope)
    assert "researcher" in scope.roles


def test_authorize_denies_unlisted_role() -> None:
    """fs.write only allows agent; researcher must be denied."""
    reg = MCPRegistry()
    reg.register(parse_server_spec("fs", _spec_dict()))
    with pytest.raises(CapabilityDenied, match="researcher"):
        reg.authorize("fs", "write", "researcher")


def test_authorize_denies_unknown_tool() -> None:
    reg = MCPRegistry()
    reg.register(parse_server_spec("fs", _spec_dict()))
    with pytest.raises(CapabilityDenied, match="no scope"):
        reg.authorize("fs", "format_disk", "agent")


def test_authorize_unknown_server_raises_server_not_found() -> None:
    reg = MCPRegistry()
    with pytest.raises(ServerNotFound):
        reg.authorize("ghost", "read", "agent")


def test_authorize_empty_roles_denies_all() -> None:
    """fs.delete has roles=[]; nobody allowed by default."""
    reg = MCPRegistry()
    reg.register(parse_server_spec("fs", _spec_dict()))
    with pytest.raises(CapabilityDenied):
        reg.authorize("fs", "delete", "agent")


def test_authorize_wildcard_role_allows_anyone() -> None:
    spec = parse_server_spec(
        "echo",
        _spec_dict(
            name="echo",
            scopes=[{"tool": "ping", "roles": ["*"]}],
        ),
    )
    reg = MCPRegistry()
    reg.register(spec)
    reg.authorize("echo", "ping", "anybody")  # no raise = pass


# ── shipped configs sanity (validates the 3 disk YAMLs parse) ─────────


def test_shipped_filesystem_yaml_parses() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "config" / "mcp_servers" / "filesystem.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = parse_server_spec("filesystem", raw)
    assert spec.name == "filesystem"
    assert spec.network is False
    assert any(s.tool == "read" for s in spec.scopes)


def test_shipped_git_yaml_denies_force_push_for_all() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "config" / "mcp_servers" / "git.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = parse_server_spec("git", raw)
    reg = MCPRegistry()
    reg.register(spec)
    # researcher cannot push (Phase 28 §validation #4 fixture)
    with pytest.raises(CapabilityDenied):
        reg.authorize("git", "push", "researcher")
    # nobody can force_push by default
    with pytest.raises(CapabilityDenied):
        reg.authorize("git", "force_push", "agent")


def test_shipped_web_fetch_yaml_has_no_filesystem_access() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "config" / "mcp_servers" / "web_fetch.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = parse_server_spec("web_fetch", raw)
    assert spec.allowed_paths == ()
    assert spec.network is True
