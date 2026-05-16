"""Phase 29 — agent memory module (working/episodic/semantic).

RUNTIME §10 LOCKED contract:
  - Working    → Redis `nami:agent:{job_id}:working` (TTL=job duration + 1h).
  - Episodic   → Postgres `agent_episodes` (pgvector-indexed, indefinite).
  - Semantic   → Postgres `embeddings`     (rebuildable from source rows).

This package never owns source-of-truth data: every embedding is derivative
and regenerable. Connect/insert failures degrade gracefully (best-effort
pattern, mirroring AgentTracesDAO and MCPAuditDAO).
"""

from __future__ import annotations

from nami_core.memory.types import (
    Episode,
    EpisodeOutcome,
    Embedding,
    SemanticChunk,
    QueryResult,
)

__all__ = [
    "Episode",
    "EpisodeOutcome",
    "Embedding",
    "SemanticChunk",
    "QueryResult",
]
