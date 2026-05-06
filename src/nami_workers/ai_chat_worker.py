"""AI Chat worker — conversational AI via proxy/external LLM APIs."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("nami_workers.ai_chat")


def ai_chat_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """AI chat worker: chat, complete, summarize, translate_text."""
    action = payload.get("action", "chat")

    if action == "chat":
        return _chat(payload)
    elif action == "complete":
        return _complete(payload)
    elif action == "summarize":
        return _summarize(payload)
    elif action == "translate_text":
        return _translate(payload)
    else:
        return {"error": f"unknown action: {action}"}


def _chat(payload: dict[str, Any]) -> dict[str, Any]:
    """Multi-turn chat conversation."""
    messages = payload.get("messages", [])
    model = payload.get("model", "auto")

    if not messages:
        return {"error": "messages required (list of {role, content})"}

    try:
        from nami_workers.utils import ai_chat_completion
        response = ai_chat_completion(model=model, messages=messages)
        return {"ok": True, "response": response, "model": model}
    except Exception as exc:
        logger.warning("AI chat failed: %s", exc)
        return {"error": str(exc)}


def _complete(payload: dict[str, Any]) -> dict[str, Any]:
    """Single-turn text completion."""
    prompt = payload.get("prompt", "")
    model = payload.get("model", "auto")

    if not prompt:
        return {"error": "prompt required"}

    messages = [{"role": "user", "content": prompt}]
    try:
        from nami_workers.utils import ai_chat_completion
        response = ai_chat_completion(model=model, messages=messages)
        return {"ok": True, "completion": response, "model": model}
    except Exception as exc:
        logger.warning("AI complete failed: %s", exc)
        return {"error": str(exc)}


def _summarize(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize text content."""
    text = payload.get("text", "")
    max_length = payload.get("max_length", 200)

    if not text:
        return {"error": "text required"}

    messages = [
        {"role": "system", "content": f"Summarize the following text in under {max_length} words. Be concise and capture key points."},
        {"role": "user", "content": text},
    ]
    try:
        from nami_workers.utils import ai_chat_completion
        summary = ai_chat_completion(model="auto", messages=messages)
        return {"ok": True, "summary": summary, "original_length": len(text)}
    except Exception as exc:
        logger.warning("AI summarize failed: %s", exc)
        return {"error": str(exc)}


def _translate(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate text to target language."""
    text = payload.get("text", "")
    target_lang = payload.get("target_lang", "en")
    source_lang = payload.get("source_lang", "auto")

    if not text:
        return {"error": "text required"}

    messages = [
        {"role": "system", "content": f"Translate the following text to {target_lang}. Only output the translation, nothing else."},
        {"role": "user", "content": text},
    ]
    try:
        from nami_workers.utils import ai_chat_completion
        translation = ai_chat_completion(model="auto", messages=messages)
        return {"ok": True, "translation": translation, "target_lang": target_lang, "source_lang": source_lang}
    except Exception as exc:
        logger.warning("AI translate failed: %s", exc)
        return {"error": str(exc)}
