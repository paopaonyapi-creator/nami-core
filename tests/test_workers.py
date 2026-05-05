"""Tests for all nami_workers — verify each worker dispatches correctly."""

from __future__ import annotations

import pytest

from nami_core.config import HarnessConfig
from nami_core.hermes import Hermes
from nami_harness.quality import QualityGate, forbid_terms, require_non_empty
from nami_harness.rails import RailPolicy
from nami_harness.runtime import HarnessRuntime
from nami_workers import ALL_WORKERS


def _make_hermes_with_workers() -> Hermes:
    """Build a Hermes with all workers registered and harnessed."""
    hermes = Hermes()

    for name, task_fn in ALL_WORKERS.items():
        # Signal worker needs strict quality gate
        if name == "signal":
            runtime = HarnessRuntime(
                rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"generate_signal", "send_signal", "send_dm"}),
                quality=QualityGate([require_non_empty("signal"), forbid_terms("guarantee", "แน่นอน", "100%", "การันตีกำไร")]),
            )
        elif name == "signal_send":
            # send_signal returns {sent, message} not {signal}
            runtime = HarnessRuntime(
                rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"send_signal"}),
                quality=QualityGate([require_non_empty("message")]),
            )
        elif name == "proxy":
            runtime = HarnessRuntime(
                rails=RailPolicy(allowed_agents={"hermes", "external"}, allowed_actions={"chat_completion", "list_models", "embed"}),
                quality=QualityGate([]),
            )
        elif name == "lottery":
            runtime = HarnessRuntime(
                rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"predict", "send_prediction", "fetch_results"}),
                quality=QualityGate([require_non_empty("prediction")]),
            )
        elif name == "trading":
            runtime = HarnessRuntime(
                rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"paper_trade", "analyze_signal", "check_position"}),
                quality=QualityGate([require_non_empty("signal")]),
            )
        else:
            runtime = HarnessRuntime(
                rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"act", "help", "status", "route", "health", "relay", "subscribe", "query", "analyze", "impact", "package_info"}),
                quality=QualityGate([]),
            )

        hermes.register(name, runtime, task_fn)

    return hermes


# === Signal Worker ===

def test_signal_worker_generate() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("signal", "generate_signal", {"task": "gold_daily"})
    assert "signal" in result.output
    assert "reason" in result.output
    assert result.passed_quality is True


def test_signal_worker_send() -> None:
    from nami_workers.signal_worker import send_signal
    result = send_signal({
        "action": "send_signal",
        "signal": {"signal": "XAU/USD Long", "reason": "breakout", "confidence": "Medium", "symbol": "XAU/USD", "price": "2340", "direction": "Long", "timeframe": "Day", "risk_level": "Medium", "invalidation": "Below 2320", "date": "2026-05-05"},
        "channel": "test",
    })
    assert result["sent"] is True


def test_signal_worker_quality_blocks_guarantee() -> None:
    hermes = _make_hermes_with_workers()

    def bad_signal(payload: dict) -> dict:
        return {"signal": "XAU/USD Long", "reason": "guarantee profit 100%"}

    hermes.register("bad_signal", HarnessRuntime(
        rails=RailPolicy(allowed_agents={"hermes"}, allowed_actions={"generate_signal"}),
        quality=QualityGate([require_non_empty("signal"), forbid_terms("guarantee", "100%")]),
    ), bad_signal)

    from nami_harness.exceptions import QualityGateFailed
    with pytest.raises(QualityGateFailed):
        hermes.dispatch("bad_signal", "generate_signal", {})


# === Proxy Worker ===

def test_proxy_worker_chat_completion() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("proxy", "chat_completion", {"model": "claude-3-sonnet", "messages": [{"role": "user", "content": "hello"}]})
    assert "response" in result.output
    assert result.passed_quality is True


def test_proxy_worker_list_models() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("proxy", "list_models", {"action": "list_models"})
    assert "models" in result.output


# === Lottery Worker ===

def test_lottery_worker_predict() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("lottery", "predict", {"region": "hanoi"})
    assert "prediction" in result.output
    assert result.output["region"] == "hanoi"
    assert result.passed_quality is True


def test_lottery_worker_unknown_region() -> None:
    from nami_workers.lottery_worker import lottery_worker
    result = lottery_worker({"action": "predict", "region": "invalid"})
    assert "error" in result


# === Bot Worker ===

def test_bot_worker_help() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("bot", "help", {})
    assert "answer" in result.output


def test_bot_worker_package_info() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("bot", "package_info", {"action": "package_info"})
    assert "answer" in result.output
    assert "299" in result.output["answer"]


def test_bot_worker_subscribe() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("bot", "subscribe", {"action": "subscribe", "package": "pro"})
    assert "answer" in result.output
    assert "Pro" in result.output["answer"]


# === Trading Worker ===

def test_trading_worker_paper_trade() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("trading", "paper_trade", {"action": "paper_trade", "symbol": "XAU_USD", "direction": "Long"})
    assert result.output["executed"] is True
    assert result.output["mode"] == "paper"
    assert result.passed_quality is True


def test_trading_worker_analyze() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("trading", "analyze_signal", {"signal": "test"})
    assert "valid" in result.output


# === Gateway Worker ===

def test_gateway_worker_route_signal() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("gateway", "route", {"path": "/api/signal/generate", "method": "POST"})
    assert result.output["routed"] is True
    assert result.output["worker"] == "signal"


def test_gateway_worker_health() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("gateway", "health", {"action": "health"})
    assert result.output["status"] == "ok"


# === Status Worker ===

def test_status_worker_health() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("status", "health", {})
    assert result.output["status"] == "ok"


# === Bridge Worker ===

def test_bridge_worker_relay() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("bridge", "relay", {"event_type": "signal", "data": {}})
    assert result.output["relayed"] is True


# === Graphify Worker ===

def test_graphify_worker_query() -> None:
    hermes = _make_hermes_with_workers()
    result = hermes.dispatch("graphify", "query", {"cypher": "MATCH (n) RETURN n", "repo": "test"})
    assert "results" in result.output


# === All Workers Registered ===

def test_all_workers_registered() -> None:
    hermes = _make_hermes_with_workers()
    workers = hermes.list_workers()
    expected = set(ALL_WORKERS.keys())
    assert set(workers) == expected
