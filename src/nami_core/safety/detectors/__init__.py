"""Per-detector modules, one file each per SAFETY §7 S7.1."""

from __future__ import annotations

from nami_core.safety.detectors.d1_planner_hallucination import detect as d1
from nami_core.safety.detectors.d2_executor_loop import detect as d2
from nami_core.safety.detectors.d4_planner_echo import detect as d4
from nami_core.safety.detectors.d6_rag_tool_injection import detect as d6
from nami_core.safety.detectors.d9_schema_drift import detect as d9
from nami_core.safety.detectors.d12_prompt_size_explosion import detect as d12
from nami_core.safety.detectors.d17_role_mixing import detect as d17
from nami_core.safety.detectors.d19_cache_bypass import detect as d19
from nami_core.safety.detectors.d20_self_replication import detect as d20

ALL_DETECTORS = [d1, d2, d4, d6, d9, d12, d17, d19, d20]

__all__ = [
    "d1", "d2", "d4", "d6", "d9", "d12", "d17", "d19", "d20",
    "ALL_DETECTORS",
]
