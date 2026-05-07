"""Tests for nami_workers.registry — worker plugin registry."""

from __future__ import annotations

from pathlib import Path

from nami_core.config import load_harness_config
from nami_core.hermes import Hermes
from nami_harness.quality import QualityGate, require_non_empty
from nami_harness.rails import RailPolicy
from nami_harness.runtime import HarnessRuntime
from nami_workers.registry import WorkerRegistry


def test_registry_registers_and_gets_worker() -> None:
    registry = WorkerRegistry()

    def my_task(payload: dict) -> dict:
        return {"result": "ok"}

    registry.register("test", my_task)
    entry = registry.get("test")

    assert entry.name == "test"
    assert entry.task is my_task


def test_registry_rejects_duplicate() -> None:
    registry = WorkerRegistry()
    registry.register("dup", lambda p: p)

    import pytest
    with pytest.raises(ValueError, match="already registered"):
        registry.register("dup", lambda p: p)


def test_registry_lists_workers() -> None:
    registry = WorkerRegistry()
    registry.register("alpha", lambda p: p)
    registry.register("beta", lambda p: p)

    assert sorted(registry.list_workers()) == ["alpha", "beta"]


def test_registry_wires_into_hermes() -> None:
    registry = WorkerRegistry()

    def signal_task(payload: dict) -> dict:
        return {"signal": "XAU/USD Long", "reason": "breakout"}

    config_file = None
    # Register with a simple harness config inline
    from nami_core.config import HarnessConfig
    config = HarnessConfig(
        name="signal",
        allowed_agents={"hermes"},
        allowed_actions={"generate_signal"},
        require_non_empty_fields=["signal", "reason"],
        forbid_terms_list=["guarantee"],
    )

    registry.register("signal", signal_task, config=config)

    hermes = Hermes()
    registry.wire_into_hermes(hermes)

    result = hermes.dispatch("signal", "generate_signal", {"task": "gold"})
    assert result.output["signal"] == "XAU/USD Long"
    assert result.passed_quality is True


def test_registry_wires_worker_without_config() -> None:
    registry = WorkerRegistry()

    def simple_task(payload: dict) -> dict:
        return {"answer": "done"}

    registry.register("simple", simple_task)

    hermes = Hermes()
    registry.wire_into_hermes(hermes)

    result = hermes.dispatch("simple", "act", {})
    assert result.output == {"answer": "done"}


def test_registry_loads_from_directory(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    (config_dir / "worker_a.yaml").write_text(
        """
name: worker_a
allowed_agents:
  - hermes
allowed_actions:
  - act
""",
        encoding="utf-8",
    )
    (config_dir / "worker_b.yaml").write_text(
        """
name: worker_b
allowed_agents:
  - hermes
allowed_actions:
  - run
""",
        encoding="utf-8",
    )

    registry = WorkerRegistry()
    registry.load_from_directory(config_dir)

    assert "worker_a" in registry.list_workers()
    assert "worker_b" in registry.list_workers()

def test_registry_skips_non_worker_yaml(tmp_path):
    from pathlib import Path
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    (config_dir / "worker_a.yaml").write_text(
        """
name: worker_a
allowed_agents:
  - hermes
allowed_actions:
  - act
""",
        encoding="utf-8",
    )
    (config_dir / "mcp_servers.example.yaml").write_text(
        """
servers:
  - name: local_tools
    transport: stdio
""",
        encoding="utf-8",
    )

    registry = WorkerRegistry()
    registry.load_from_directory(config_dir)

    assert "worker_a" in registry.list_workers()
    assert "mcp_servers.example" not in registry.list_workers()
