"""Phase 33 — DetectorRunner: middleware that runs all detectors per S7.2.

Detectors are pure functions: `(ctx) -> Detection | None`. Runner sequences
them, aggregates outcomes, and emits the SAFETY §7 S7.3 metric.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable

from nami_core.safety.types import Detection, DetectorContext, DetectorOutcome

logger = logging.getLogger("nami_core.safety.runner")


Detector = Callable[[DetectorContext], Detection | None]


_METRIC: Callable[[str, str], None] | None = None
_FALLBACK_COUNTS: dict[tuple[str, str], int] = {}


def set_metric_emitter(fn: Callable[[str, str], None] | None) -> None:
    """Install the Prometheus emitter. Tests can swap a stub."""
    global _METRIC
    _METRIC = fn


def _emit(pattern: str, action: str) -> None:
    if _METRIC is not None:
        try:
            _METRIC(pattern, action)
            return
        except Exception as exc:  # noqa: BLE001 — observability never blocks safety
            logger.warning("safety metric emit failed: %s", exc)
    _FALLBACK_COUNTS[(pattern, action)] = _FALLBACK_COUNTS.get((pattern, action), 0) + 1


def get_fallback_counts() -> dict[tuple[str, str], int]:
    """Snapshot of in-process counts used when no real Prometheus emitter installed."""
    return dict(_FALLBACK_COUNTS)


def reset_fallback_counts() -> None:
    _FALLBACK_COUNTS.clear()


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
    "get_fallback_counts",
    "reset_fallback_counts",
]
