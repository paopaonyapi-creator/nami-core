"""AI Image worker — text-to-image generation and image description."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("nami_workers.image_worker")

AI_CONFIG_PATH = os.environ.get("NAMI_AI_CONFIG", "/etc/nami-harness/ai_config.json")


def _load_config() -> dict:
    try:
        with open(AI_CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _get_api_key() -> str:
    cfg = _load_config()
    return cfg.get("openrouter_key", "") or cfg.get("openai_key", "") or os.environ.get("OPENAI_API_KEY", "")


def _generate_image(prompt: str, size: str = "1024x1024", n: int = 1) -> dict[str, Any]:
    """Generate image from text prompt using OpenRouter/OpenAI DALL-E."""
    api_key = _get_api_key()
    if not api_key:
        return {"ok": False, "error": "no API key configured"}

    try:
        import urllib.request
        import urllib.error

        url = "https://openrouter.ai/api/v1/images/generations"
        payload = json.dumps({
            "model": "openai/dall-e-3",
            "prompt": prompt,
            "size": size,
            "n": n,
        }).encode()

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())

        images = []
        for img in data.get("data", []):
            if "url" in img:
                images.append({"url": img["url"]})
            elif "b64_json" in img:
                images.append({"b64_json": img["b64_json"][:100] + "...", "format": "base64"})

        return {"ok": True, "images": images, "count": len(images)}

    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        logger.warning("Image gen HTTP error %d: %s", e.code, body)
        return {"ok": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as exc:
        logger.warning("Image gen failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _describe_image(image_url: str) -> dict[str, Any]:
    """Describe an image using vision model via chat completion."""
    try:
        from nami_workers.utils import ai_chat_completion
        result = ai_chat_completion(
            messages=[
                {"role": "system", "content": "You are an image description assistant. Describe the image in detail."},
                {"role": "user", "content": f"Describe this image in detail. Image URL: {image_url}"},
            ],
            model="openai/gpt-4o-mini",
        )
        return {"ok": True, "description": result}
    except Exception as exc:
        logger.warning("Image describe failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _list_models() -> dict[str, Any]:
    """List available image generation models."""
    return {
        "ok": True,
        "models": [
            {"id": "openai/dall-e-3", "type": "generation", "sizes": ["1024x1024", "1024x1792", "1792x1024"]},
            {"id": "openai/gpt-4o-mini", "type": "vision", "description": "Image description"},
        ],
    }


def image_worker(task: dict[str, Any]) -> dict[str, Any]:
    """AI Image worker — generate and describe images.

    Actions:
        generate  — text-to-image (requires: prompt, optional: size, n)
        describe  — image-to-text (requires: image_url)
        models    — list available image models
    """
    action = task.get("action", "")

    if action == "generate":
        prompt = task.get("prompt", "")
        if not prompt:
            return {"ok": False, "error": "prompt is required"}
        return _generate_image(
            prompt=prompt,
            size=task.get("size", "1024x1024"),
            n=task.get("n", 1),
        )

    elif action == "describe":
        image_url = task.get("image_url", "")
        if not image_url:
            return {"ok": False, "error": "image_url is required"}
        return _describe_image(image_url)

    elif action == "models":
        return _list_models()

    else:
        return {"ok": False, "error": f"unknown action: {action}", "valid_actions": ["generate", "describe", "models"]}
