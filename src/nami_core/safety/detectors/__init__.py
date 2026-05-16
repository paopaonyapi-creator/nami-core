"""Per-detector modules, one file each per SAFETY §7 S7.1."""

from __future__ import annotations

from nami_core.safety.detectors.d1_planner_hallucination import detect as d1
from nami_core.safety.detectors.d2_executor_loop import detect as d2
from nami_core.safety.detectors.d3_evaluator_collusion import detect as d3
from nami_core.safety.detectors.d4_planner_echo import detect as d4
from nami_core.safety.detectors.d5_front_loaded_burn import detect as d5
from nami_core.safety.detectors.d6_rag_tool_injection import detect as d6
from nami_core.safety.detectors.d7_recursive_deadlock import detect as d7
from nami_core.safety.detectors.d8_orphaned_child import detect as d8
from nami_core.safety.detectors.d9_schema_drift import detect as d9
from nami_core.safety.detectors.d10_cost_outlier import detect as d10
from nami_core.safety.detectors.d11_latency_outlier import detect as d11
from nami_core.safety.detectors.d12_prompt_size_explosion import detect as d12
from nami_core.safety.detectors.d13_heartbeat_missing import detect as d13
from nami_core.safety.detectors.d14_dlq_growth import detect as d14
from nami_core.safety.detectors.d15_mcp_unhealthy import detect as d15
from nami_core.safety.detectors.d16_embedding_drift import detect as d16
from nami_core.safety.detectors.d17_role_mixing import detect as d17
from nami_core.safety.detectors.d18_forbidden_file_access import detect as d18
from nami_core.safety.detectors.d19_cache_bypass import detect as d19
from nami_core.safety.detectors.d20_self_replication import detect as d20

ALL_DETECTORS = [
    d1, d2, d3, d4, d5, d6, d7, d8, d9, d10,
    d11, d12, d13, d14, d15, d16, d17, d18, d19, d20,
]

__all__ = [
    "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9", "d10",
    "d11", "d12", "d13", "d14", "d15", "d16", "d17", "d18", "d19", "d20",
    "ALL_DETECTORS",
]
