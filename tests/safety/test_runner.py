"""Phase 33 — DetectorRunner tests."""

from __future__ import annotations

import pytest

from nami_core.safety.detectors import ALL_DETECTORS
from nami_core.safety.runner import (
    DetectorRunner,
    get_detection_counts,
    get_fallback_counts,
    reset_detection_counts,
    reset_fallback_counts,
    safety_metrics_prometheus_lines,
    set_metric_emitter,
)
from nami_core.safety.types import Detection, DetectorContext


def _ctx(**kw) -> DetectorContext:
    base = dict(job_id="j1", role="planner", iteration=0)
    base.update(kw)
    return DetectorContext(**base)


@pytest.fixture(autouse=True)
def _isolate_metrics():
    reset_fallback_counts()
    set_metric_emitter(None)
    yield
    reset_fallback_counts()
    set_metric_emitter(None)


def test_runner_aggregates_detections() -> None:
    runner = DetectorRunner(ALL_DETECTORS)
    ctx = _ctx(
        plan={"tool": "ghost"},
        tool_registry=["search"],
        rag_chunks=["<tool_call>x</tool_call>"],
    )
    outcome = runner.run(ctx)
    patterns = {d.pattern for d in outcome.detections}
    assert {"D1", "D6"}.issubset(patterns)


def test_runner_halt_flag_set_on_halt_branch() -> None:
    runner = DetectorRunner(ALL_DETECTORS)
    h = [("call", "x")] * 3
    outcome = runner.run(_ctx(action_payload_history=h))
    assert outcome.halt is True


def test_runner_halt_flag_clear_on_alert_only() -> None:
    runner = DetectorRunner(ALL_DETECTORS)
    outcome = runner.run(_ctx(temperature=0.5, plan_hash_history=["h", "h"]))
    assert outcome.halt is False
    patterns = {d.pattern for d in outcome.detections}
    assert "D19" in patterns


def test_runner_exception_in_detector_does_not_crash() -> None:
    def boom(_ctx: DetectorContext):
        raise RuntimeError("buggy detector")

    def good(_ctx: DetectorContext):
        return Detection(pattern="DX", action="alert", reason="ok")

    outcome = DetectorRunner([boom, good]).run(_ctx())
    assert [d.pattern for d in outcome.detections] == ["DX"]


def test_runner_emits_metric_per_detection() -> None:
    calls: list[tuple[str, str]] = []
    set_metric_emitter(lambda pat, act: calls.append((pat, act)))

    runner = DetectorRunner(ALL_DETECTORS)
    runner.run(_ctx(plan={"tool": "ghost"}, tool_registry=["search"]))
    assert ("D1", "reject") in calls


def test_runner_metric_failure_falls_back_to_internal_counter() -> None:
    def bad_emit(_p, _a):
        raise RuntimeError("prom down")

    set_metric_emitter(bad_emit)
    DetectorRunner(ALL_DETECTORS).run(_ctx(plan={"tool": "ghost"}, tool_registry=["ok"]))
    counts = get_fallback_counts()
    assert counts[("D1", "reject")] == 1


def test_runner_filtered_chunks_surfaced() -> None:
    runner = DetectorRunner(ALL_DETECTORS)
    ctx = _ctx(rag_chunks=["normal", "<tool_call>x</tool_call>"])
    outcome = runner.run(ctx)
    assert outcome.filtered_chunks is not None
    assert "[FILTERED]" in outcome.filtered_chunks[1]


def test_runner_empty_context_returns_no_detections() -> None:
    outcome = DetectorRunner(ALL_DETECTORS).run(_ctx())
    assert outcome.detections == []
    assert outcome.halt is False


def test_runner_outcome_by_action_filter() -> None:
    runner = DetectorRunner(ALL_DETECTORS)
    ctx = _ctx(
        plan={"tool": "ghost"},
        tool_registry=["search"],
        rag_chunks=["<tool_call>x</tool_call>"],
    )
    outcome = runner.run(ctx)
    rejects = outcome.by_action("reject")
    filters = outcome.by_action("filter")
    assert len(rejects) == 1 and rejects[0].pattern == "D1"
    assert len(filters) == 1 and filters[0].pattern == "D6"


def test_safety_metrics_prometheus_lines_empty_emits_stable_schema() -> None:
    lines = safety_metrics_prometheus_lines()
    assert lines[0] == "# TYPE nami_safety_detection_total counter"
    assert any("pattern=\"none\"" in line and "action_taken=\"none\"" in line for line in lines)


def test_safety_metrics_prometheus_lines_records_detection_counts() -> None:
    runner = DetectorRunner(ALL_DETECTORS)
    runner.run(_ctx(plan={"tool": "ghost"}, tool_registry=["search"]))
    runner.run(_ctx(plan={"tool": "ghost"}, tool_registry=["search"]))

    lines = safety_metrics_prometheus_lines()
    assert any(
        'nami_safety_detection_total{pattern="D1",action_taken="reject"} 2' == line
        for line in lines
    )


def test_detection_counts_always_recorded_even_with_external_emitter() -> None:
    """S7.3: in-process count is canonical so /metrics/prometheus always works."""
    pushed: list[tuple[str, str]] = []
    set_metric_emitter(lambda pat, act: pushed.append((pat, act)))

    DetectorRunner(ALL_DETECTORS).run(_ctx(plan={"tool": "ghost"}, tool_registry=["ok"]))

    assert ("D1", "reject") in pushed
    assert get_detection_counts()[("D1", "reject")] == 1


def test_get_fallback_counts_alias_returns_detection_counts() -> None:
    DetectorRunner(ALL_DETECTORS).run(_ctx(plan={"tool": "ghost"}, tool_registry=["ok"]))
    assert get_fallback_counts() == get_detection_counts()


def test_reset_detection_counts_clears_store() -> None:
    DetectorRunner(ALL_DETECTORS).run(_ctx(plan={"tool": "ghost"}, tool_registry=["ok"]))
    assert get_detection_counts()
    reset_detection_counts()
    assert get_detection_counts() == {}
