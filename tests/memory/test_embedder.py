"""Phase 29 — Embedder cache + provider routing + fallback tests."""

from __future__ import annotations

from typing import Sequence

import pytest

from nami_core.memory.embedder import DEFAULT_DIM, Embedder, _stub_vector


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.last_inputs: list[str] = []

    def __call__(self, texts: Sequence[str], model_version: str) -> list[list[float]]:
        self.calls += 1
        self.last_inputs = list(texts)
        return [[float(len(t)), 0.0, 1.0] for t in texts]


def test_embed_single_text_returns_vector() -> None:
    provider = CountingProvider()
    emb = Embedder(model_version="m1", provider=provider).embed("hello")
    assert emb.model_version == "m1"
    assert emb.vector == [5.0, 0.0, 1.0]
    assert provider.calls == 1


def test_cache_hit_avoids_provider_call() -> None:
    provider = CountingProvider()
    embedder = Embedder(model_version="m1", provider=provider)

    embedder.embed("hello")
    embedder.embed("hello")
    embedder.embed("hello")

    assert provider.calls == 1
    assert embedder.cache_hits == 2
    assert embedder.cache_misses == 1


def test_cache_miss_per_unique_text() -> None:
    provider = CountingProvider()
    embedder = Embedder(model_version="m1", provider=provider)

    embedder.embed_many(["a", "b", "a", "c"])
    assert embedder.cache_misses == 3
    assert embedder.cache_hits == 1
    assert provider.last_inputs == ["a", "b", "c"]


def test_cache_keyed_by_model_version() -> None:
    provider = CountingProvider()
    e1 = Embedder(model_version="m1", provider=provider)
    e2 = Embedder(model_version="m2", provider=provider)
    e1.embed("hello")
    e2.embed("hello")
    assert provider.calls == 2


def test_cache_lru_evicts_oldest() -> None:
    provider = CountingProvider()
    embedder = Embedder(model_version="m1", provider=provider, cache_size=2)
    embedder.embed("a")
    embedder.embed("b")
    embedder.embed("c")  # evicts "a"

    embedder.embed("a")  # miss again — was evicted
    assert provider.calls == 4


def test_provider_size_mismatch_raises() -> None:
    def bad(texts: Sequence[str], _model: str) -> list[list[float]]:
        return [[1.0]]

    embedder = Embedder(model_version="m1", provider=bad)
    with pytest.raises(RuntimeError, match="returned 1 vectors for 2 inputs"):
        embedder.embed_many(["x", "y"])


def test_provider_failure_propagates_by_default() -> None:
    def boom(_texts: Sequence[str], _model: str) -> list[list[float]]:
        raise RuntimeError("provider down")

    embedder = Embedder(model_version="m1", provider=boom)
    with pytest.raises(RuntimeError, match="provider down"):
        embedder.embed("x")


def test_provider_failure_falls_back_to_stub_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NAMI_EMBED_FALLBACK", "stub")

    def boom(_texts: Sequence[str], _model: str) -> list[list[float]]:
        raise RuntimeError("nope")

    embedder = Embedder(model_version="m1", provider=boom)
    vec = embedder.embed("hello").vector
    assert len(vec) == DEFAULT_DIM
    assert vec == _stub_vector("hello")


def test_stub_vector_deterministic() -> None:
    assert _stub_vector("x") == _stub_vector("x")
    assert _stub_vector("x") != _stub_vector("y")
    assert len(_stub_vector("hello")) == DEFAULT_DIM


def test_embed_many_preserves_input_order() -> None:
    provider = CountingProvider()
    embedder = Embedder(model_version="m1", provider=provider)
    embedder.embed("a")  # warm cache
    out = embedder.embed_many(["b", "a", "c"])
    assert out[1] == [1.0, 0.0, 1.0]  # cached "a"
    assert out[0] == [1.0, 0.0, 1.0]
    assert out[2] == [1.0, 0.0, 1.0]
