"""Lottery Worker — Hanoi + Lao lottery AI prediction engine.

Migrated from /opt/hanoi-bot and /opt/laopatana-stat-lab.
Shared prediction engine for both Hanoi (Vietnam) and Lao lotteries.

Actions:
  - predict: Generate lottery prediction for a region
  - send_prediction: Format and send prediction to channel
  - fetch_results: Fetch latest draw results
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

from .utils import ai_chat_completion, telegram_send

logger = logging.getLogger(__name__)

# ── VPS Lottery API (from /opt/hanoi-bot) ──
LOTTERY_API_BASE = os.environ.get("LOTTERY_API_BASE", "http://127.0.0.1:3000/api")

REGION_CONFIG = {
    "hanoi": {"name_th": "ฮานอย", "draw_types": ["special", "normal", "vip"]},
    "lao": {"name_th": "ลาว", "draw_types": ["main"]},
}


def fetch_draw_results(region: str = "hanoi", limit: int = 30) -> list[dict[str, Any]]:
    """Fetch recent draw results from VPS lottery API (/opt/hanoi-bot)."""
    try:
        url = f"{LOTTERY_API_BASE}/results?limit={limit}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        logger.warning("Lottery API unavailable for results")
        return []


def fetch_predictions(region: str = "hanoi") -> dict[str, Any]:
    """Fetch AI predictions from VPS lottery API (/opt/hanoi-bot/hanoi_ai.py)."""
    preds = {}
    cfg = REGION_CONFIG.get(region, REGION_CONFIG["hanoi"])
    for draw_type in cfg.get("draw_types", ["special"]):
        try:
            url = f"{LOTTERY_API_BASE}/predict/{draw_type}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                preds[draw_type] = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
            logger.warning("Lottery predict %s unavailable: %s", draw_type, e)
            preds[draw_type] = {"error": str(e)}
    return preds

PREDICTION_SYSTEM_PROMPT = """You are a lottery statistical analysis AI.
Analyze historical patterns for the given region lottery and provide predictions.

You MUST respond in this exact JSON format:
{
  "numbers": [n1, n2, n3, n4, n5, n6],
  "method": "statistical method name",
  "confidence": "Low" or "Very Low",
  "analysis": "brief explanation of the statistical approach"
}

Rules:
- Provide numbers within the valid range for the region
- Never claim high confidence or guarantee results
- Always include risk disclaimer
- This is for entertainment and statistical research only
"""

PREDICTION_TEMPLATE = """🎰 Nami Lottery Prediction — {region}

Numbers: {prediction}
Method: {method}
Confidence: {confidence}

⚠️ หมายเหตุ: AI statistical analysis ไม่ใช่การันตีผล
จัดการ risk ตามความเหมาะสม"""

REGIONS = {
    "hanoi": {"name": "Hanoi (Hà Nội)", "format": "6 numbers", "range": "1-99"},
    "lao": {"name": "Lao (ລາວ)", "format": "5 numbers", "range": "1-55"},
}


def predict(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate lottery prediction for a region.

    Payload keys:
      - region: "hanoi" or "lao"

    Returns dict with: prediction, region, method, confidence
    """
    region = payload.get("region", "hanoi")

    if region not in REGIONS:
        return {"error": f"unknown region: {region}", "valid_regions": list(REGIONS.keys())}

    region_info = REGIONS[region]

    logger.info("Prediction request for %s", region_info["name"])

    # Try VPS lottery API predictions first
    vps_preds = fetch_predictions(region)
    vps_results = fetch_draw_results(region, limit=10)

    # Build enriched prompt with VPS data
    context = f"Generate prediction for {region_info['name']} lottery. Format: {region_info['format']}, Range: {region_info['range']}"
    if vps_preds and not all("error" in v for v in vps_preds.values()):
        context += f"\n\n=== VPS Engine Predictions ===\n{json.dumps(vps_preds, ensure_ascii=False)[:800]}"
    if vps_results:
        context += f"\n\n=== Recent Results (last 5) ===\n{json.dumps(vps_results[:5], ensure_ascii=False)[:500]}"

    messages = [
        {"role": "system", "content": PREDICTION_SYSTEM_PROMPT},
        {"role": "user", "content": context},
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
        numbers = data.get("numbers", [])
        method = data.get("method", "AI statistical analysis")
        confidence = data.get("confidence", "Low")
    except (json.JSONDecodeError, IndexError):
        # Fallback: random numbers
        import random
        max_num = 100 if region == "hanoi" else 56
        count = 6 if region == "hanoi" else 5
        numbers = sorted(random.sample(range(1, max_num), count))
        method = "AI statistical analysis"
        confidence = "Low"

    prediction = ", ".join(str(n) for n in numbers)

    return {
        "prediction": prediction,
        "region": region,
        "method": method,
        "confidence": confidence,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def send_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    """Format and send prediction to subscriber channel.

    Payload keys:
      - prediction: prediction dict from predict()
      - channel: target Telegram channel/chat ID

    Returns dict with: sent, message
    """
    pred_data = payload.get("prediction", {})
    channel = payload.get("channel", os.environ.get("LOTTERY_CHANNEL", ""))

    if not pred_data.get("prediction"):
        return {"sent": False, "message": "No prediction data provided"}

    if not channel:
        return {"sent": False, "message": "No target channel configured"}

    message = PREDICTION_TEMPLATE.format(
        region=REGIONS.get(pred_data.get("region", "hanoi"), {}).get("name", "Unknown"),
        prediction=pred_data.get("prediction", "N/A"),
        method=pred_data.get("method", "N/A"),
        confidence=pred_data.get("confidence", "N/A"),
    )

    result = telegram_send(channel, message)

    if result.get("ok"):
        logger.info("Prediction sent to channel %s", channel)
        return {"sent": True, "message": message, "channel": channel}
    else:
        return {"sent": False, "message": f"Send failed: {result.get('error')}", "channel": channel}


def fetch_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch latest draw results for a region.

    Payload keys:
      - region: "hanoi" or "lao"

    Returns dict with: results, region, draw_date
    """
    region = payload.get("region", "hanoi")

    if region not in REGIONS:
        return {"error": f"unknown region: {region}"}

    # Use VPS lottery API (from /opt/hanoi-bot/hanoi_scraper_kqxs.py)
    results = fetch_draw_results(region, limit=30)
    logger.info("Fetched %d results for %s", len(results), region)

    return {
        "results": results[:10],
        "total": len(results),
        "region": region,
        "draw_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


ACTIONS: dict[str, callable] = {
    "predict": predict,
    "send_prediction": send_prediction,
    "fetch_results": fetch_results,
}


def lottery_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "predict")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
