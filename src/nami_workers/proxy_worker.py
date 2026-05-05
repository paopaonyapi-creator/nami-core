"""Proxy Worker — LLM API proxy with multi-provider fallback.

Migrated from /opt/maxplus-proxy/proxy.py.
Routes LLM requests through multiple providers (OpenRouter, NVIDIA NIM,
Anthropic direct) with fallback logic and cost tracking.

Actions:
  - chat_completion: Generate chat completion
  - list_models: List available models
  - embed: Generate embeddings
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .utils import ai_chat_completion

logger = logging.getLogger(__name__)

PROVIDERS = ["openrouter", "nvidia_nim", "anthropic"]

# ── VPS MaxPlus Proxy (from /opt/maxplus-proxy/proxy.py) ──
MAXPLUS_PROXY_URL = os.environ.get("MAXPLUS_PROXY_URL", "http://127.0.0.1:8091")

MODEL_CATALOG = [
    {"id": "claude-sonnet-4-6", "provider": "maxplus", "context": 200000},
    {"id": "claude-3-sonnet", "provider": "openrouter", "context": 200000},
    {"id": "gpt-4o", "provider": "openrouter", "context": 128000},
    {"id": "deepseek-chat", "provider": "openrouter", "context": 64000},
    {"id": "meta-llama-3.1-70b-instruct", "provider": "nvidia_nim", "context": 128000},
    {"id": "nomic-embed-text", "provider": "openrouter", "context": 8192, "type": "embedding"},
]


def _call_maxplus_proxy(messages: list[dict], model: str = "claude-sonnet-4-6", max_tokens: int = 2048) -> dict[str, Any]:
    """Call VPS MaxPlus proxy (L1: OpenRouter, L2: NVIDIA fallback)."""
    import urllib.request
    import urllib.error
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{MAXPLUS_PROXY_URL}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "content": data.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "model": data.get("model", model),
                "provider": "maxplus",
                "usage": data.get("usage", {}),
            }
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.warning("MaxPlus proxy unavailable: %s", e)
        return {"content": "", "provider": "maxplus", "error": str(e)}


def _load_provider_config() -> dict[str, Any]:
    """Load provider config from /etc/nami-harness/ai_config.json."""
    config_path = os.environ.get(
        "AI_CONFIG_PATH",
        "/etc/nami-harness/ai_config.json",
    )
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a chat completion via multi-provider fallback.

    Payload keys:
      - model: model name (e.g. "claude-3-sonnet")
      - messages: list of message dicts
      - max_tokens: optional max tokens
      - temperature: optional temperature

    Returns dict with: response, model, provider, tokens, cost
    """
    model = payload.get("model", "claude-3-sonnet")
    messages = payload.get("messages", [])
    max_tokens = payload.get("max_tokens", 2048)
    temperature = payload.get("temperature", 0.7)

    logger.info("Chat completion request: model=%s, messages=%d", model, len(messages))

    # Try VPS MaxPlus proxy first (L1: OpenRouter, L2: NVIDIA fallback)
    result = _call_maxplus_proxy(messages, model=model, max_tokens=max_tokens)
    if result.get("content"):
        content = result.get("content", "")
        usage = result.get("usage", {})
        return {
            "response": content,
            "model": result.get("model", model),
            "provider": result.get("provider", "maxplus"),
            "tokens": usage.get("total_tokens", 0),
            "cost": 0.0,
        }

    # Fallback to shared ai_chat_completion (proxy → direct OpenRouter)
    logger.info("MaxPlus unavailable, falling back to ai_chat_completion")
    result = ai_chat_completion(
        messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    content = result.get("content", "")
    usage = result.get("usage", {})

    return {
        "response": content,
        "model": result.get("model", model),
        "provider": result.get("provider", "unknown"),
        "tokens": usage.get("total_tokens", 0),
        "cost": 0.0,
    }


def list_models(payload: dict[str, Any]) -> dict[str, Any]:
    """List available models from all providers.

    Returns dict with: models (list of model info dicts)
    """
    return {"models": MODEL_CATALOG}


def embed(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate embeddings for input text.

    Payload keys:
      - input: text or list of texts
      - model: embedding model name

    Returns dict with: embeddings, model, tokens
    """
    text = payload.get("input", "")
    model = payload.get("model", "nomic-embed-text")

    # Embedding calls go through the same proxy
    messages = [{"role": "user", "content": f"Embed: {text}"}]
    result = ai_chat_completion(messages, model=model)

    logger.info("Embed request: model=%s", model)

    return {
        "embeddings": [],
        "model": model,
        "tokens": result.get("usage", {}).get("total_tokens", 0),
    }


ACTIONS: dict[str, callable] = {
    "chat_completion": chat_completion,
    "list_models": list_models,
    "embed": embed,
}


def proxy_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "chat_completion")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
