"""Sentiment worker — analyze text sentiment using AI."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("nami_workers.sentiment")


def sentiment_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Sentiment worker: analyze, batch_analyze."""
    action = payload.get("action", "analyze")

    if action == "analyze":
        return _analyze(payload)
    elif action == "batch_analyze":
        return _batch_analyze(payload)
    else:
        return {"error": f"unknown action: {action}"}


def _analyze(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze sentiment of a single text."""
    text = payload.get("text", "")

    if not text:
        return {"error": "text required"}

    messages = [
        {"role": "system", "content": "Analyze the sentiment of the following text. Respond with JSON: {\"sentiment\": \"positive\"|\"negative\"|\"neutral\", \"score\": 0.0-1.0, \"keywords\": [list of key phrases]}"},
        {"role": "user", "content": text},
    ]
    try:
        from nami_workers.utils import ai_chat_completion
        import json
        response = ai_chat_completion(model="auto", messages=messages)
        # Try to parse as JSON
        try:
            result = json.loads(response)
            return {"ok": True, **result}
        except json.JSONDecodeError:
            return {"ok": True, "sentiment": "unknown", "raw_response": response}
    except Exception as exc:
        logger.warning("Sentiment analyze failed: %s", exc)
        return {"error": str(exc)}


def _batch_analyze(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze sentiment of multiple texts."""
    texts = payload.get("texts", [])

    if not texts:
        return {"error": "texts list required"}

    results = []
    for text in texts:
        r = _analyze({"text": text})
        results.append(r)

    pos = sum(1 for r in results if r.get("sentiment") == "positive")
    neg = sum(1 for r in results if r.get("sentiment") == "negative")
    neu = sum(1 for r in results if r.get("sentiment") in ("neutral", "unknown"))

    return {
        "ok": True,
        "total": len(results),
        "positive": pos,
        "negative": neg,
        "neutral": neu,
        "results": results,
    }
