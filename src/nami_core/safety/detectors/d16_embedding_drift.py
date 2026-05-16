"""D16 — Embedding-version drift: query embedder differs from corpus.

Fires when the active query embedder's `model_version` is not present in the
target corpus (`embedding_corpus_versions`). This usually means the index was
re-embedded with a new model but live retrieval is still using the previous
version (or vice-versa), which silently degrades recall to zero on most stores
because they filter by `model_version`.

Action: `force_reroll` — non-terminal advisory; caller is expected to either
re-embed the corpus or fall back to a compatible model. This detector never
halts a branch.
"""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    query_version = ctx.embedding_query_version
    corpus_versions = list(ctx.embedding_corpus_versions or [])
    if not query_version or not corpus_versions:
        return None
    if query_version in corpus_versions:
        return None
    return Detection(
        pattern="D16",
        action="force_reroll",
        reason=(
            f"embedding-version drift: query uses {query_version!r} but corpus "
            f"only contains {sorted(set(corpus_versions))!r}"
        ),
        severity="medium",
        metadata={
            "query_version": query_version,
            "corpus_versions": sorted(set(corpus_versions)),
        },
    )
