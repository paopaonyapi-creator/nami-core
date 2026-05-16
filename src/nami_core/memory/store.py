"""Phase 29 — memory store interface + InMemoryStore + PgVectorStore.

Two implementations:
  - InMemoryStore: deterministic, used for tests and dev runs without Postgres.
  - PgVectorStore : best-effort Postgres-backed store. Connect failures are
    logged and degrade to no-op (returns False / []), per the same pattern
    as AgentTracesDAO and MCPAuditDAO.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Iterable, Protocol

from nami_core.db import get_connection
from nami_core.memory.types import Episode, QueryResult, SemanticChunk

logger = logging.getLogger("nami_core.memory.store")


class MemoryStore(Protocol):
    def write_episode(self, episode: Episode) -> bool: ...
    def list_episodes(self, role: str | None = None, limit: int = 20) -> list[Episode]: ...
    def upsert_chunks(self, chunks: Iterable[SemanticChunk]) -> int: ...
    def query_semantic(
        self,
        namespace: str,
        embedding: list[float],
        model_version: str,
        limit: int = 5,
    ) -> list[QueryResult]: ...
    def corpus_versions(self, namespace: str) -> list[str]: ...



def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryStore:
    """Deterministic in-process store. Holds everything in lists."""

    def __init__(self) -> None:
        self.episodes: list[Episode] = []
        self.chunks: list[SemanticChunk] = []

    def write_episode(self, episode: Episode) -> bool:
        self.episodes.append(episode)
        return True

    def list_episodes(self, role: str | None = None, limit: int = 20) -> list[Episode]:
        rows = [e for e in self.episodes if role is None or e.role == role]
        rows.sort(key=lambda e: e.finished_at, reverse=True)
        return rows[:limit]

    def upsert_chunks(self, chunks: Iterable[SemanticChunk]) -> int:
        count = 0
        for chunk in chunks:
            existing = next(
                (
                    i
                    for i, c in enumerate(self.chunks)
                    if c.namespace == chunk.namespace
                    and c.source_ref == chunk.source_ref
                    and c.chunk_index == chunk.chunk_index
                    and c.model_version == chunk.model_version
                ),
                None,
            )
            if existing is None:
                self.chunks.append(chunk)
            else:
                self.chunks[existing] = chunk
            count += 1
        return count

    def query_semantic(
        self,
        namespace: str,
        embedding: list[float],
        model_version: str,
        limit: int = 5,
    ) -> list[QueryResult]:
        scored: list[QueryResult] = []
        for chunk in self.chunks:
            if chunk.namespace != namespace or chunk.model_version != model_version:
                continue
            score = _cosine(embedding, chunk.embedding)
            scored.append(QueryResult(chunk=chunk, score=score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    def corpus_versions(self, namespace: str) -> list[str]:
        seen: set[str] = set()
        for chunk in self.chunks:
            if chunk.namespace == namespace:
                seen.add(chunk.model_version)
        return sorted(seen)


def _vector_literal(vec: list[float] | None) -> str | None:
    if vec is None:
        return None
    return "[" + ",".join(repr(float(v)) for v in vec) + "]"


class PgVectorStore:
    """Postgres + pgvector backed store. Best-effort writes."""

    def __init__(self, dbname: str | None = None, dsn: str | None = None) -> None:
        self.dbname = dbname or os.environ.get("NAMI_JOBS_DB", "glodbyproza")
        self.dsn = dsn or os.environ.get("NAMI_JOBS_DSN")

    def _connect(self):
        if self.dsn:
            import psycopg

            return psycopg.connect(self.dsn)
        return get_connection(self.dbname)

    def write_episode(self, episode: Episode) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO agent_episodes (
                            job_id, trace_id, role, summary, outcome,
                            cost_usd, started_at, finished_at, metadata,
                            embedding, model_version
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, %s)
                        """,
                        (
                            episode.job_id,
                            episode.trace_id,
                            episode.role,
                            episode.summary,
                            episode.outcome,
                            episode.cost_usd,
                            episode.started_at,
                            episode.finished_at,
                            json.dumps(episode.metadata or {}),
                            _vector_literal(episode.embedding),
                            episode.model_version,
                        ),
                    )
                conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("agent_episodes insert failed: %s", exc)
            return False

    def list_episodes(self, role: str | None = None, limit: int = 20) -> list[Episode]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    if role is None:
                        cur.execute(
                            """
                            SELECT job_id, trace_id, role, summary, outcome, cost_usd,
                                   started_at, finished_at, metadata, model_version
                            FROM agent_episodes
                            ORDER BY finished_at DESC LIMIT %s
                            """,
                            (limit,),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT job_id, trace_id, role, summary, outcome, cost_usd,
                                   started_at, finished_at, metadata, model_version
                            FROM agent_episodes
                            WHERE role = %s
                            ORDER BY finished_at DESC LIMIT %s
                            """,
                            (role, limit),
                        )
                    rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent_episodes select failed: %s", exc)
            return []
        out: list[Episode] = []
        for row in rows:
            md = row[8]
            if isinstance(md, str):
                md = json.loads(md)
            out.append(
                Episode(
                    job_id=row[0],
                    trace_id=row[1],
                    role=row[2],
                    summary=row[3],
                    outcome=row[4],
                    cost_usd=float(row[5] or 0),
                    started_at=row[6],
                    finished_at=row[7],
                    metadata=md or {},
                    model_version=row[9],
                )
            )
        return out

    def upsert_chunks(self, chunks: Iterable[SemanticChunk]) -> int:
        rows: list[tuple[Any, ...]] = []
        for chunk in chunks:
            rows.append(
                (
                    chunk.namespace,
                    chunk.source_ref,
                    chunk.chunk_index,
                    chunk.content,
                    _vector_literal(chunk.embedding),
                    chunk.model_version,
                    json.dumps(chunk.metadata or {}),
                )
            )
        if not rows:
            return 0
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    for r in rows:
                        cur.execute(
                            """
                            INSERT INTO embeddings (
                                namespace, source_ref, chunk_index, content,
                                embedding, model_version, metadata
                            )
                            VALUES (%s, %s, %s, %s, %s::vector, %s, %s::jsonb)
                            ON CONFLICT (namespace, source_ref, chunk_index, model_version)
                            DO UPDATE SET content = EXCLUDED.content,
                                          embedding = EXCLUDED.embedding,
                                          metadata = EXCLUDED.metadata
                            """,
                            r,
                        )
                conn.commit()
            return len(rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning("embeddings upsert failed: %s", exc)
            return 0

    def query_semantic(
        self,
        namespace: str,
        embedding: list[float],
        model_version: str,
        limit: int = 5,
    ) -> list[QueryResult]:
        vec = _vector_literal(embedding)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT namespace, source_ref, chunk_index, content,
                               model_version, metadata,
                               1 - (embedding <=> %s::vector) AS score
                        FROM embeddings
                        WHERE namespace = %s AND model_version = %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (vec, namespace, model_version, vec, limit),
                    )
                    rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.warning("embeddings query failed: %s", exc)
            return []
        out: list[QueryResult] = []
        for row in rows:
            md = row[5]
            if isinstance(md, str):
                md = json.loads(md)
            out.append(
                QueryResult(
                    chunk=SemanticChunk(
                        namespace=row[0],
                        source_ref=row[1],
                        chunk_index=row[2],
                        content=row[3],
                        embedding=[],
                        model_version=row[4],
                        metadata=md or {},
                    ),
                    score=float(row[6] or 0.0),
                )
            )
        return out

    def corpus_versions(self, namespace: str) -> list[str]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT DISTINCT model_version FROM embeddings WHERE namespace = %s",
                        (namespace,),
                    )
                    rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("embeddings corpus_versions lookup failed: %s", exc)
            return []
        return sorted({str(row[0]) for row in rows if row and row[0]})


__all__ = ["MemoryStore", "InMemoryStore", "PgVectorStore"]
