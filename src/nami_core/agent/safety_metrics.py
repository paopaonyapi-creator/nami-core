"""Inference-call anomaly + agent-loop burn helpers (SAFETY §7 D5/D10/D11).

Three pure surfaces — neither the inference gateway nor the agent loop
is modified. Callers:

  - After every gateway call, push (cost_usd, latency_ms) into a per-role
    `RollingP95`, then call `check_call_anomaly(...)` for D10/D11 firings.
  - After every plan step, build the per-iter cost list from
    `state.steps` and call `check_burn_pattern(state)` for D5.

`RollingP95` is a fixed-size sliding window (default 200 samples) — solid
enough for outlier detection at the volumes Nami OS T1 actually hits, and
zero external deps. Swap to a real streaming-quantile sketch (e.g. KLL)
when sample volume exceeds 10k/role/hour.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from nami_core.agent.state import AgentState
from nami_core.safety.detectors import d5, d10, d11
from nami_core.safety.types import Detection, DetectorContext


@dataclass
class RollingP95:
    """Sliding-window p95 estimator. Per-role usage is the typical pattern."""

    window: int = 200
    samples: Deque[float] = field(default_factory=deque)

    def push(self, value: float) -> None:
        if value is None:
            return
        self.samples.append(float(value))
        while len(self.samples) > self.window:
            self.samples.popleft()

    def __len__(self) -> int:
        return len(self.samples)

    def value(self) -> float | None:
        n = len(self.samples)
        if n < 20:
            return None  # too few samples — outlier detection would be noisy
        ordered = sorted(self.samples)
        # Index of the 95th percentile in a sorted list of n.
        idx = max(0, min(n - 1, int(round(0.95 * (n - 1)))))
        return ordered[idx]


@dataclass
class InferenceCallStats:
    """Bundles per-role rolling estimators for cost + latency."""

    cost: RollingP95 = field(default_factory=RollingP95)
    latency: RollingP95 = field(default_factory=RollingP95)

    def record(self, cost_usd: float, latency_ms: float) -> None:
        if cost_usd > 0:
            self.cost.push(cost_usd)
        if latency_ms > 0:
            self.latency.push(latency_ms)


def check_call_anomaly(
    *,
    role: str,
    cost_usd: float,
    latency_ms: float,
    stats: InferenceCallStats,
) -> list[Detection]:
    """Run D10 + D11 against one call, with `stats` providing the rolling p95.

    Returns the list of detections (0, 1, or 2 firings). The caller decides
    whether to alert, log, or page — this helper is detection-only.
    """
    p95_cost = stats.cost.value()
    p95_latency = stats.latency.value()
    detections: list[Detection] = []
    ctx = DetectorContext(
        job_id="",
        role=role,
        iteration=0,
        call_cost_usd=max(0.0, float(cost_usd)),
        rolling_p95_cost_usd=p95_cost,
        call_latency_ms=max(0.0, float(latency_ms)),
        rolling_p95_latency_ms=p95_latency,
    )
    for det in (d10(ctx), d11(ctx)):
        if det is not None:
            det.metadata.setdefault("role", role)
            detections.append(det)
    return detections


def check_burn_pattern(state: AgentState, *, budget_total_usd: float) -> Detection | None:
    """Run D5 against an agent loop state.

    `budget_total_usd` is the per-root cost cap (SAFETY §3 default $5);
    the detector reports front-loaded burn relative to the cumulative
    spend so far, not the absolute budget — but the budget is required
    so D5 can short-circuit when nothing has been spent yet.
    """
    if budget_total_usd <= 0:
        return None
    history: list[float] = []
    for step in state.steps:
        if step.kind == "plan" and step.cost_usd:
            history.append(float(step.cost_usd))
    if not history:
        return None
    ctx = DetectorContext(
        job_id=state.job_id,
        role="agent",
        iteration=state.iters,
        iter_cost_history=history,
        iter_budget_total=float(budget_total_usd),
    )
    det = d5(ctx)
    if det is not None:
        det.metadata.setdefault("job_id", state.job_id)
    return det


__all__ = [
    "RollingP95",
    "InferenceCallStats",
    "check_call_anomaly",
    "check_burn_pattern",
]
