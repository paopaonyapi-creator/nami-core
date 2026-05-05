"""Harness configuration loader from YAML files.

Each worker has its own YAML config defining rails, brakes,
quality, and sensor settings. This module loads and validates
those configs, then builds HarnessRuntime instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from nami_harness.brakes import BudgetGuard, CircuitBreaker, FileKillSwitch
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty
from nami_harness.rails import RailPolicy, RateLimitRail
from nami_harness.runtime import HarnessRuntime
from nami_harness.sensors import JsonlSensor


@dataclass
class HarnessConfig:
    """Parsed harness configuration for one worker."""

    name: str
    allowed_agents: set[str] = field(default_factory=set)
    allowed_actions: set[str] = field(default_factory=set)
    max_daily_actions: int | None = None
    rate_limit_max_events: int | None = None
    rate_limit_window_seconds: float | None = None
    kill_switch_path: str | None = None
    circuit_breaker_threshold: int | None = None
    budget_guard_max_cost: float | None = None
    require_non_empty_fields: list[str] = field(default_factory=list)
    forbid_terms_list: list[str] = field(default_factory=list)
    sensor_path: str | None = None

    def build_runtime(self) -> HarnessRuntime:
        rate_limit: RateLimitRail | None = None
        if self.rate_limit_max_events is not None and self.rate_limit_window_seconds is not None:
            rate_limit = RateLimitRail(
                max_events=self.rate_limit_max_events,
                window_seconds=self.rate_limit_window_seconds,
            )

        rails = RailPolicy(
            allowed_agents=self.allowed_agents,
            allowed_actions=self.allowed_actions,
            max_daily_actions=self.max_daily_actions,
            rate_limit=rate_limit,
        )

        checks: list = []
        for f in self.require_non_empty_fields:
            checks.append(require_non_empty(f))
        if self.forbid_terms_list:
            checks.append(forbid_terms(*self.forbid_terms_list))
        quality = QualityGate(checks) if checks else QualityGate([])

        kill_switch: FileKillSwitch | None = None
        if self.kill_switch_path:
            kill_switch = FileKillSwitch(self.kill_switch_path)

        circuit_breaker: CircuitBreaker | None = None
        if self.circuit_breaker_threshold is not None:
            circuit_breaker = CircuitBreaker(failure_threshold=self.circuit_breaker_threshold)

        budget_guard: BudgetGuard | None = None
        if self.budget_guard_max_cost is not None:
            budget_guard = BudgetGuard(max_cost=self.budget_guard_max_cost)

        sensor: JsonlSensor | None = None
        if self.sensor_path:
            sensor = JsonlSensor(self.sensor_path)

        return HarnessRuntime(
            rails=rails,
            quality=quality,
            sensor=sensor,
            kill_switch=kill_switch,
            circuit_breaker=circuit_breaker,
            budget_guard=budget_guard,
        )


def load_harness_config(path: str | Path) -> HarnessConfig:
    """Load a harness config from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")

    with path.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"config must be a mapping: {path}")

    return HarnessConfig(
        name=raw.get("name", path.stem),
        allowed_agents=set(raw.get("allowed_agents", [])),
        allowed_actions=set(raw.get("allowed_actions", [])),
        max_daily_actions=raw.get("max_daily_actions"),
        rate_limit_max_events=raw.get("rate_limit", {}).get("max_events"),
        rate_limit_window_seconds=raw.get("rate_limit", {}).get("window_seconds"),
        kill_switch_path=raw.get("kill_switch_path"),
        circuit_breaker_threshold=raw.get("circuit_breaker", {}).get("failure_threshold"),
        budget_guard_max_cost=raw.get("budget_guard", {}).get("max_cost"),
        require_non_empty_fields=raw.get("quality", {}).get("require_non_empty", []),
        forbid_terms_list=raw.get("quality", {}).get("forbid_terms", []),
        sensor_path=raw.get("sensor_path"),
    )
