"""Phase 29 — memory lifecycle: working → episodic → semantic.

Working tier lives in Redis (TTL = job duration + 1h). On job termination
the worker calls `promote_episode()` which:

  1. Reads the working scratchpad (best-effort; missing → empty).
  2. Summarises into an `Episode`.
  3. Embeds the summary (if embedder configured).
  4. Writes via the configured `MemoryStore`.

Semantic-tier ingestion (`ingest_documents`) chunks long text, embeds each
chunk, and upserts into the `embeddings` table.

Both flows are best-effort: a failure logs a warning but never raises into
the agent loop. Memory is observability, not source of truth.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Sequence

from nami_core.memory.embedder import Embedder
from nami_core.memory.store import MemoryStore
from nami_core.memory.types import Episode, EpisodeOutcome, SemanticChunk

logger = logging.getLogger("nami_core.memory.lifecycle")


def chunk_text(text: str, chunk_size: int = 800, overlap: int | None = None) -> list[str]:
    """Naive overlapping-window chunker. Word-aware, no model dependency."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap is None:
        overlap = min(100, max(0, chunk_size - 1))
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = chunk_size - overlap
    i = 0
    while i < len(words):
        window = words[i : i + chunk_size]
        chunks.append(" ".join(window))
        if i + chunk_size >= len(words):
            break
        i += step
    return chunks


def promote_episode(
    *,
    store: MemoryStore,
    job_id: str,
    role: str,
    summary: str,
    outcome: EpisodeOutcome,
    started_at: datetime,
    finished_at: datetime,
    trace_id: str | None = None,
    cost_usd: float = 0.0,
    metadata: dict | None = None,
    embedder: Embedder | None = None,
) -> Episode:
    """Build an Episode, embed its summary, and persist via the store."""
    embedding: list[float] | None = None
    model_version = "none"
    if embedder is not None and summary:
        try:
            emb = embedder.embed(summary)
            embedding = emb.vector
            model_version = emb.model_version
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("episode embed failed: %s", exc)

    episode = Episode(
        job_id=job_id,
        trace_id=trace_id,
        role=role,
        summary=summary,
        outcome=outcome,
        cost_usd=cost_usd,
        started_at=started_at,
        finished_at=finished_at,
        metadata=metadata or {},
        embedding=embedding,
        model_version=model_version,
    )
    try:
        store.write_episode(episode)
    except Exception as exc:  # noqa: BLE001
        logger.warning("episode persist failed: %s", exc)
    return episode


def ingest_documents(
    *,
    store: MemoryStore,
    namespace: str,
    documents: Iterable[tuple[str, str]],
    embedder: Embedder,
    chunk_size: int = 800,
    overlap: int | None = None,
    metadata: dict | None = None,
) -> int:
    """Chunk + embed + upsert. `documents` is an iterable of (source_ref, text)."""
    pending: list[SemanticChunk] = []
    for source_ref, text in documents:
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            continue
        try:
            vectors = embedder.embed_many(chunks)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest embed failed for %s: %s", source_ref, exc)
            continue
        for idx, (content, vec) in enumerate(zip(chunks, vectors)):
            pending.append(
                SemanticChunk(
                    namespace=namespace,
                    source_ref=source_ref,
                    chunk_index=idx,
                    content=content,
                    embedding=vec,
                    model_version=embedder.model_version,
                    metadata=metadata or {},
                )
            )
    if not pending:
        return 0
    try:
        return store.upsert_chunks(pending)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingest upsert failed: %s", exc)
        return 0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["chunk_text", "promote_episode", "ingest_documents", "now_utc"]
