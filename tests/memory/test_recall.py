"""Phase 33 — safe_recall + D16 embedding-drift integration tests."""

from __future__ import annotations

from nami_core.memory.embedder import Embedder, _stub_vector
from nami_core.memory.recall import safe_recall
from nami_core.memory.store import InMemoryStore
from nami_core.memory.types import SemanticChunk
from nami_core.safety.detectors import ALL_DETECTORS
from nami_core.safety.runner import DetectorRunner


def _embedder(version: str) -> Embedder:
    return Embedder(
        model_version=version,
        provider=lambda texts, _v: [_stub_vector(t) for t in texts],
    )


def _seed_chunks(store: InMemoryStore, namespace: str, version: str) -> None:
    store.upsert_chunks(
        [
            SemanticChunk(
                namespace=namespace,
                source_ref="doc.md",
                chunk_index=0,
                content="hello world",
                embedding=_stub_vector("hello world"),
                model_version=version,
            )
        ]
    )


def test_safe_recall_emits_d16_when_query_version_not_in_corpus() -> None:
    store = InMemoryStore()
    _seed_chunks(store, "docs", version="legacy-v1")

    outcome = safe_recall(
        embedder=_embedder("new-v2"),
        store=store,
        namespace="docs",
        query="anything",
        safety_runner=DetectorRunner(ALL_DETECTORS),
    )

    patterns = {d.pattern for d in outcome.detections}
    assert "D16" in patterns
    drift = next(d for d in outcome.detections if d.pattern == "D16")
    assert drift.action == "force_reroll"
    assert drift.metadata["query_version"] == "new-v2"
    assert "legacy-v1" in drift.metadata["corpus_versions"]


def test_safe_recall_no_d16_when_versions_match() -> None:
    store = InMemoryStore()
    _seed_chunks(store, "docs", version="m1")

    outcome = safe_recall(
        embedder=_embedder("m1"),
        store=store,
        namespace="docs",
        query="anything",
        safety_runner=DetectorRunner(ALL_DETECTORS),
    )

    assert all(d.pattern != "D16" for d in outcome.detections)


def test_safe_recall_no_d16_for_empty_corpus() -> None:
    store = InMemoryStore()

    outcome = safe_recall(
        embedder=_embedder("m1"),
        store=store,
        namespace="empty",
        query="anything",
        safety_runner=DetectorRunner(ALL_DETECTORS),
    )

    assert outcome.detections == []
    assert outcome.results == []
    assert outcome.corpus_versions == []


def test_safe_recall_returns_results_unchanged_even_when_drift_detected() -> None:
    """Drift is advisory: results from query_semantic must be returned as-is."""
    store = InMemoryStore()
    _seed_chunks(store, "docs", version="legacy-v1")

    outcome = safe_recall(
        embedder=_embedder("new-v2"),
        store=store,
        namespace="docs",
        query="anything",
        safety_runner=DetectorRunner(ALL_DETECTORS),
    )

    # InMemoryStore filters by model_version, so results are empty under drift,
    # but the drift detection itself is what we surface.
    assert outcome.results == []
    assert outcome.query_version == "new-v2"
    assert any(d.pattern == "D16" for d in outcome.detections)


def test_safe_recall_without_safety_runner_is_silent() -> None:
    store = InMemoryStore()
    _seed_chunks(store, "docs", version="legacy-v1")

    outcome = safe_recall(
        embedder=_embedder("new-v2"),
        store=store,
        namespace="docs",
        query="anything",
    )

    assert outcome.detections == []
    assert outcome.corpus_versions == ["legacy-v1"]
