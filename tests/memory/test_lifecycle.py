"""Phase 29 — lifecycle: chunker + episode promotion + ingestion tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

import pytest

from nami_core.memory.embedder import Embedder
from nami_core.memory.lifecycle import (
    chunk_text,
    ingest_documents,
    promote_episode,
)
from nami_core.memory.store import InMemoryStore


def _provider(texts: Sequence[str], _model: str) -> list[list[float]]:
    return [[float(len(t)), 0.0, 1.0] for t in texts]


# ── chunker ────────────────────────────────────────────────────────────


def test_chunk_text_short_input_single_chunk() -> None:
    assert chunk_text("hello world", chunk_size=10) == ["hello world"]


def test_chunk_text_overlap_window() -> None:
    text = " ".join(str(i) for i in range(10))
    chunks = chunk_text(text, chunk_size=4, overlap=1)
    assert chunks[0] == "0 1 2 3"
    assert chunks[1].startswith("3 ")  # overlap of 1 word


def test_chunk_text_empty_returns_empty_list() -> None:
    assert chunk_text("") == []


def test_chunk_text_invalid_overlap_raises() -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", chunk_size=2, overlap=2)


def test_chunk_text_invalid_chunk_size_raises() -> None:
    with pytest.raises(ValueError):
        chunk_text("a", chunk_size=0)


# ── promote_episode ────────────────────────────────────────────────────


def test_promote_episode_writes_with_embedding() -> None:
    store = InMemoryStore()
    embedder = Embedder(model_version="mv1", provider=_provider)
    t = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)

    ep = promote_episode(
        store=store,
        job_id="j1",
        role="agent",
        summary="finished backtest",
        outcome="succeeded",
        started_at=t,
        finished_at=t,
        cost_usd=0.12,
        embedder=embedder,
    )

    assert ep.embedding == [17.0, 0.0, 1.0]
    assert ep.model_version == "mv1"
    assert len(store.episodes) == 1


def test_promote_episode_without_embedder_keeps_null_vector() -> None:
    store = InMemoryStore()
    t = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
    ep = promote_episode(
        store=store,
        job_id="j1",
        role="agent",
        summary="x",
        outcome="failed",
        started_at=t,
        finished_at=t,
    )
    assert ep.embedding is None
    assert ep.model_version == "none"


def test_promote_episode_embedder_failure_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    store = InMemoryStore()

    def boom(_texts: Sequence[str], _model: str) -> list[list[float]]:
        raise RuntimeError("embed offline")

    embedder = Embedder(model_version="m", provider=boom)
    t = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)

    ep = promote_episode(
        store=store,
        job_id="j1",
        role="agent",
        summary="failed mid-step",
        outcome="failed",
        started_at=t,
        finished_at=t,
        embedder=embedder,
    )

    assert ep.embedding is None
    assert len(store.episodes) == 1


def test_promote_episode_store_failure_does_not_raise() -> None:
    class BoomStore(InMemoryStore):
        def write_episode(self, episode):  # type: ignore[override]
            raise RuntimeError("db down")

    t = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
    ep = promote_episode(
        store=BoomStore(),
        job_id="j1",
        role="agent",
        summary="x",
        outcome="succeeded",
        started_at=t,
        finished_at=t,
    )
    assert ep.job_id == "j1"


# ── ingest_documents ───────────────────────────────────────────────────


def test_ingest_documents_chunks_and_upserts() -> None:
    store = InMemoryStore()
    embedder = Embedder(model_version="mv1", provider=_provider)

    text = " ".join(str(i) for i in range(20))
    written = ingest_documents(
        store=store,
        namespace="docs",
        documents=[("a.md", text)],
        embedder=embedder,
        chunk_size=5,
        overlap=1,
    )
    assert written > 1
    assert len(store.chunks) == written
    refs = {c.source_ref for c in store.chunks}
    assert refs == {"a.md"}
    assert all(c.namespace == "docs" for c in store.chunks)
    assert all(c.model_version == "mv1" for c in store.chunks)


def test_ingest_documents_skips_empty_text() -> None:
    store = InMemoryStore()
    embedder = Embedder(model_version="mv1", provider=_provider)
    written = ingest_documents(
        store=store,
        namespace="docs",
        documents=[("empty.md", "")],
        embedder=embedder,
    )
    assert written == 0


def test_ingest_documents_embed_failure_skips_doc() -> None:
    store = InMemoryStore()

    def boom(_texts: Sequence[str], _model: str) -> list[list[float]]:
        raise RuntimeError("nope")

    embedder = Embedder(model_version="mv1", provider=boom)
    written = ingest_documents(
        store=store,
        namespace="docs",
        documents=[("a.md", "some text here")],
        embedder=embedder,
    )
    assert written == 0
    assert store.chunks == []


def test_ingest_documents_re_upsert_replaces_content() -> None:
    store = InMemoryStore()
    embedder = Embedder(model_version="mv1", provider=_provider)

    ingest_documents(
        store=store,
        namespace="docs",
        documents=[("a.md", "alpha beta gamma")],
        embedder=embedder,
        chunk_size=10,
    )
    first_count = len(store.chunks)

    ingest_documents(
        store=store,
        namespace="docs",
        documents=[("a.md", "alpha beta gamma")],
        embedder=embedder,
        chunk_size=10,
    )
    assert len(store.chunks) == first_count
