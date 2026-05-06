"""Gateway Worker — Unified REST API entry point.

Migrated from /opt/nami-api-gateway.
Routes HTTP requests to appropriate workers, handles auth, rate limiting.

Actions:
  - route: Route request to appropriate worker
  - health: Health check endpoint
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def route(payload: dict[str, Any]) -> dict[str, Any]:
    """Route an API request to the appropriate worker.

    Payload keys:
      - path: API path (e.g. "/api/signal/generate")
      - method: HTTP method
      - body: request body
      - api_key: client API key

    Returns dict with: routed, worker, path
    """
    path = payload.get("path", "/")
    method = payload.get("method", "GET")

    # Route mapping
    routes = {
        "/api/signal": "signal",
        "/api/proxy": "proxy",
        "/api/lottery": "lottery",
        "/api/trading": "trading",
        "/api/bot": "bot",
        "/api/status": "status",
        "/api/gold": "gold",
        "/api/miroshark": "miroshark",
        "/api/graphify": "graphify",
    }

    worker_name = "default"
    for prefix, name in routes.items():
        if path.startswith(prefix):
            worker_name = name
            break

    logger.info("Route: %s %s → %s", method, path, worker_name)

    return {
        "routed": True,
        "worker": worker_name,
        "path": path,
        "method": method,
    }


def health(payload: dict[str, Any]) -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "nami-gateway",
        "version": "0.0.1",
    }


def agent_route(payload: dict[str, Any]) -> dict[str, Any]:
    """Route task to appropriate AI agent based on category.

    Migrated from /opt/agent-wrappers/nami-router.py.

    Payload keys:
      - category: task category (architecture, coding, quick_fix, research, docs, etc.)
      - description: task description

    Returns dict with: agent, model, category, description
    """
    category = payload.get("category", "general")
    description = payload.get("description", "")

    CATEGORY_MAP = {
        "architecture": {"agent": "claude", "model": "claude-opus-4-7", "icon": "🧠"},
        "system_design": {"agent": "claude", "model": "claude-opus-4-7", "icon": "🧠"},
        "debug_complex": {"agent": "claude", "model": "claude-sonnet-4-6", "icon": "⚡"},
        "refactor": {"agent": "claude", "model": "claude-sonnet-4-6", "icon": "⚡"},
        "feature": {"agent": "claude", "model": "claude-sonnet-4-6", "icon": "⚡"},
        "coding": {"agent": "claude", "model": "claude-sonnet-4-6", "icon": "⚡"},
        "quick_fix": {"agent": "claude", "model": "claude-haiku-4-5", "icon": "💨"},
        "simple_script": {"agent": "claude", "model": "claude-haiku-4-5", "icon": "💨"},
        "reasoning": {"agent": "opencode", "model": "nemotron-3-nano-reasoning", "icon": "🧮"},
        "math": {"agent": "opencode", "model": "nemotron-3-nano-reasoning", "icon": "🧮"},
        "research": {"agent": "opencode", "model": "gemma-4-31b-it", "icon": "📚"},
        "general": {"agent": "opencode", "model": "nemotron-3-super-120b", "icon": "🌐"},
        "docs": {"agent": "thclaws", "model": "-", "icon": "📄"},
        "pdf": {"agent": "thclaws", "model": "-", "icon": "📕"},
    }

    mapping = CATEGORY_MAP.get(category, CATEGORY_MAP["general"])

    logger.info("Agent route: %s → %s/%s", category, mapping["agent"], mapping["model"])

    return {
        "agent": mapping["agent"],
        "model": mapping["model"],
        "icon": mapping["icon"],
        "category": category,
        "description": description,
    }


ACTIONS: dict[str, callable] = {
    "route": route,
    "health": health,
    "agent_route": agent_route,
}


def gateway_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "route")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
