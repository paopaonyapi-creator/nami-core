"""Phase 33b — D5/D7/D8 detector tests."""

from __future__ import annotations

from nami_core.safety.detectors import d5, d7, d8
from nami_core.safety.types import DetectorContext


def _ctx(**kw) -> DetectorContext:
    base = dict(job_id="j1", role="planner", iteration=0)
    base.update(kw)
    return DetectorContext(**base)


# ── D5 ─────────────────────────────────────────────────────────────────


def test_d5_front_loaded_burn_alerts() -> None:
    hist = [0.40, 0.04, 0.03, 0.02, 0.01]  # 80% in first 1/5
    det = d5(_ctx(iter_cost_history=hist, iter_budget_total=1.0))
    assert det is not None
    assert det.action == "alert"
    assert det.metadata["early_share"] >= 0.80


def test_d5_even_spend_passes() -> None:
    hist = [0.10] * 5
    assert d5(_ctx(iter_cost_history=hist, iter_budget_total=1.0)) is None


def test_d5_short_history_skipped() -> None:
    assert d5(_ctx(iter_cost_history=[1.0, 0.0], iter_budget_total=1.0)) is None


def test_d5_zero_budget_skipped() -> None:
    assert d5(_ctx(iter_cost_history=[0.1] * 10, iter_budget_total=0.0)) is None


def test_d5_zero_total_cost_skipped() -> None:
    assert d5(_ctx(iter_cost_history=[0.0] * 10, iter_budget_total=1.0)) is None


# ── D7 ─────────────────────────────────────────────────────────────────


def test_d7_cycle_rejected() -> None:
    det = d7(_ctx(job_id="j2", parent_chain=["root", "j1", "j2", "j3"]))
    assert det is not None
    assert det.action == "reject"
    assert det.metadata["cycle_depth"] == 2


def test_d7_no_cycle_passes() -> None:
    assert d7(_ctx(job_id="j-new", parent_chain=["root", "j1"])) is None


def test_d7_empty_chain_skipped() -> None:
    assert d7(_ctx(job_id="j1")) is None


# ── D8 ─────────────────────────────────────────────────────────────────


def test_d8_failed_parent_halts() -> None:
    det = d8(_ctx(parent_status="failed"))
    assert det is not None
    assert det.action == "halt_branch"


def test_d8_cancelled_parent_halts() -> None:
    det = d8(_ctx(parent_status="cancelled"))
    assert det is not None
    assert det.action == "halt_branch"


def test_d8_running_parent_passes() -> None:
    assert d8(_ctx(parent_status="running")) is None


def test_d8_succeeded_parent_passes() -> None:
    assert d8(_ctx(parent_status="succeeded")) is None


def test_d8_no_parent_status_skipped() -> None:
    assert d8(_ctx()) is None
