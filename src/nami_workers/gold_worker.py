"""Gold Worker — Gold/Crypto signal engine integration.

Wraps the Gold Signal OS (telegram-premium-bot) and gold scraper
as a nami-core worker for unified access to gold/crypto signals.

Actions:
  - prices: Get latest gold/crypto prices
  - signal: Get gold trading signal
  - analysis: Get MiroShark AI analysis
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Gold Signal OS paths (from /opt/telegram-premium + /opt/gold-signal-os) ──
PRICES_FILE = os.environ.get("GOLD_PRICES_FILE", os.path.expanduser("~/.hermes/scraper/prices.json"))
MIROSHARK_OUTPUT = os.environ.get("MIROSHARK_OUTPUT", os.path.expanduser("~/.hermes/scraper/miroshark_output"))
GOLD_DB = os.environ.get("GOLD_DB", "/opt/gold-signal-os/gold_prices.db")


def _read_prices() -> dict[str, Any]:
    """Read latest gold/crypto prices from scraper output."""
    try:
        with open(PRICES_FILE) as f:
            data = json.load(f)
        hs = data.get("gold", {}).get("Huasengheng", {})
        crypto = data.get("crypto", {}).get("data", {})
        return {
            "timestamp": data.get("timestamp", "")[:19],
            "spot_usd": hs.get("gold_spot_usd"),
            "spot_thb": hs.get("gold_spot_thb"),
            "buy_thb": hs.get("gold_buy_thb"),
            "sell_thb": hs.get("gold_sell_thb"),
            "btc_usd": crypto.get("BTC", {}).get("price_usd"),
            "eth_usd": crypto.get("ETH", {}).get("price_usd"),
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Prices file unavailable: %s", e)
        return {"error": f"prices unavailable: {e}"}


def _read_miroshark_analysis() -> dict[str, Any]:
    """Read latest MiroShark AI analysis output."""
    try:
        # Find latest output file
        import glob
        files = sorted(glob.glob(os.path.join(MIROSHARK_OUTPUT, "*.json")), reverse=True)
        if not files:
            return {"error": "no analysis files found"}
        with open(files[0]) as f:
            data = json.load(f)
        return {
            "file": os.path.basename(files[0]),
            "analysis": data.get("analysis", data.get("content", ""))[:2000],
            "signal": data.get("signal", ""),
            "confidence": data.get("confidence", ""),
        }
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("MiroShark analysis unavailable: %s", e)
        return {"error": f"analysis unavailable: {e}"}


def prices(payload: dict[str, Any]) -> dict[str, Any]:
    """Get latest gold/crypto prices."""
    return _read_prices()


def signal(payload: dict[str, Any]) -> dict[str, Any]:
    """Get gold trading signal from MiroShark analysis."""
    analysis = _read_miroshark_analysis()
    prices_data = _read_prices()

    if "error" in analysis and "error" in prices_data:
        return {"error": "both analysis and prices unavailable"}

    return {
        "signal": analysis.get("signal", "neutral"),
        "confidence": analysis.get("confidence", "low"),
        "gold_spot": prices_data.get("spot_usd"),
        "gold_thb": prices_data.get("spot_thb"),
        "analysis_summary": analysis.get("analysis", "")[:500],
    }


def analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """Get full MiroShark AI analysis."""
    return _read_miroshark_analysis()


ACTIONS: dict[str, callable] = {
    "prices": prices,
    "signal": signal,
    "analysis": analysis,
}


def gold_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "prices")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
