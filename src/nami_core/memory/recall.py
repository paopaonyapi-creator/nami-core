"""Phase 33 — safe semantic recall with D16 embedding-drift detection.

`safe_recall` is an opt-in wrapper around `MemoryStore.query_semantic` that:

1. Embeds the query through the supplied `Embedder`.
2. Asks the store which `model_version`s are present in the namespace.
3. Runs the optional `DetectorRunner` over a `DetectorContext` populated
   with the query/corpus versions so D16 fires when they diverge.
4. ALWAYS returns the underlying `query_semantic` results unchanged.

D16 emits `force_reroll` (non-terminal). The retrieval flow is intentionally
unaffected — callers can inspect the returned `detections` list to decide
whether to re-embed the corpus, fall back to a legacy version, or ignore.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from nami_core.memory.embedder import Embedder
from nami_core.memory.store import MemoryStore
from nami_core.memory.types import QueryResult
from nami_core.safety.runner import DetectorRunner
from nami_core.safety.types import Detection, DetectorContext

logger = logging.getLogger("nami_core.memory.recall")


@dataclass
class RecallOutcome:
    results: list[QueryResult]
    detections: list[Detection]
    query_version: str
    corpus_versions: list[str]


def safe_recall(
    *,
    embedder: Embedder,
    store: MemoryStore,
    namespace: str,
    query: str,
    limit: int = 5,
    safety_runner: DetectorRunner | None = None,
    job_id: str = "recall",
    role: str = "agent",
) -> RecallOutcome:
    """Embed `query`, run safety detectors, then call `store.query_semantic`.

    Best-effort: any exception when reading corpus versions or running
    detectors degrades to an empty `detections` list — the underlying
    semantic query is the primary contract and must not be blocked.
    """
    embedding = embedder.embed(query)
    corpus_versions = _safe_corpus_versions(store, namespace)
    detections: list[Detection] = []
    if safety_runner is not None:
        ctx = DetectorContext(
            job_id=job_id,
            role=role,
            iteration=0,
            embedding_query_version=embedding.model_version,
            embedding_corpus_versions=list(corpus_versions),
        )
        try:
            outcome = safety_runner.run(ctx)
            detections = list(outcome.detections)
        except Exception as exc:  # noqa: BLE001 — safety must never block recall
            logger.warning("safe_recall detector run failed: %s", exc)
    results = store.query_semantic(
        namespace=namespace,
        embedding=embedding.vector,
        model_version=embedding.model_version,
        limit=limit,
    )
    return RecallOutcome(
        results=list(results),
        detections=detections,
        query_version=embedding.model_version,
        corpus_versions=list(corpus_versions),
    )


def _safe_corpus_versions(store: MemoryStore, namespace: str) -> Sequence[str]:
    fn = getattr(store, "corpus_versions", None)
    if fn is None:
        return []
    try:
        return list(fn(namespace))
    except Exception as exc:  # noqa: BLE001
        logger.warning("corpus_versions lookup failed: %s", exc)
        return []


__all__ = ["RecallOutcome", "safe_recall"]
