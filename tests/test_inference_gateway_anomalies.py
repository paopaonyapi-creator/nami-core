"""Tests for D10/D11 wiring on InferenceGateway._record_call_anomalies."""

from __future__ import annotations

from nami_core.inference_gateway import InferenceGateway
from nami_core.safety.runner import get_detection_counts, reset_detection_counts


def _new_gateway() -> InferenceGateway:
    """Build a gateway without loading policy (no env required)."""
    g = InferenceGateway.__new__(InferenceGateway)
    g.policy = None  # not used by _record_call_anomalies
    g._call_stats = {}
    return g


def _warm(gateway: InferenceGateway, model: str, cost: float, latency: float, n: int = 30) -> None:
    """Push n baseline calls so RollingP95 has enough samples (>=20)."""
    for _ in range(n):
        gateway._record_call_anomalies(model, cost, int(latency))


def test_baseline_calls_no_detection() -> None:
    reset_detection_counts()
    g = _new_gateway()
    _warm(g, "gpt-4o-mini", cost=0.01, latency=200, n=30)
    counts = get_detection_counts()
    assert counts.get(("D10", "alert"), 0) == 0
    assert counts.get(("D11", "alert"), 0) == 0


def test_thin_baseline_no_detection_even_on_huge_call() -> None:
    """RollingP95 returns None below 20 samples; outliers cannot trigger."""
    reset_detection_counts()
    g = _new_gateway()
    _warm(g, "gpt-4o-mini", cost=0.01, latency=200, n=5)
    g._record_call_anomalies("gpt-4o-mini", cost_usd=10.0, latency_ms=100_000)
    counts = get_detection_counts()
    assert counts.get(("D10", "alert"), 0) == 0
    assert counts.get(("D11", "alert"), 0) == 0


def test_d10_cost_outlier_emits_metric() -> None:
    reset_detection_counts()
    g = _new_gateway()
    _warm(g, "gpt-4o-mini", cost=0.01, latency=200, n=30)
    g._record_call_anomalies("gpt-4o-mini", cost_usd=0.50, latency_ms=200)
    counts = get_detection_counts()
    assert counts.get(("D10", "alert"), 0) >= 1


def test_d11_latency_outlier_emits_metric() -> None:
    reset_detection_counts()
    g = _new_gateway()
    _warm(g, "gpt-4o-mini", cost=0.01, latency=200, n=30)
    g._record_call_anomalies("gpt-4o-mini", cost_usd=0.01, latency_ms=10_000)
    counts = get_detection_counts()
    assert counts.get(("D11", "alert"), 0) >= 1


def test_per_model_stats_are_independent() -> None:
    reset_detection_counts()
    g = _new_gateway()
    _warm(g, "gpt-4o-mini", cost=0.01, latency=200, n=30)
    # Different model has zero baseline → cannot fire D10/D11.
    g._record_call_anomalies("claude-haiku", cost_usd=10.0, latency_ms=10_000)
    counts = get_detection_counts()
    assert counts.get(("D10", "alert"), 0) == 0
    assert counts.get(("D11", "alert"), 0) == 0


def test_record_anomalies_swallows_internal_failures() -> None:
    """Best-effort contract: a broken stats lookup must not crash the call."""
    reset_detection_counts()
    g = _new_gateway()
    # Sabotage the stats lookup; helper must catch and return cleanly.
    g._stats_for = lambda model: (_ for _ in ()).throw(RuntimeError("boom"))
    g._record_call_anomalies("gpt-4o-mini", cost_usd=0.01, latency_ms=200)
    # No detections, no exception — that's the contract.


def test_call_stats_dict_is_bounded_to_cap() -> None:
    """Hardening: feeding many distinct model names must not grow _call_stats unbounded."""
    g = _new_gateway()
    cap = InferenceGateway._STATS_CAP
    for i in range(cap + 50):
        g._record_call_anomalies(f"model-{i}", cost_usd=0.01, latency_ms=100)
    assert len(g._call_stats) <= cap
    # FIFO eviction: oldest entries gone, latest still present.
    assert "model-0" not in g._call_stats
    assert f"model-{cap + 49}" in g._call_stats
