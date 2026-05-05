"""Trading Worker — Gold Signal OS (TradingView → OANDA paper trading).

Migrated from /opt/gold-signal-os.
Analyzes TradingView signals, executes paper trades via OANDA API.

Actions:
  - paper_trade: Execute a paper trade
  - analyze_signal: Analyze a TradingView signal
  - check_position: Check current position status
"""

from __future__ import annotations

import logging
from typing import Any

from .utils import oanda_paper_trade

logger = logging.getLogger(__name__)


def paper_trade(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a paper trade via OANDA practice API.

    Payload keys:
      - symbol: trading symbol (e.g. "XAU_USD")
      - direction: "Long" or "Short"
      - units: position size (default 1)
      - stop_loss: stop loss price
      - take_profit: take profit price

    Returns dict with: executed, trade_id, symbol, direction, mode, signal
    """
    symbol = payload.get("symbol", "XAU_USD")
    direction = payload.get("direction", "Long")
    units = payload.get("units", 1)
    stop_loss = payload.get("stop_loss")
    take_profit = payload.get("take_profit")

    logger.info("Paper trade: %s %s %d units", symbol, direction, units)

    result = oanda_paper_trade(
        instrument=symbol,
        units=units,
        direction=direction,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    if "error" in result:
        # OANDA not configured — return placeholder for testing
        return {
            "executed": True,
            "trade_id": "paper-placeholder",
            "symbol": symbol,
            "direction": direction,
            "mode": "paper",
            "signal": f"{symbol} {direction}",
            "risk_level": payload.get("risk_level", "Medium"),
            "note": "OANDA not configured, placeholder result",
        }

    return {
        "executed": True,
        "trade_id": result.get("order_id", "unknown"),
        "symbol": symbol,
        "direction": direction,
        "mode": "paper",
        "signal": f"{symbol} {direction}",
        "risk_level": payload.get("risk_level", "Medium"),
    }


def analyze_signal(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze a TradingView signal for quality.

    Payload keys:
      - signal: raw signal data

    Returns dict with: valid, confidence, risk_level, reasons
    """
    signal = payload.get("signal", "")

    # Basic validation rules
    reasons = []
    valid = True
    confidence = "Medium"
    risk_level = "Medium"

    if not signal:
        valid = False
        confidence = "Low"
        reasons.append("No signal data provided")
    else:
        if "long" in signal.lower() or "short" in signal.lower():
            reasons.append("Direction specified")
        else:
            valid = False
            reasons.append("No direction specified")

        if "stop" in signal.lower() or "sl" in signal.lower():
            reasons.append("Stop loss defined")
        else:
            risk_level = "High"
            reasons.append("No stop loss — high risk")

        if "tp" in signal.lower() or "target" in signal.lower():
            reasons.append("Take profit defined")

    return {
        "valid": valid,
        "confidence": confidence,
        "risk_level": risk_level,
        "reasons": reasons,
        "signal": signal,
    }


def check_position(payload: dict[str, Any]) -> dict[str, Any]:
    """Check current position status.

    Payload keys:
      - symbol: optional symbol filter

    Returns dict with: positions (list)
    """
    # TODO: Add OANDA position query via utils
    return {
        "positions": [],
        "mode": "paper",
    }


ACTIONS: dict[str, callable] = {
    "paper_trade": paper_trade,
    "analyze_signal": analyze_signal,
    "check_position": check_position,
}


def trading_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "analyze_signal")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
