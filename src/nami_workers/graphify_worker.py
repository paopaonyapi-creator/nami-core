"""Graphify Worker — Knowledge Graph API for code intelligence.

Migrated from /opt/graphify-http + /opt/graphify-mcp.
Provides knowledge graph queries, code analysis, impact analysis,
and graph data loading from VPS graphify-out directories.

Actions:
  - query: Execute a knowledge graph query
  - analyze: Analyze code structure
  - impact: Impact analysis for changes
  - load_graphs: Load available graph data from VPS
  - list_graphs: List available graph names
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── VPS Graph paths (from /opt/graphify-mcp/mcp_server.py) ──
GRAPH_ROOTS = [
    "/root/laopatana-stat-lab/graphify-out",
    "/opt/hanoi-bot/graphify-out",
    "/opt/gold-signal-os/graphify-out",
    "/opt/MiroShark/graphify-out",
    "/opt/telegram-premium/graphify-out",
]


def _load_graph_data(name: str) -> dict[str, Any] | None:
    """Load graph.json from VFS graphify-out directory."""
    for root in GRAPH_ROOTS:
        gpath = os.path.join(root, "graph.json")
        if os.path.exists(gpath) and name in root.lower():
            try:
                with open(gpath) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
    return None


def list_graphs(payload: dict[str, Any]) -> dict[str, Any]:
    """List available graph names from VPS."""
    graphs = []
    for root in GRAPH_ROOTS:
        gpath = os.path.join(root, "graph.json")
        if os.path.exists(gpath):
            name = Path(root).parent.name
            graphs.append({"name": name, "path": gpath, "size": os.path.getsize(gpath)})
    return {"graphs": graphs}


def load_graphs(payload: dict[str, Any]) -> dict[str, Any]:
    """Load all available graph data from VPS graphify-out directories."""
    name = payload.get("name", "")
    if name:
        data = _load_graph_data(name)
        if data:
            return {"name": name, "nodes": len(data.get("nodes", [])), "edges": len(data.get("links", [])), "loaded": True}
        return {"name": name, "loaded": False, "error": "graph not found"}

    # Load all
    results = []
    for root in GRAPH_ROOTS:
        gpath = os.path.join(root, "graph.json")
        if os.path.exists(gpath):
            try:
                with open(gpath) as f:
                    data = json.load(f)
                gname = Path(root).parent.name
                results.append({"name": gname, "nodes": len(data.get("nodes", [])), "edges": len(data.get("links", []))})
            except (json.JSONDecodeError, OSError):
                continue
    return {"graphs": results}


def query(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a knowledge graph query.

    Payload keys:
      - cypher: Cypher query string
      - repo: target repository

    Returns dict with: results, query
    """
    cypher = payload.get("cypher", "")
    repo = payload.get("repo", "")

    # Try loading graph data for the repo
    if repo:
        data = _load_graph_data(repo)
        if data:
            return {"results": data.get("nodes", [])[:50], "query": cypher, "repo": repo, "source": "graphify-out"}

    logger.info("Graph query: repo=%s", repo)

    return {
        "results": [],
        "query": cypher,
        "repo": repo,
    }


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze code structure.

    Payload keys:
      - repo: target repository
      - type: analysis type (smells, trends, coverage)

    Returns dict with: findings, repo, type
    """
    repo = payload.get("repo", "")
    analysis_type = payload.get("type", "smells")

    # TODO: Replace with actual code analysis logic
    return {
        "findings": [],
        "repo": repo,
        "type": analysis_type,
    }


def impact(payload: dict[str, Any]) -> dict[str, Any]:
    """Impact analysis for proposed changes.

    Payload keys:
      - repo: target repository
      - file: changed file path
      - change_type: type of change

    Returns dict with: impacted_files, risk_level
    """
    repo = payload.get("repo", "")
    file = payload.get("file", "")

    # TODO: Replace with actual impact analysis logic
    return {
        "impacted_files": [],
        "risk_level": "Low",
        "repo": repo,
        "changed_file": file,
    }


ACTIONS: dict[str, callable] = {
    "query": query,
    "analyze": analyze,
    "impact": impact,
    "load_graphs": load_graphs,
    "list_graphs": list_graphs,
}


def graphify_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "query")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
