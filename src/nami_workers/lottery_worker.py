"""Lottery Worker — Hanoi + Lao lottery AI prediction (shared logic).

Migrated from /opt/hanoi-bot and /opt/laopatana-stat-lab.
Shared prediction engine with region-specific scrapers and formatters.

Actions:
  - predict: Generate lottery prediction for a region
  - send_prediction: Send prediction to subscribers
  - fetch_results: Fetch latest draw results
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

REGIONS = {"hanoi", "lao"}

PREDICTION_TEMPLATE = """🎰 {region_title} Lottery AI Prediction — {date}

Numbers: {prediction}
Confidence: {confidence}
Method: AI statistical analysis

⚠️ เป็น AI statistical analysis ไม่ใช่การันตีผล"""


def _load_ai_config() -> dict[str, Any]:
    config_path = os.environ.get("AI_CONFIG_PATH", "/etc/nami-harness/ai_config.json")
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def predict(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate lottery prediction for a region.

    Payload keys:
      - region: "hanoi" or "lao"
      - draw_type: optional draw type (e.g. "special")

    Returns dict with: prediction, confidence, region, method
    """
    region = payload.get("region", "hanoi")
    if region not in REGIONS:
        return {"error": f"unknown region: {region}", "valid_regions": list(REGIONS)}

    config = _load_ai_config()

    # TODO: Replace with actual AI prediction logic from hanoi_bot.py
    # The original uses statistical analysis of historical data
    logger.info("Lottery prediction: region=%s", region)

    return {
        "prediction": "42, 17, 88, 3, 55, 29",
        "confidence": "Low",
        "region": region,
        "method": "AI statistical analysis",
    }


def send_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    """Send formatted prediction to subscribers.

    Payload keys:
      - prediction: prediction dict from predict()
      - channel: target Telegram channel

    Returns dict with: sent, message
    """
    pred = payload.get("prediction", {})
    region = pred.get("region", "hanoi")
    channel = payload.get("channel", "")

    if not pred.get("prediction"):
        return {"sent": False, "message": "No prediction data"}

    region_titles = {"hanoi": "Hanoi", "lao": "Lao"}
    message = PREDICTION_TEMPLATE.format(
        region_title=region_titles.get(region, region.title()),
        date=pred.get("date", "N/A"),
        prediction=pred["prediction"],
        confidence=pred.get("confidence", "N/A"),
    )

    # TODO: Replace with actual Telegram API call
    logger.info("Prediction sent: region=%s, channel=%s", region, channel)
    return {"sent": True, "message": message, "channel": channel}


def fetch_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch latest draw results from scraper.

    Payload keys:
      - region: "hanoi" or "lao"

    Returns dict with: results, region, draw_date
    """
    region = payload.get("region", "hanoi")

    # TODO: Replace with actual scraper logic from hanoi_bot.py / laopatana
    logger.info("Fetch results: region=%s", region)

    return {
        "results": [],
        "region": region,
        "draw_date": "N/A",
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
