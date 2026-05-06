"""Search worker — web search and knowledge retrieval."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger("nami_workers.search")


def search_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Search worker: web, knowledge."""
    action = payload.get("action", "web")

    if action == "web":
        return _web_search(payload)
    elif action == "knowledge":
        return _knowledge_search(payload)
    else:
        return {"error": f"unknown action: {action}"}


def _web_search(payload: dict[str, Any]) -> dict[str, Any]:
    """Perform a web search using DuckDuckGo Instant Answer API."""
    query = payload.get("query", "")
    limit = payload.get("limit", 5)

    if not query:
        return {"error": "query required"}

    try:
        url = f"https://api.duckduckgo.com/?q={urllib.request.quote(query)}&format=json&no_html=1"
        req = urllib.request.Request(url, headers={"User-Agent": "NamiCore/0.7.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        # Extract abstract
        if data.get("AbstractText"):
            results.append({
                "type": "abstract",
                "title": data.get("Heading", ""),
                "text": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
            })
        # Extract related topics
        for topic in data.get("RelatedTopics", [])[:limit]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "type": "related",
                    "title": topic.get("Text", "")[:80],
                    "text": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })

        return {"ok": True, "query": query, "results": results[:limit], "total": len(results)}
    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return {"error": str(exc)}


def _knowledge_search(payload: dict[str, Any]) -> dict[str, Any]:
    """Search internal knowledge base (dispatch analytics)."""
    query = payload.get("query", "")

    if not query:
        return {"error": "query required"}

    # Search through analytics/dispatch history
    try:
        import importlib
        analytics_mod = importlib.import_module("nami_workers.analytics_worker")
        summary = analytics_mod.analytics_worker({"action": "summary"})
        leaderboard = analytics_mod.analytics_worker({"action": "leaderboard", "limit": 10})
        return {
            "ok": True,
            "query": query,
            "stats": summary,
            "top_workers": leaderboard.get("leaderboard", []),
        }
    except Exception as exc:
        logger.warning("Knowledge search failed: %s", exc)
        return {"error": str(exc)}
