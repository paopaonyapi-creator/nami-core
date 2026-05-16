"""Phase 33 — DetectorRunner: middleware that runs all detectors per S7.2.

Detectors are pure functions: `(ctx) -> Detection | None`. Runner sequences
them, aggregates outcomes, and emits the SAFETY §7 S7.3 metric
`nami_safety_detection_total{pattern,action_taken}`.

Counts are always recorded in an in-process store and exposed via
`safety_metrics_prometheus_lines()` for `/metrics/prometheus`. An optional
external emitter may be installed via `set_metric_emitter()` for callers
that also want to push to e.g. statsd; emitter failures never block safety.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable

from nami_core.safety.types import Detection, DetectorContext, DetectorOutcome

logger = logging.getLogger("nami_core.safety.runner")


Detector = Callable[[DetectorContext], Detection | None]


_METRIC: Callable[[str, str], None] | None = None
_DETECTION_COUNTS: dict[tuple[str, str], int] = {}


def set_metric_emitter(fn: Callable[[str, str], None] | None) -> None:
    """Install an optional external emitter (e.g. statsd push). Tests can swap a stub."""
    global _METRIC
    _METRIC = fn


def _emit(pattern: str, action: str) -> None:
    # S7.3: always record in-process for /metrics/prometheus exposure.
    _DETECTION_COUNTS[(pattern, action)] = _DETECTION_COUNTS.get((pattern, action), 0) + 1
    if _METRIC is not None:
        try:
            _METRIC(pattern, action)
        except Exception as exc:  # noqa: BLE001 — observability never blocks safety
            logger.warning("safety metric emit failed: %s", exc)


def get_detection_counts() -> dict[tuple[str, str], int]:
    """Snapshot of in-process detection counts."""
    return dict(_DETECTION_COUNTS)


def reset_detection_counts() -> None:
    _DETECTION_COUNTS.clear()


# Backward-compat aliases (kept for existing imports / tests).
def get_fallback_counts() -> dict[tuple[str, str], int]:
    """Deprecated alias for get_detection_counts()."""
    return get_detection_counts()


def reset_fallback_counts() -> None:
    """Deprecated alias for reset_detection_counts()."""
    reset_detection_counts()


def safety_metrics_prometheus_lines() -> list[str]:
    """Render `nami_safety_detection_total` per SAFETY §7.3.

    Always emits the TYPE header so scrapers see a stable schema even when
    no detections have fired yet.
    """
    lines = ["# TYPE nami_safety_detection_total counter"]
    if not _DETECTION_COUNTS:
        lines.append('nami_safety_detection_total{pattern="none",action_taken="none"} 0')
        return lines
    for (pattern, action), count in sorted(_DETECTION_COUNTS.items()):
        lines.append(
            f'nami_safety_detection_total{{pattern="{pattern}",action_taken="{action}"}} {count}'
        )
    return lines


_HALT_ACTIONS = {"halt_branch", "halt_action", "halt_role"}


class DetectorRunner:
    def __init__(self, detectors: Iterable[Detector]) -> None:
        self.detectors: list[Detector] = list(detectors)

    def run(self, ctx: DetectorContext) -> DetectorOutcome:
        detections: list[Detection] = []
        for detector in self.detectors:
            try:
                result = detector(ctx)
            except Exception as exc:  # noqa: BLE001 — never let a buggy detector
                logger.warning("detector %s raised: %s", detector.__name__, exc)
                continue
            if result is None:
                continue
            detections.append(result)
            _emit(result.pattern, result.action)

        outcome = DetectorOutcome(
            detections=detections,
            halt=any(d.action in _HALT_ACTIONS for d in detections),
        )

        filtered = [d for d in detections if d.action == "filter" and "chunks" in d.metadata]
        if filtered:
            outcome.filtered_chunks = filtered[-1].metadata["chunks"]
        return outcome


__all__ = [
    "Detector",
    "DetectorRunner",
    "set_metric_emitter",
    "get_detection_counts",
    "reset_detection_counts",
    "get_fallback_counts",
    "reset_fallback_counts",
    "safety_metrics_prometheus_lines",
]
