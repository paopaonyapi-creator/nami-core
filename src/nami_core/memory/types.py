"""Phase 29 memory types — episodic + semantic schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


EpisodeOutcome = Literal["succeeded", "failed", "cancelled"]


@dataclass
class Episode:
    """A per-task summary written when a job terminates.

    Lives in `agent_episodes`. The `embedding` is derivative — if pgvector
    is unavailable at write time the row is still inserted (embedding NULL)
    and can be back-filled by the lifecycle promoter.
    """

    job_id: str
    role: str
    summary: str
    outcome: EpisodeOutcome
    started_at: datetime
    finished_at: datetime
    trace_id: str | None = None
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    model_version: str = "none"

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            self.started_at = self.started_at.replace(tzinfo=timezone.utc)
        if self.finished_at.tzinfo is None:
            self.finished_at = self.finished_at.replace(tzinfo=timezone.utc)


@dataclass
class SemanticChunk:
    """A semantic-tier chunk: regenerable from `source_ref`."""

    namespace: str
    source_ref: str
    chunk_index: int
    content: str
    embedding: list[float]
    model_version: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Embedding:
    """Raw vector + the model version that produced it (L10.2)."""

    vector: list[float]
    model_version: str


@dataclass
class QueryResult:
    """One semantic search hit. `score` is cosine similarity in [0,1]."""

    chunk: SemanticChunk
    score: float


__all__ = [
    "Episode",
    "EpisodeOutcome",
    "SemanticChunk",
    "Embedding",
    "QueryResult",
]
