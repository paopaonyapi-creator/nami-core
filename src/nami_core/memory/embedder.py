"""Phase 29 — embedder with cache + provider routing.

The embedder pulls vectors via `inference_gateway.embed()` (single-dispatch
contract, RUNTIME §6 L1.2) and caches by (model_version, sha256(text)) so
repeated calls don't re-bill. Failures degrade to a deterministic stub
vector when `NAMI_EMBED_FALLBACK=stub` is set; otherwise raise.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections import OrderedDict
from typing import Callable, Sequence

from nami_core.memory.types import Embedding

logger = logging.getLogger("nami_core.memory.embedder")

DEFAULT_DIM = 1536
DEFAULT_MODEL = "text-embedding-3-small"


def _stub_vector(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """Deterministic vector derived from sha256 — only for tests / fallback."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = (digest * ((dim // len(digest)) + 1))[:dim]
    return [(b - 128) / 128.0 for b in raw]


class Embedder:
    """LRU-cached embedder. Provider-injectable for tests."""

    def __init__(
        self,
        model_version: str | None = None,
        dim: int = DEFAULT_DIM,
        provider: Callable[[Sequence[str], str], list[list[float]]] | None = None,
        cache_size: int = 1024,
    ) -> None:
        self.model_version = model_version or os.environ.get(
            "NAMI_EMBED_MODEL", DEFAULT_MODEL
        )
        self.dim = dim
        self.provider = provider or _default_provider
        self.cache_size = cache_size
        self._cache: "OrderedDict[str, list[float]]" = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0

    def _cache_key(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.model_version}:{h}"

    def _cache_get(self, key: str) -> list[float] | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, vec: list[float]) -> None:
        self._cache[key] = vec
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def embed(self, text: str) -> Embedding:
        return Embedding(vector=self.embed_many([text])[0], model_version=self.model_version)

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        unique: dict[str, list[int]] = {}
        for i, text in enumerate(texts):
            key = self._cache_key(text)
            cached = self._cache_get(key)
            if cached is not None:
                self.cache_hits += 1
                results[i] = cached
            elif text in unique:
                self.cache_hits += 1
                unique[text].append(i)
            else:
                self.cache_misses += 1
                unique[text] = [i]

        if unique:
            miss_texts = list(unique.keys())
            try:
                vectors = self.provider(miss_texts, self.model_version)
            except Exception as exc:  # noqa: BLE001
                if os.environ.get("NAMI_EMBED_FALLBACK") == "stub":
                    logger.warning("embed provider failed (%s); using stub fallback", exc)
                    vectors = [_stub_vector(t, self.dim) for t in miss_texts]
                else:
                    raise
            if len(vectors) != len(miss_texts):
                raise RuntimeError(
                    f"embedder provider returned {len(vectors)} vectors for {len(miss_texts)} inputs"
                )
            for text, vec in zip(miss_texts, vectors):
                self._cache_put(self._cache_key(text), vec)
                for idx in unique[text]:
                    results[idx] = vec

        return [r if r is not None else [] for r in results]


def _default_provider(texts: Sequence[str], model_version: str) -> list[list[float]]:
    """Default provider: route through inference_gateway.embed if available;
    otherwise fall back to deterministic stub (dev/test mode)."""
    try:
        from nami_core import inference_gateway  # noqa: F401

        if hasattr(inference_gateway, "embed"):
            return list(inference_gateway.embed(list(texts), model=model_version))
    except Exception as exc:  # noqa: BLE001
        logger.debug("inference_gateway.embed unavailable: %s", exc)

    return [_stub_vector(t) for t in texts]


__all__ = ["Embedder", "DEFAULT_DIM", "DEFAULT_MODEL", "_stub_vector"]
