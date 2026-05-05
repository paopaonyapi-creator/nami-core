"""Tests for nami_core.hermes — Hermes router and dispatcher."""

from __future__ import annotations

import pytest

from nami_core.hermes import Hermes
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty
from nami_harness.rails import RailPolicy
from nami_harness.runtime import HarnessRuntime


def test_hermes_registers_and_dispatches_worker() -> None:
    hermes = Hermes()
    runtime = HarnessRuntime(
        rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"summarize"}),
        quality=QualityGate([require_non_empty("answer")]),
    )

    def worker(payload: dict) -> dict:
        return {"answer": f"processed: {payload['task']}"}

    hermes.register("test_worker", runtime, worker, actions={"summarize"})
    result = hermes.dispatch("test_worker", "summarize", {"task": "hello"})

    assert result.output == {"answer": "processed: hello"}
    assert result.passed_quality is True


def test_hermes_rejects_duplicate_worker() -> None:
    hermes = Hermes()
    runtime = HarnessRuntime(rails=RailPolicy(), quality=QualityGate([]))

    hermes.register("dup", runtime, lambda p: p)
    with pytest.raises(ValueError, match="already registered"):
        hermes.register("dup", runtime, lambda p: p)


def test_hermes_rejects_unknown_worker() -> None:
    hermes = Hermes()

    with pytest.raises(ValueError, match="unknown worker"):
        hermes.dispatch("nonexistent", "act", {})


def test_hermes_list_workers() -> None:
    hermes = Hermes()
    runtime = HarnessRuntime(rails=RailPolicy(), quality=QualityGate([]))

    hermes.register("alpha", runtime, lambda p: p)
    hermes.register("beta", runtime, lambda p: p)

    assert sorted(hermes.list_workers()) == ["alpha", "beta"]


def test_hermes_worker_actions() -> None:
    hermes = Hermes()
    runtime = HarnessRuntime(rails=RailPolicy(), quality=QualityGate([]))

    hermes.register("worker", runtime, lambda p: p, actions={"read", "write"})

    assert hermes.worker_actions("worker") == {"read", "write"}


def test_hermes_quality_gate_blocks_bad_output() -> None:
    hermes = Hermes()
    runtime = HarnessRuntime(
        rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"draft"}),
        quality=QualityGate([forbid_terms("secret")]),
    )

    def leaky_worker(payload: dict) -> dict:
        return {"answer": "the secret is 123"}

    hermes.register("leaky", runtime, leaky_worker, actions={"draft"})

    from nami_harness.exceptions import QualityGateFailed
    with pytest.raises(QualityGateFailed):
        hermes.dispatch("leaky", "draft", {})


def test_hermes_rails_block_unauthorized_agent() -> None:
    hermes = Hermes()
    runtime = HarnessRuntime(
        rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"act"}),
        quality=QualityGate([]),
    )

    hermes.register("guarded", runtime, lambda p: {"ok": True}, actions={"act"})

    from nami_harness.exceptions import RailDenied
    with pytest.raises(RailDenied):
        hermes.dispatch("guarded", "act", {}, agent="unauthorized")
