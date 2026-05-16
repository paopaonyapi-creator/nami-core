"""Tests for evaluator + cache-bypass safety helpers (D3 + D19)."""

from __future__ import annotations

from nami_core.agent.safety_eval import (
    EvaluatorAcceptanceTracker,
    check_cache_bypass,
)


# ── EvaluatorAcceptanceTracker (D3) ────────────────────────────────────


def test_tracker_below_min_window_no_detection() -> None:
    t = EvaluatorAcceptanceTracker()
    for _ in range(50):
        t.record("eval-1", accepted=True)
    assert t.check("eval-1") is None


def test_tracker_100_pct_acceptance_over_100_fires() -> None:
    t = EvaluatorAcceptanceTracker()
    for _ in range(100):
        t.record("eval-1", accepted=True)
    det = t.check("eval-1")
    assert det is not None
    assert det.pattern == "D3"
    assert det.metadata["instance_id"] == "eval-1"
    assert det.metadata["acceptance_rate"] == 1.0


def test_tracker_995_pct_over_200_fires() -> None:
    t = EvaluatorAcceptanceTracker(window=200)
    for _ in range(199):
        t.record("eval-1", accepted=True)
    t.record("eval-1", accepted=False)
    det = t.check("eval-1")
    assert det is not None
    assert det.metadata["acceptance_rate"] > 0.99


def test_tracker_95_pct_passes() -> None:
    t = EvaluatorAcceptanceTracker()
    for _ in range(95):
        t.record("eval-1", accepted=True)
    for _ in range(5):
        t.record("eval-1", accepted=False)
    assert t.check("eval-1") is None


def test_tracker_per_instance_independent() -> None:
    t = EvaluatorAcceptanceTracker()
    for _ in range(100):
        t.record("eval-1", accepted=True)
    for i in range(100):
        t.record("eval-2", accepted=i % 2 == 0)
    assert t.check("eval-1") is not None
    assert t.check("eval-2") is None


def test_tracker_window_evicts_oldest() -> None:
    t = EvaluatorAcceptanceTracker(window=100)
    # First 100 are rejects, then 100 accepts → rate becomes 100%.
    for _ in range(100):
        t.record("e", accepted=False)
    for _ in range(100):
        t.record("e", accepted=True)
    det = t.check("e")
    assert det is not None
    assert det.metadata["acceptance_rate"] == 1.0


def test_tracker_unknown_instance_returns_none() -> None:
    t = EvaluatorAcceptanceTracker()
    assert t.rate("ghost") is None
    assert t.sample_size("ghost") == 0
    assert t.check("ghost") is None


def test_tracker_colluding_instances_filter() -> None:
    t = EvaluatorAcceptanceTracker()
    for _ in range(100):
        t.record("colluder", accepted=True)
    for _ in range(100):
        t.record("clean", accepted=(_ % 4 != 0))
    assert t.colluding_instances() == ["colluder"]


# ── check_cache_bypass (D19) ──────────────────────────────────────────


def test_zero_temperature_passes() -> None:
    assert check_cache_bypass(temperature=0.0, plan_hash_history=["h", "h"]) is None


def test_nonzero_temp_with_repeated_hash_fires() -> None:
    det = check_cache_bypass(temperature=0.7, plan_hash_history=["h", "h"])
    assert det is not None
    assert det.pattern == "D19"
    assert det.action == "alert"


def test_nonzero_temp_with_distinct_hashes_passes() -> None:
    assert check_cache_bypass(temperature=0.7, plan_hash_history=["h1", "h2"]) is None


def test_single_hash_passes() -> None:
    assert check_cache_bypass(temperature=0.7, plan_hash_history=["h"]) is None


def test_role_propagates_through_context() -> None:
    """Smoke: role kwarg doesn't crash the helper (used for future per-role policy)."""
    det = check_cache_bypass(temperature=0.5, plan_hash_history=["h", "h"], role="executor")
    assert det is not None
