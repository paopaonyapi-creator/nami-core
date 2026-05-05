"""Shared utilities for Nami workers.

Common functions used across workers:
- Telegram API sender
- AI provider caller (via maxplus-proxy or direct)
- OANDA paper trading client
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

# ─── Telegram ───────────────────────────────────────────────────


def _get_telegram_token() -> str:
    """Load Telegram bot token from /etc/nami-harness."""
    token_path = os.environ.get(
        "TELEGRAM_TOKEN_PATH",
        "/etc/nami-harness/telegram_bot_token",
    )
    try:
        with open(token_path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def telegram_send(chat_id: str, text: str, *, parse_mode: str = "HTML") -> dict[str, Any]:
    """Send a message via Telegram Bot API.

    Returns the API response as a dict, or {"ok": False, "error": ...} on failure.
    """
    token = _get_telegram_token()
    if not token:
        logger.warning("No Telegram token configured")
        return {"ok": False, "error": "no_token"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        logger.error("Telegram send failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ─── AI Provider ────────────────────────────────────────────────


def _get_ai_config() -> dict[str, Any]:
    """Load AI provider config from /etc/nami-harness/ai_config.json."""
    config_path = os.environ.get(
        "AI_CONFIG_PATH",
        "/etc/nami-harness/ai_config.json",
    )
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        # Some old configs store just a key string
        if isinstance(data, str):
            return {"openrouter": {"api_key": data.strip()}}
        return {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def ai_chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str = "claude-3-sonnet",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """Call AI chat completion via maxplus-proxy or direct API.

    Tries proxy first, falls back to direct OpenRouter API.
    Returns dict with: content, model, provider, usage
    """
    proxy_url = os.environ.get("MAXPLUS_PROXY_URL", "http://localhost:8091")

    # Try proxy first
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{proxy_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "content": data.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "model": data.get("model", model),
                "provider": "proxy",
                "usage": data.get("usage", {}),
            }
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        logger.info("Proxy unavailable, trying direct API")

    # Fallback: direct OpenRouter API
    config = _get_ai_config()
    or_val = config.get("openrouter", {})
    openrouter_key = or_val if isinstance(or_val, str) else or_val.get("api_key", "")
    if not openrouter_key:
        return {"content": "", "model": model, "provider": "none", "usage": {}, "error": "no_api_key"}

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openrouter_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "content": data.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "model": data.get("model", model),
                "provider": "openrouter",
                "usage": data.get("usage", {}),
            }
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        logger.error("Direct API call failed: %s", exc)
        return {"content": "", "model": model, "provider": "none", "usage": {}, "error": str(exc)}


# ─── OANDA Paper Trading ────────────────────────────────────────


def _get_oanda_config() -> dict[str, str]:
    """Load OANDA credentials from /etc/nami-harness."""
    config_path = os.environ.get("OANDA_CONFIG_PATH", "/etc/nami-harness/oanda.env")
    result: dict[str, str] = {}
    try:
        with open(config_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    result[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return result


def oanda_paper_trade(
    instrument: str,
    units: int,
    direction: str,
    *,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict[str, Any]:
    """Place a paper trade via OANDA practice API.

    Returns dict with: order_id, instrument, units, direction, mode
    """
    config = _get_oanda_config()
    api_key = config.get("OANDA_API_KEY", "")
    account_id = config.get("OANDA_ACCOUNT_ID", "")

    if not api_key or not account_id:
        return {"error": "OANDA not configured", "mode": "paper"}

    base_url = "https://api-fxpractice.oanda.com"
    url = f"{base_url}/v3/accounts/{account_id}/orders"

    order_type = "MARKET"
    if direction.lower() == "short":
        units = -abs(units)

    order_body = {
        "order": {
            "type": order_type,
            "instrument": instrument,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
        }
    }

    if stop_loss:
        order_body["order"]["stopLossOnFill"] = {"price": str(stop_loss)}
    if take_profit:
        order_body["order"]["takeProfitOnFill"] = {"price": str(take_profit)}

    payload = json.dumps(order_body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "order_id": data.get("orderFillTransaction", {}).get("id", "unknown"),
                "instrument": instrument,
                "units": units,
                "direction": direction,
                "mode": "paper",
                "raw": data,
            }
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        logger.error("OANDA trade failed: %s", exc)
        return {"error": str(exc), "mode": "paper"}
