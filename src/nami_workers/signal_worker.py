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
from pathlib import Path
from typing import Any

from .utils import ai_chat_completion, telegram_send

logger = logging.getLogger(__name__)

# ── VPS Price Data (from /opt/telegram-premium/signals_bot.py) ──
PRICES_FILE = os.environ.get(
    "PRICES_FILE", os.path.expanduser("~/.hermes/scraper/prices.json")
)
MIROSHARK_OUTPUT = os.environ.get(
    "MIROSHARK_OUTPUT", os.path.expanduser("~/.hermes/scraper/miroshark_output")
)


def read_prices() -> dict[str, Any]:
    """Read live gold/crypto prices from scraper data (VPS: /opt/telegram-premium)."""
    try:
        with open(PRICES_FILE) as f:
            data = json.load(f)
        hs = data.get("gold", {}).get("Huasengheng", {})
        crypto = data.get("crypto", {}).get("data", {})
        return {
            "timestamp": data.get("timestamp", "")[:19],
            "spot_usd": hs.get("gold_spot_usd"),
            "buy_thb": hs.get("gold_buy_thb"),
            "sell_thb": hs.get("gold_sell_thb"),
            "btc_usd": crypto.get("BTC", {}).get("price_usd") if isinstance(crypto, dict) else None,
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def read_miroshark_briefings() -> list[dict[str, Any]]:
    """Read latest MiroShark gold briefings (VPS: /opt/MiroShark output)."""
    briefings = []
    path = Path(MIROSHARK_OUTPUT)
    if not path.exists():
        return briefings
    for f in sorted(path.glob("gold_briefing_*.json"))[-3:]:
        try:
            briefings.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return briefings

SIGNAL_SYSTEM_PROMPT = """You are a professional market analyst AI.
Analyze the given symbol and provide a trading signal.

You MUST respond in this exact JSON format:
{
  "symbol": "XAU/USD",
  "price": "current_or_estimated_price",
  "direction": "Long" or "Short" or "No Trade",
  "confidence": "High" or "Medium" or "Low",
  "timeframe": "Day" or "4H" or "1H",
  "reasons": ["reason 1", "reason 2", "reason 3"],
  "risk_level": "High" or "Medium" or "Low",
  "invalidation": "price level where trade is invalidated"
}

Rules:
- Only give High confidence when 3+ confluences align
- Always include risk_level and invalidation
- Never use words like "guarantee", "sure", "certain"
- If no clear setup exists, set direction to "No Trade"
"""

SIGNAL_TEMPLATE = """🔔 Nami Premium Signal — {date}

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

    # Enrich with real VPS price data if available
    prices = read_prices()
    briefings = read_miroshark_briefings()
    context_parts = [f"Analyze {symbol} for {task} trading signal. Current date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"]
    if prices:
        context_parts.append(f"\nLive prices: Gold spot ${prices.get('spot_usd', 'N/A')}, Buy ฿{prices.get('buy_thb', 'N/A')}, Sell ฿{prices.get('sell_thb', 'N/A')}, BTC ${prices.get('btc_usd', 'N/A')}")
    if briefings:
        latest = briefings[-1]
        context_parts.append(f"\nLatest MiroShark briefing: {json.dumps(latest.get('prediction', {}), ensure_ascii=False)[:500]}")

    messages = [
        {"role": "system", "content": SIGNAL_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(context_parts)},
    ]

    ai_result = ai_chat_completion(messages, model="claude-3-sonnet")
    content = ai_result.get("content", "")

    # Parse AI response
    try:
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        data = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        logger.warning("AI response not valid JSON, using fallback")
        data = {
            "symbol": symbol,
            "price": "N/A",
            "direction": "No Trade",
            "confidence": "Low",
            "timeframe": "Day",
            "reasons": ["AI analysis unavailable"],
            "risk_level": "High",
            "invalidation": "N/A",
        }

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
        "ai_provider": ai_result.get("provider", "unknown"),
    }

    logger.info("Signal generated: %s %s (%s)", signal["symbol"], signal["direction"], signal["confidence"])
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

    direction = signal_data.get("direction", "N/A")
    if direction == "No Trade":
        message = NO_SIGNAL_TEMPLATE.format(reason="No high-confidence setup found today")
    else:
        message = SIGNAL_TEMPLATE.format(
            date=signal_data.get("date", "N/A"),
            symbol=signal_data.get("symbol", "N/A"),
            price=signal_data.get("price", "N/A"),
            direction=direction,
            confidence=signal_data.get("confidence", "N/A"),
            timeframe=signal_data.get("timeframe", "N/A"),
            reasons=signal_data.get("reason", "• N/A"),
            risk_level=signal_data.get("risk_level", "N/A"),
            invalidation=signal_data.get("invalidation", "N/A"),
        )

    result = telegram_send(channel, message)

    if result.get("ok"):
        logger.info("Signal sent to channel %s", channel)
        return {"sent": True, "message": message, "channel": channel}
    else:
        logger.error("Signal send failed: %s", result.get("error"))
        return {"sent": False, "message": f"Send failed: {result.get('error')}", "channel": channel}


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

    result = telegram_send(str(user_id), text)

    if result.get("ok"):
        logger.info("DM sent to user %s", user_id)
        return {"sent": True, "user_id": user_id}
    else:
        return {"sent": False, "user_id": user_id, "error": result.get("error")}


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
