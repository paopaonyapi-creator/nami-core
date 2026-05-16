"""Phase 33 — safety detectors (SAFETY §7 LOCKED).

Each detector lives in its own module under `detectors/` per S7.1.
DetectorRunner runs them as middleware between agent role transitions
(S7.2) and emits `nami_safety_detection_total{pattern, action_taken}`
per S7.3.
"""

from __future__ import annotations

from nami_core.safety.types import (
    ActionTaken,
    Detection,
    DetectorContext,
    DetectorOutcome,
)
from nami_core.safety.runner import DetectorRunner, Detector

__all__ = [
    "ActionTaken",
    "Detection",
    "DetectorContext",
    "DetectorOutcome",
    "DetectorRunner",
    "Detector",
]
