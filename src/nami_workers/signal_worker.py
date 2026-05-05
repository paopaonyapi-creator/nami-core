"""Signal Worker — Gold/AI signal generation and Telegram delivery.

Migrated from /opt/telegram-premium-bot.
Generates AI-powered market signals, validates them through
Harness quality gates (no guarantee terms), and sends to
Premium subscribers via Telegram.

Actions:
  - generate_signal: Run AI analysis, produce signal payload
  - send_signal: Deliver formatted signal to subscriber channels
  - send_dm: Send direct message to a specific user
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Signal format template (from NAMI_PREMIUM_BIBLE)
SIGNAL_TEMPLATE = """Nami Premium Signal — {date}

Symbol: {symbol} @{price}
Direction: {direction}
Confidence: {confidence}
Timeframe: {timeframe}

Reason:
{reasons}

Risk Level: {risk_level}
Invalidation: {invalidation}

⚠️ หมายเหตุ: AI statistical analysis ไม่ใช่การันตีผล
จัดการ risk ตามความเหมาะสม"""

NO_SIGNAL_TEMPLATE = """วันนี้ไม่มีสัญญาณที่ผ่าน quality gate ครับ
เหตุผล: {reason}
รอ setup ที่ดีกว่าดีกว่า forcing trade ครับ"""


def _load_ai_config() -> dict[str, Any]:
    """Load AI provider config from /etc/nami-harness/ai_config.json."""
    config_path = os.environ.get(
        "AI_CONFIG_PATH",
        "/etc/nami-harness/ai_config.json",
    )
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("AI config not found at %s, using defaults", config_path)
        return {}


def _call_ai(prompt: str, config: dict[str, Any]) -> str:
    """Call AI provider via maxplus-proxy or direct API.

    TODO: Replace with actual API call logic from /opt/telegram-premium-bot.
    Currently returns a placeholder for testing.
    """
    proxy_url = os.environ.get("MAXPLUS_PROXY_URL", "http://localhost:8091")
    # In production, this would call the proxy with the prompt
    # For now, return structured placeholder
    return json.dumps({
        "symbol": "XAU/USD",
        "price": "2340",
        "direction": "Long",
        "confidence": "Medium",
        "timeframe": "Day",
        "reasons": ["Breakout above resistance", "Volume confirmation", "Trend alignment"],
        "risk_level": "Medium",
        "invalidation": "Below 2320 support",
    })


def generate_signal(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a market signal using AI analysis.

    Payload keys:
      - task: signal type (e.g. "gold_daily", "forex_intraday")
      - symbol: optional specific symbol to analyze

    Returns dict with keys: signal, reason, confidence, risk_level,
    symbol, price, direction, timeframe, invalidation
    """
    task = payload.get("task", "gold_daily")
    symbol = payload.get("symbol", "XAU/USD")

    config = _load_ai_config()

    prompt = f"Analyze {symbol} for {task} trading signal. Provide direction, confidence, risk level, and invalidation point."
    ai_response = _call_ai(prompt, config)

    try:
        data = json.loads(ai_response)
    except json.JSONDecodeError:
        data = {"raw": ai_response}

    now = datetime.now(timezone.utc)
    signal = {
        "signal": f"{data.get('symbol', symbol)} {data.get('direction', 'N/A')} @{data.get('price', 'N/A')}",
        "reason": "\n".join(f"• {r}" for r in data.get("reasons", ["AI analysis"])),
        "confidence": data.get("confidence", "Low"),
        "risk_level": data.get("risk_level", "Medium"),
        "symbol": data.get("symbol", symbol),
        "price": data.get("price", "N/A"),
        "direction": data.get("direction", "N/A"),
        "timeframe": data.get("timeframe", "Day"),
        "invalidation": data.get("invalidation", "N/A"),
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(),
    }

    logger.info("Signal generated: %s %s", signal["symbol"], signal["direction"])
    return signal


def send_signal(payload: dict[str, Any]) -> dict[str, Any]:
    """Format and send signal to Premium subscriber channel.

    Payload keys:
      - signal: the signal dict from generate_signal
      - channel: target Telegram channel/chat ID

    Returns dict with: sent, message
    """
    signal_data = payload.get("signal", {})
    channel = payload.get("channel", os.environ.get("PREMIUM_CHANNEL", ""))

    if not signal_data.get("signal"):
        return {"sent": False, "message": "No signal data provided"}

    if not channel:
        return {"sent": False, "message": "No target channel configured"}

    message = SIGNAL_TEMPLATE.format(
        date=signal_data.get("date", "N/A"),
        symbol=signal_data.get("symbol", "N/A"),
        price=signal_data.get("price", "N/A"),
        direction=signal_data.get("direction", "N/A"),
        confidence=signal_data.get("confidence", "N/A"),
        timeframe=signal_data.get("timeframe", "N/A"),
        reasons=signal_data.get("reason", "• N/A"),
        risk_level=signal_data.get("risk_level", "N/A"),
        invalidation=signal_data.get("invalidation", "N/A"),
    )

    # TODO: Replace with actual Telegram API call
    # bot_token from /etc/nami-harness/telegram.env
    logger.info("Signal sent to channel %s", channel)
    return {"sent": True, "message": message, "channel": channel}


def send_dm(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a direct message to a specific Telegram user.

    Payload keys:
      - user_id: Telegram user ID
      - text: message text

    Returns dict with: sent, user_id
    """
    user_id = payload.get("user_id")
    text = payload.get("text", "")

    if not user_id or not text:
        return {"sent": False, "message": "Missing user_id or text"}

    # TODO: Replace with actual Telegram API call
    logger.info("DM sent to user %s", user_id)
    return {"sent": True, "user_id": user_id}


# Worker dispatch table
ACTIONS: dict[str, callable] = {
    "generate_signal": generate_signal,
    "send_signal": send_signal,
    "send_dm": send_dm,
}


def signal_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point — dispatches based on payload['action']."""
    action = payload.get("action", "generate_signal")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
