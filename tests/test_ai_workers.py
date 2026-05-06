"""Tests for AI workers: ai_chat, sentiment, search."""

from __future__ import annotations

import importlib
from unittest.mock import patch, MagicMock

import pytest


def _mod(name: str):
    return importlib.import_module(f"nami_workers.{name}")


# === AI Chat Worker ===

def test_ai_chat_no_messages() -> None:
    m = _mod("ai_chat_worker")
    r = m.ai_chat_worker({"action": "chat", "messages": []})
    assert "error" in r

def test_ai_chat_with_ai() -> None:
    m = _mod("ai_chat_worker")
    with patch("nami_workers.utils.ai_chat_completion", return_value="Hello!"):
        r = m.ai_chat_worker({"action": "chat", "messages": [{"role": "user", "content": "hi"}]})
        assert r["ok"] is True
        assert r["response"] == "Hello!"

def test_ai_complete_no_prompt() -> None:
    m = _mod("ai_chat_worker")
    assert "error" in m.ai_chat_worker({"action": "complete", "prompt": ""})

def test_ai_complete_with_ai() -> None:
    m = _mod("ai_chat_worker")
    with patch("nami_workers.utils.ai_chat_completion", return_value="world"):
        r = m.ai_chat_worker({"action": "complete", "prompt": "hello"})
        assert r["ok"] is True
        assert r["completion"] == "world"

def test_ai_summarize_no_text() -> None:
    m = _mod("ai_chat_worker")
    assert "error" in m.ai_chat_worker({"action": "summarize", "text": ""})

def test_ai_summarize_with_ai() -> None:
    m = _mod("ai_chat_worker")
    with patch("nami_workers.utils.ai_chat_completion", return_value="Short summary"):
        r = m.ai_chat_worker({"action": "summarize", "text": "Long text here..."})
        assert r["ok"] is True
        assert r["summary"] == "Short summary"

def test_ai_translate_no_text() -> None:
    m = _mod("ai_chat_worker")
    assert "error" in m.ai_chat_worker({"action": "translate_text", "text": ""})

def test_ai_translate_with_ai() -> None:
    m = _mod("ai_chat_worker")
    with patch("nami_workers.utils.ai_chat_completion", return_value="Bonjour"):
        r = m.ai_chat_worker({"action": "translate_text", "text": "Hello", "target_lang": "fr"})
        assert r["ok"] is True
        assert r["translation"] == "Bonjour"

def test_ai_chat_unknown_action() -> None:
    m = _mod("ai_chat_worker")
    assert "error" in m.ai_chat_worker({"action": "invalid"})

def test_ai_chat_ai_failure() -> None:
    m = _mod("ai_chat_worker")
    with patch("nami_workers.utils.ai_chat_completion", side_effect=Exception("API down")):
        r = m.ai_chat_worker({"action": "chat", "messages": [{"role": "user", "content": "hi"}]})
        assert "error" in r


# === Sentiment Worker ===

def test_sentiment_no_text() -> None:
    m = _mod("sentiment_worker")
    assert "error" in m.sentiment_worker({"action": "analyze", "text": ""})

def test_sentiment_analyze_positive() -> None:
    m = _mod("sentiment_worker")
    with patch("nami_workers.utils.ai_chat_completion", return_value='{"sentiment":"positive","score":0.9,"keywords":["great","love"]}'):
        r = m.sentiment_worker({"action": "analyze", "text": "I love this!"})
        assert r["ok"] is True
        assert r["sentiment"] == "positive"

def test_sentiment_analyze_non_json() -> None:
    m = _mod("sentiment_worker")
    with patch("nami_workers.utils.ai_chat_completion", return_value="It seems positive"):
        r = m.sentiment_worker({"action": "analyze", "text": "test"})
        assert r["ok"] is True
        assert r["sentiment"] == "unknown"

def test_sentiment_batch_no_texts() -> None:
    m = _mod("sentiment_worker")
    assert "error" in m.sentiment_worker({"action": "batch_analyze", "texts": []})

def test_sentiment_batch() -> None:
    m = _mod("sentiment_worker")
    with patch("nami_workers.utils.ai_chat_completion", return_value='{"sentiment":"positive","score":0.8,"keywords":[]}'):
        r = m.sentiment_worker({"action": "batch_analyze", "texts": ["good", "great"]})
        assert r["ok"] is True
        assert r["total"] == 2

def test_sentiment_unknown_action() -> None:
    m = _mod("sentiment_worker")
    assert "error" in m.sentiment_worker({"action": "invalid"})


# === Search Worker ===

def test_search_web_no_query() -> None:
    m = _mod("search_worker")
    assert "error" in m.search_worker({"action": "web", "query": ""})

def test_search_web_with_api() -> None:
    m = _mod("search_worker")
    mock_data = {"AbstractText": "Test result", "Heading": "Test", "AbstractURL": "http://test", "RelatedTopics": []}
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = __import__("json").dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        r = m.search_worker({"action": "web", "query": "test"})
        assert r["ok"] is True
        assert len(r["results"]) > 0

def test_search_knowledge_no_query() -> None:
    m = _mod("search_worker")
    assert "error" in m.search_worker({"action": "knowledge", "query": ""})

def test_search_knowledge() -> None:
    m = _mod("search_worker")
    import tempfile, os
    am = _mod("analytics_worker")
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    old = am.DB_PATH; am.DB_PATH = f.name
    try:
        am.analytics_worker({"action": "dispatch_log", "worker": "test", "latency_ms": 50, "ok": True})
        r = m.search_worker({"action": "knowledge", "query": "test"})
        assert r["ok"] is True
        assert "stats" in r
    finally:
        am.DB_PATH = old; os.unlink(f.name)

def test_search_unknown_action() -> None:
    m = _mod("search_worker")
    assert "error" in m.search_worker({"action": "invalid"})
