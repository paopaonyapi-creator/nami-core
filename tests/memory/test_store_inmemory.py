"""Phase 29 — InMemoryStore round-trip + ranking tests."""

from __future__ import annotations

from datetime import datetime, timezone

from nami_core.memory.store import InMemoryStore, _cosine
from nami_core.memory.types import Episode, SemanticChunk


def _ep(job_id: str, role: str = "agent", outcome: str = "succeeded") -> Episode:
    t = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
    return Episode(
        job_id=job_id,
        role=role,
        summary=f"summary for {job_id}",
        outcome=outcome,  # type: ignore[arg-type]
        started_at=t,
        finished_at=t,
    )


def test_episode_round_trip() -> None:
    store = InMemoryStore()
    assert store.write_episode(_ep("j1")) is True
    assert store.write_episode(_ep("j2", role="planner")) is True

    rows = store.list_episodes()
    assert {r.job_id for r in rows} == {"j1", "j2"}


def test_episode_filter_by_role() -> None:
    store = InMemoryStore()
    store.write_episode(_ep("j1", role="agent"))
    store.write_episode(_ep("j2", role="planner"))

    rows = store.list_episodes(role="planner")
    assert [r.job_id for r in rows] == ["j2"]


def test_episodes_naive_datetime_coerced_to_utc() -> None:
    naive = datetime(2026, 5, 16, 12, 0)
    ep = Episode(
        job_id="j",
        role="agent",
        summary="x",
        outcome="succeeded",
        started_at=naive,
        finished_at=naive,
    )
    assert ep.started_at.tzinfo is timezone.utc
    assert ep.finished_at.tzinfo is timezone.utc


def test_chunk_upsert_dedup_per_key() -> None:
    store = InMemoryStore()
    c1 = SemanticChunk(
        namespace="docs",
        source_ref="a.md",
        chunk_index=0,
        content="v1",
        embedding=[1.0, 0.0],
        model_version="m1",
    )
    c2 = SemanticChunk(
        namespace="docs",
        source_ref="a.md",
        chunk_index=0,
        content="v2",
        embedding=[0.0, 1.0],
        model_version="m1",
    )
    assert store.upsert_chunks([c1]) == 1
    assert store.upsert_chunks([c2]) == 1
    assert len(store.chunks) == 1
    assert store.chunks[0].content == "v2"


def test_query_semantic_ranks_by_cosine() -> None:
    store = InMemoryStore()
    chunks = [
        SemanticChunk("ns", "a", 0, "alpha", [1.0, 0.0, 0.0], "m1"),
        SemanticChunk("ns", "b", 0, "beta", [0.0, 1.0, 0.0], "m1"),
        SemanticChunk("ns", "c", 0, "gamma", [0.7, 0.7, 0.0], "m1"),
    ]
    store.upsert_chunks(chunks)

    hits = store.query_semantic("ns", [1.0, 0.0, 0.0], "m1", limit=2)
    assert [h.chunk.source_ref for h in hits] == ["a", "c"]
    assert hits[0].score > hits[1].score


def test_query_filters_namespace_and_model() -> None:
    store = InMemoryStore()
    store.upsert_chunks(
        [
            SemanticChunk("ns1", "a", 0, "x", [1.0, 0.0], "m1"),
            SemanticChunk("ns2", "b", 0, "y", [1.0, 0.0], "m1"),
            SemanticChunk("ns1", "c", 0, "z", [1.0, 0.0], "m2"),
        ]
    )
    hits = store.query_semantic("ns1", [1.0, 0.0], "m1", limit=10)
    assert [h.chunk.source_ref for h in hits] == ["a"]


def test_cosine_orthogonal_is_zero() -> None:
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_zero_vector_safe() -> None:
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_dim_mismatch_returns_zero() -> None:
    assert _cosine([1.0], [1.0, 0.0]) == 0.0
