"""Tests for nami_core.config — YAML harness config loader."""

from __future__ import annotations

import pytest
from pathlib import Path

from nami_core.config import HarnessConfig, load_harness_config


def test_load_signal_config(tmp_path: Path) -> None:
    config_file = tmp_path / "signal_harness.yaml"
    config_file.write_text(
        """
name: signal
allowed_agents:
  - hermes
allowed_actions:
  - generate_signal
  - send_signal
max_daily_actions: 100
rate_limit:
  max_events: 30
  window_seconds: 60
kill_switch_path: /tmp/kill_signal_test
circuit_breaker:
  failure_threshold: 5
budget_guard:
  max_cost: 5.0
quality:
  require_non_empty:
    - signal
    - reason
  forbid_terms:
    - guarantee
sensor_path: /tmp/nami-harness-test/signals.jsonl
""",
        encoding="utf-8",
    )

    config = load_harness_config(config_file)

    assert config.name == "signal"
    assert config.allowed_agents == {"hermes"}
    assert config.allowed_actions == {"generate_signal", "send_signal"}
    assert config.max_daily_actions == 100
    assert config.rate_limit_max_events == 30
    assert config.rate_limit_window_seconds == 60
    assert config.kill_switch_path == "/tmp/kill_signal_test"
    assert config.circuit_breaker_threshold == 5
    assert config.budget_guard_max_cost == 5.0
    assert config.require_non_empty_fields == ["signal", "reason"]
    assert config.forbid_terms_list == ["guarantee"]
    assert config.sensor_path == "/tmp/nami-harness-test/signals.jsonl"


def test_config_builds_runtime(tmp_path: Path) -> None:
    config_file = tmp_path / "minimal.yaml"
    config_file.write_text(
        """
name: minimal
allowed_agents:
  - hermes
allowed_actions:
  - act
quality:
  require_non_empty:
    - answer
""",
        encoding="utf-8",
    )

    config = load_harness_config(config_file)
    runtime = config.build_runtime()

    # Verify runtime works
    from nami_harness.runtime import HarnessContext
    result = runtime.run(
        HarnessContext(agent="hermes", action="act"),
        {"input": "hello"},
        lambda payload: {"answer": payload["input"].upper()},
    )
    assert result.output == {"answer": "HELLO"}


def test_config_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_harness_config("/nonexistent/config.yaml")


def test_config_name_defaults_to_file_stem(tmp_path: Path) -> None:
    config_file = tmp_path / "my_worker.yaml"
    config_file.write_text("allowed_agents: []\n", encoding="utf-8")

    config = load_harness_config(config_file)
    assert config.name == "my_worker"


def test_config_builds_runtime_with_all_layers(tmp_path: Path) -> None:
    config_file = tmp_path / "full.yaml"
    sensor_path = tmp_path / "events.jsonl"
    kill_path = tmp_path / "kill"

    config_file.write_text(
        f"""
name: full
allowed_agents:
  - hermes
allowed_actions:
  - act
rate_limit:
  max_events: 5
  window_seconds: 10
kill_switch_path: {kill_path}
circuit_breaker:
  failure_threshold: 2
budget_guard:
  max_cost: 1.0
quality:
  require_non_empty:
    - answer
  forbid_terms:
    - bad
sensor_path: {sensor_path}
""",
        encoding="utf-8",
    )

    config = load_harness_config(config_file)
    runtime = config.build_runtime()

    # All layers should be present
    assert runtime.rails is not None
    assert runtime.quality is not None
    assert runtime.sensor is not None
    assert runtime.kill_switch is not None
    assert runtime.circuit_breaker is not None
    assert runtime.budget_guard is not None
