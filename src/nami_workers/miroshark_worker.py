"""MiroShark Worker — AI prediction engine integration.

Wraps the MiroShark Oracle API (port 8003) as a nami-core worker,
providing unified access to MiroShark predictions and graph queries.

Actions:
  - predict: Get AI prediction from MiroShark Oracle
  - graph_query: Query MiroShark knowledge graph
  - status: Check MiroShark Oracle service status
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

# ── MiroShark Oracle API (from /opt/miroshark-oracle) ──
ORACLE_API_URL = os.environ.get("ORACLE_API_URL", "http://127.0.0.1:8003")
MIROSHARK_API_URL = os.environ.get("MIROSHARK_API_URL", "http://127.0.0.1:5001")


def _oracle_get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    """GET request to MiroShark Oracle API."""
    url = f"{ORACLE_API_URL}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
        logger.warning("Oracle API error: %s", e)
        return {"error": str(e)}


def _oracle_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST request to MiroShark Oracle API."""
    url = f"{ORACLE_API_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
        logger.warning("Oracle API error: %s", e)
        return {"error": str(e)}


def predict(payload: dict[str, Any]) -> dict[str, Any]:
    """Get AI prediction from MiroShark Oracle.

    Payload keys:
      - question: the question to ask
      - model: optional model override

    Returns dict with: answer, model, provider
    """
    question = payload.get("question", "")
    model = payload.get("model", "")

    if not question:
        return {"error": "question required"}

    result = _oracle_post("/predict", {"question": question, "model": model})
    if "error" in result:
        return result
    return {
        "answer": result.get("answer", result.get("prediction", "")),
        "model": result.get("model", "miroshark"),
        "provider": "miroshark-oracle",
        "raw": result,
    }


def graph_query(payload: dict[str, Any]) -> dict[str, Any]:
    """Query MiroShark knowledge graph (Neo4j).

    Payload keys:
      - query: Cypher query string
      - params: optional query parameters

    Returns dict with: results, query
    """
    query = payload.get("query", "")
    params = payload.get("params", {})

    if not query:
        return {"error": "query required"}

    result = _oracle_post("/graph", {"query": query, "params": params})
    if "error" in result:
        return result
    return {
        "results": result.get("results", []),
        "query": query,
    }


def status(payload: dict[str, Any]) -> dict[str, Any]:
    """Check MiroShark Oracle service status."""
    result = _oracle_get("/health")
    if "error" in result:
        return {"status": "down", "error": result["error"]}
    return {"status": "ok", "service": "miroshark-oracle", "raw": result}


ACTIONS: dict[str, callable] = {
    "predict": predict,
    "graph_query": graph_query,
    "status": status,
}


def miroshark_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "status")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
