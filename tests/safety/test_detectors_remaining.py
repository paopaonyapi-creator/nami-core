"""Phase 33c — D3/D10/D11/D13/D14/D15/D18 detector tests (closes all 20)."""

from __future__ import annotations

from nami_core.safety.detectors import d3, d10, d11, d13, d14, d15, d18
from nami_core.safety.types import DetectorContext


def _ctx(**kw) -> DetectorContext:
    base = dict(job_id="j1", role="planner", iteration=0)
    base.update(kw)
    return DetectorContext(**base)


# ── D3 ─────────────────────────────────────────────────────────────────


def test_d3_high_acceptance_alerts() -> None:
    det = d3(_ctx(evaluator_acceptance_rate=0.995, evaluator_window_size=100))
    assert det is not None
    assert det.action == "alert"


def test_d3_below_threshold_passes() -> None:
    assert d3(_ctx(evaluator_acceptance_rate=0.95, evaluator_window_size=200)) is None


def test_d3_small_window_skipped() -> None:
    assert d3(_ctx(evaluator_acceptance_rate=1.0, evaluator_window_size=50)) is None


def test_d3_no_rate_skipped() -> None:
    assert d3(_ctx()) is None


# ── D10 ────────────────────────────────────────────────────────────────


def test_d10_cost_outlier_alerts() -> None:
    det = d10(_ctx(call_cost_usd=0.10, rolling_p95_cost_usd=0.01))
    assert det is not None
    assert det.action == "alert"
    assert det.metadata["ratio"] >= 5.0


def test_d10_within_band_passes() -> None:
    assert d10(_ctx(call_cost_usd=0.02, rolling_p95_cost_usd=0.01)) is None


def test_d10_no_baseline_skipped() -> None:
    assert d10(_ctx(call_cost_usd=1.0)) is None


def test_d10_zero_call_skipped() -> None:
    assert d10(_ctx(call_cost_usd=0.0, rolling_p95_cost_usd=0.01)) is None


# ── D11 ────────────────────────────────────────────────────────────────


def test_d11_latency_outlier_alerts() -> None:
    det = d11(_ctx(call_latency_ms=10000, rolling_p95_latency_ms=1000))
    assert det is not None
    assert det.action == "alert"


def test_d11_within_band_passes() -> None:
    assert d11(_ctx(call_latency_ms=1500, rolling_p95_latency_ms=1000)) is None


def test_d11_no_baseline_skipped() -> None:
    assert d11(_ctx(call_latency_ms=10000)) is None


# ── D13 ────────────────────────────────────────────────────────────────


def test_d13_missing_heartbeat_halts() -> None:
    det = d13(_ctx(job_running_seconds=120, heartbeat_present=False))
    assert det is not None
    assert det.action == "halt_branch"


def test_d13_short_run_skipped() -> None:
    assert d13(_ctx(job_running_seconds=30, heartbeat_present=False)) is None


def test_d13_heartbeat_present_passes() -> None:
    assert d13(_ctx(job_running_seconds=120, heartbeat_present=True)) is None


# ── D14 ────────────────────────────────────────────────────────────────


def test_d14_dlq_over_threshold_halts_action() -> None:
    det = d14(_ctx(dlq_length=75))
    assert det is not None
    assert det.action == "halt_action"


def test_d14_dlq_at_threshold_passes() -> None:
    assert d14(_ctx(dlq_length=50)) is None


def test_d14_empty_dlq_passes() -> None:
    assert d14(_ctx(dlq_length=0)) is None


# ── D15 ────────────────────────────────────────────────────────────────


def test_d15_three_timeouts_alerts() -> None:
    det = d15(_ctx(mcp_consecutive_timeouts=3, mcp_server_name="filesystem"))
    assert det is not None
    assert det.action == "alert"
    assert det.metadata["server"] == "filesystem"


def test_d15_two_timeouts_passes() -> None:
    assert d15(_ctx(mcp_consecutive_timeouts=2, mcp_server_name="git")) is None


def test_d15_no_server_name_skipped() -> None:
    assert d15(_ctx(mcp_consecutive_timeouts=5)) is None


# ── D18 ────────────────────────────────────────────────────────────────


def test_d18_path_inside_allowed_root_passes() -> None:
    assert (
        d18(_ctx(file_access_path="/opt/nami/work/x.txt", file_access_allowed_roots=["/opt/nami/work"]))
        is None
    )


def test_d18_path_outside_allowed_root_halts() -> None:
    det = d18(_ctx(file_access_path="/etc/passwd", file_access_allowed_roots=["/opt/nami/work"]))
    assert det is not None
    assert det.action == "halt_branch"


def test_d18_traversal_marker_halts() -> None:
    det = d18(_ctx(file_access_path="/opt/nami/work/../../etc/passwd", file_access_allowed_roots=["/opt/nami/work"]))
    assert det is not None
    assert det.metadata["reason"] == "traversal"


def test_d18_null_byte_halts() -> None:
    det = d18(_ctx(file_access_path="/opt/nami/work/x\x00.txt", file_access_allowed_roots=["/opt/nami/work"]))
    assert det is not None
    assert det.metadata["reason"] == "traversal"


def test_d18_no_roots_configured_halts() -> None:
    det = d18(_ctx(file_access_path="/opt/nami/work/x.txt"))
    assert det is not None
    assert det.metadata["reason"] == "no_roots"


def test_d18_no_path_skipped() -> None:
    assert d18(_ctx()) is None


def test_d18_exact_root_match_passes() -> None:
    assert (
        d18(_ctx(file_access_path="/opt/nami/work", file_access_allowed_roots=["/opt/nami/work"]))
        is None
    )
