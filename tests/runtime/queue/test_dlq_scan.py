"""Tests for the D14 DLQ scan helper."""

from __future__ import annotations

from nami_core.runtime.queue.dlq_scan import scan_dlq


def test_below_threshold_no_detection() -> None:
    r = scan_dlq(dlq_length=10)
    assert r.detection is None
    assert r.top_action is None
    assert r.dlq_length == 10


def test_at_threshold_no_detection() -> None:
    r = scan_dlq(dlq_length=50)
    assert r.detection is None


def test_above_threshold_fires() -> None:
    r = scan_dlq(dlq_length=75)
    assert r.detection is not None
    assert r.detection.pattern == "D14"
    assert r.detection.action == "halt_action"


def test_top_action_surfaced_in_metadata() -> None:
    r = scan_dlq(
        dlq_length=120,
        action_failure_counts={"agent.run": 80, "lottery.backtest_v6": 30, "other": 10},
    )
    assert r.detection is not None
    assert r.top_action == "agent.run"
    assert r.top_action_count == 80
    assert r.detection.metadata["top_action"] == "agent.run"
    assert r.detection.metadata["top_action_count"] == 80


def test_top_action_tiebreak_alphabetical() -> None:
    r = scan_dlq(
        dlq_length=80,
        action_failure_counts={"b.action": 10, "a.action": 10},
    )
    # max() with key=(count, name) picks lexicographically later name on tie.
    assert r.top_action == "b.action"


def test_top_action_computed_even_without_detection() -> None:
    r = scan_dlq(
        dlq_length=5,
        action_failure_counts={"x": 3, "y": 2},
    )
    assert r.detection is None
    assert r.top_action == "x"
    assert r.top_action_count == 3


def test_empty_counts_with_detection_leaves_top_action_none() -> None:
    r = scan_dlq(dlq_length=100, action_failure_counts={})
    assert r.detection is not None
    assert r.top_action is None
    assert r.top_action_count == 0


def test_negative_length_clamped_to_zero() -> None:
    r = scan_dlq(dlq_length=-5)
    assert r.dlq_length == -5  # raw input preserved
    assert r.detection is None  # but detector sees clamped value
