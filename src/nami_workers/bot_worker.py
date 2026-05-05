"""Bot Worker — General Nami Telegram bot commands.

Migrated from /opt/nami-bot.
Handles common Telegram bot commands like help, status, packages, subscribe.

Actions:
  - help: Show help message
  - status: Show system status
  - package_info: Show premium package info
  - subscribe: Handle subscription request
"""

from __future__ import annotations

import logging
from typing import Any

from .utils import telegram_send

logger = logging.getLogger(__name__)

PACKAGES = {
    "basic": {"name": "Basic", "price": "฿299/month", "features": ["ภาพรวม + สัญญาณพื้นฐาน", "1 ช่องสัญญาณ"]},
    "pro": {"name": "Pro", "price": "฿599/month", "features": ["สัญญาณ AI ครบชุด", "3 ช่องสัญญาณ", "Lottery prediction"]},
    "vip": {"name": "VIP", "price": "฿999/month", "features": ["ทุกอย่างใน Pro", "Paper trading signals", "Direct DM support", "Priority access"]},
}


def help(payload: dict[str, Any]) -> dict[str, Any]:
    """Show help message with available commands.

    Returns dict with: answer
    """
    return {
        "answer": (
            "🤖 Nami Bot Commands:\n\n"
            "/help — Show this help\n"
            "/status — System status\n"
            "/packages — Premium packages\n"
            "/subscribe <package> — Subscribe to a package\n\n"
            "Powered by Nami Core"
        ),
    }


def status(payload: dict[str, Any]) -> dict[str, Any]:
    """Show system status.

    Returns dict with: answer
    """
    return {
        "answer": (
            "📊 Nami System Status:\n\n"
            "✅ Signal Worker — Active\n"
            "✅ Proxy Worker — Active\n"
            "✅ Lottery Worker — Active\n"
            "✅ Trading Worker — Active\n"
            "✅ Gateway Worker — Active\n\n"
            "All systems operational"
        ),
    }


def package_info(payload: dict[str, Any]) -> dict[str, Any]:
    """Show premium package info.

    Returns dict with: answer
    """
    lines = ["Nami Premium Packages:\n"]
    for key, pkg in PACKAGES.items():
        lines.append(f"  {pkg['name']}: {pkg['price']}")
        for feat in pkg["features"]:
            lines.append(f"    • {feat}")
        lines.append("")

    return {"answer": "\n".join(lines)}


def subscribe(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle subscription request.

    Payload keys:
      - package: package key (basic, pro, vip)
      - user_id: Telegram user ID (optional, for DM reply)

    Returns dict with: answer
    """
    package_key = payload.get("package", "basic").lower()
    user_id = payload.get("user_id")

    if package_key not in PACKAGES:
        return {"answer": f"Unknown package: {package_key}. Available: basic, pro, vip"}

    pkg = PACKAGES[package_key]

    logger.info("Subscription request for %s", pkg["name"])

    answer = (
        f"✅ Subscription request received!\n\n"
        f"Package: {pkg['name']}\n"
        f"Price: {pkg['price']}\n\n"
        f"Please contact @paopaonyza for payment details."
    )

    # Send DM reply if user_id provided
    if user_id:
        telegram_send(str(user_id), answer)

    return {"answer": answer}


ACTIONS: dict[str, callable] = {
    "help": help,
    "status": status,
    "package_info": package_info,
    "subscribe": subscribe,
}


def bot_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "help")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"error": f"unknown action: {action}"}

    return handler(payload)
