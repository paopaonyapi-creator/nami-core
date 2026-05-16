"""Evaluator + planner-cache safety helpers (SAFETY §7 D3 + D19).

D3 — Evaluator collusion: per-evaluator-instance rolling acceptance tracker.
Caller (the critic/evaluator role's worker) records each decision via
`record(instance_id, accepted=True|False)`. `check(instance_id)` runs D3
against the rolling rate.

D19 — Cache-bypass via temperature: pure-function check. Caller passes
the current call's temperature + the recent plan-hash history; helper
returns the D19 detection if the shape matches (non-zero temperature
with a repeated plan hash).

Both are stateless on disk — D3's tracker is in-process per-evaluator;
caller is expected to seed it from `agent_traces` on cold start.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Iterable

from nami_core.safety.detectors import d3, d19
from nami_core.safety.types import Detection, DetectorContext


@dataclass
class EvaluatorAcceptanceTracker:
    """Per-evaluator-instance rolling acceptance window.

    SAFETY §7 D3 fires when acceptance rate >99% over ≥100 samples. The
    tracker keeps a fixed-size deque per instance so memory stays bounded.
    """

    window: int = 100
    decisions: dict[str, Deque[bool]] = field(default_factory=dict)

    def record(self, instance_id: str, *, accepted: bool) -> None:
        dq = self.decisions.setdefault(instance_id, deque())
        dq.append(bool(accepted))
        while len(dq) > self.window:
            dq.popleft()

    def rate(self, instance_id: str) -> float | None:
        dq = self.decisions.get(instance_id)
        if not dq:
            return None
        return sum(dq) / len(dq)

    def sample_size(self, instance_id: str) -> int:
        return len(self.decisions.get(instance_id, ()))

    def check(self, instance_id: str) -> Detection | None:
        rate = self.rate(instance_id)
        size = self.sample_size(instance_id)
        if rate is None:
            return None
        ctx = DetectorContext(
            job_id="",
            role="critic",
            iteration=0,
            evaluator_acceptance_rate=rate,
            evaluator_window_size=size,
        )
        det = d3(ctx)
        if det is not None:
            det.metadata.setdefault("instance_id", instance_id)
        return det

    def colluding_instances(self, candidates: Iterable[str] | None = None) -> list[str]:
        names = list(candidates) if candidates is not None else list(self.decisions.keys())
        return [n for n in names if self.check(n) is not None]


def check_cache_bypass(
    *,
    temperature: float,
    plan_hash_history: Iterable[str],
    role: str = "planner",
) -> Detection | None:
    """Run D19 against one planner call.

    Caller passes the temperature of the latest planning call + the
    accumulating plan-hash history (most recent last). Returns a D19
    detection if the call has non-zero temperature AND the latest plan
    hash matches the immediately prior one — the cache-bypass shape.
    """
    hist = list(plan_hash_history)
    ctx = DetectorContext(
        job_id="",
        role=role,
        iteration=0,
        temperature=float(temperature),
        plan_hash_history=hist,
    )
    return d19(ctx)


__all__ = [
    "EvaluatorAcceptanceTracker",
    "check_cache_bypass",
]
