"""Tests for inference-call + burn-pattern safety helpers (D5/D10/D11)."""

from __future__ import annotations

from nami_core.agent.safety_metrics import (
    InferenceCallStats,
    RollingP95,
    check_burn_pattern,
    check_call_anomaly,
)
from nami_core.agent.state import AgentState, AgentStep


# ── RollingP95 ─────────────────────────────────────────────────────────


def test_rolling_p95_too_few_samples_returns_none() -> None:
    p = RollingP95()
    for v in [0.01] * 10:
        p.push(v)
    assert p.value() is None


def test_rolling_p95_value_on_20_samples() -> None:
    p = RollingP95()
    for v in range(1, 21):  # 1..20
        p.push(float(v))
    # p95 of 1..20 → index round(0.95*19)=18 → value 19
    assert p.value() == 19.0


def test_rolling_p95_window_evicts_oldest() -> None:
    p = RollingP95(window=20)
    for v in range(1, 100):  # 99 samples; window keeps last 20
        p.push(float(v))
    assert len(p) == 20
    # Last 20 are 80..99 → p95 index 18 → value 98
    assert p.value() == 98.0


def test_rolling_p95_ignores_none() -> None:
    p = RollingP95()
    p.push(None)  # type: ignore[arg-type]
    assert len(p) == 0


# ── InferenceCallStats ─────────────────────────────────────────────────


def test_stats_records_only_positive_values() -> None:
    s = InferenceCallStats()
    s.record(cost_usd=0.0, latency_ms=0.0)
    s.record(cost_usd=-1.0, latency_ms=-5.0)
    s.record(cost_usd=0.05, latency_ms=200.0)
    assert len(s.cost) == 1
    assert len(s.latency) == 1


# ── check_call_anomaly (D10 + D11) ─────────────────────────────────────


def _warm_stats(cost: float, latency: float, n: int = 30) -> InferenceCallStats:
    s = InferenceCallStats()
    for _ in range(n):
        s.record(cost_usd=cost, latency_ms=latency)
    return s


def test_no_anomaly_within_band() -> None:
    s = _warm_stats(cost=0.01, latency=200.0)
    dets = check_call_anomaly(role="planner", cost_usd=0.02, latency_ms=300.0, stats=s)
    assert dets == []


def test_d10_cost_outlier_flagged() -> None:
    s = _warm_stats(cost=0.01, latency=200.0)
    dets = check_call_anomaly(role="planner", cost_usd=0.20, latency_ms=200.0, stats=s)
    patterns = {d.pattern for d in dets}
    assert "D10" in patterns
    cost_det = next(d for d in dets if d.pattern == "D10")
    assert cost_det.metadata["role"] == "planner"


def test_d11_latency_outlier_flagged() -> None:
    s = _warm_stats(cost=0.01, latency=200.0)
    dets = check_call_anomaly(role="executor", cost_usd=0.02, latency_ms=5000.0, stats=s)
    patterns = {d.pattern for d in dets}
    assert "D11" in patterns


def test_both_outliers_flagged_together() -> None:
    s = _warm_stats(cost=0.01, latency=200.0)
    dets = check_call_anomaly(role="critic", cost_usd=0.50, latency_ms=10000.0, stats=s)
    patterns = {d.pattern for d in dets}
    assert patterns == {"D10", "D11"}


def test_no_anomaly_when_baseline_too_thin() -> None:
    s = InferenceCallStats()
    for _ in range(5):
        s.record(cost_usd=0.01, latency_ms=200.0)
    # rolling p95 returns None below 20 samples → no detection possible
    dets = check_call_anomaly(role="planner", cost_usd=10.0, latency_ms=10000.0, stats=s)
    assert dets == []


# ── check_burn_pattern (D5) ────────────────────────────────────────────


def _state_with_plan_costs(costs: list[float]) -> AgentState:
    s = AgentState(job_id="j1", trace_id="t1", parent_id=None, goal="g")
    for cost in costs:
        s.add_step(AgentStep(kind="plan", content="", cost_usd=cost))
    return s


def test_burn_pattern_front_loaded_alerts() -> None:
    state = _state_with_plan_costs([0.40, 0.04, 0.03, 0.02, 0.01])
    det = check_burn_pattern(state, budget_total_usd=1.0)
    assert det is not None
    assert det.pattern == "D5"
    assert det.metadata["job_id"] == "j1"


def test_burn_pattern_even_spend_no_alert() -> None:
    state = _state_with_plan_costs([0.10] * 5)
    assert check_burn_pattern(state, budget_total_usd=1.0) is None


def test_burn_pattern_zero_budget_skipped() -> None:
    state = _state_with_plan_costs([0.40, 0.04, 0.03, 0.02, 0.01])
    assert check_burn_pattern(state, budget_total_usd=0.0) is None


def test_burn_pattern_no_plan_costs_skipped() -> None:
    state = _state_with_plan_costs([])
    assert check_burn_pattern(state, budget_total_usd=1.0) is None


def test_burn_pattern_only_plan_steps_counted() -> None:
    state = _state_with_plan_costs([0.40, 0.04, 0.03, 0.02, 0.01])
    # Add act/observe with cost — must NOT confuse the detector.
    state.add_step(AgentStep(kind="act", content="", cost_usd=99.0))
    state.add_step(AgentStep(kind="observe", content="", cost_usd=99.0))
    det = check_burn_pattern(state, budget_total_usd=1.0)
    assert det is not None
    assert det.metadata["iters"] == 5
