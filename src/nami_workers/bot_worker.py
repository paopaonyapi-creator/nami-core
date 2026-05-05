"""Bot Worker — General Nami Telegram bot commands.

Migrated from /opt/nami-bot.
Handles help, status, package info, and general commands.

Actions:
  - help: Show available commands
  - status: Show bot/service status
  - package_info: Show Premium package details
  - subscribe: Handle subscription request
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PACKAGES = {
    "basic": {"price": 299, "currency": "THB", "period": "month", "features": ["ภาพรวม + สัญญาณพื้นฐาน"]},
    "pro": {"price": 599, "currency": "THB", "period": "month", "features": ["เหตุผลละเอียด + risk assessment"]},
    "vip": {"price": 999, "currency": "THB", "period": "month", "features": ["early signal + priority support"]},
}

FOUNDER_PRICES = {"pro": 499, "vip": 799}


def help_command(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": (
            "Nami Bot Commands:\n"
            "/help — แสดงคำสั่ง\n"
            "/status — สถานะระบบ\n"
            "/packages — ดูแพ็กเกจ Premium\n"
            "/subscribe — สมัคร Premium"
        ),
    }


def status_command(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": "Nami Core: active\nHarness: operational\nWorkers: registered",
    }


def package_info(payload: dict[str, Any]) -> dict[str, Any]:
    lines = ["Nami Premium Packages:"]
    for name, info in PACKAGES.items():
        founder = FOUNDER_PRICES.get(name)
        price_line = f"  {name.title()}: ฿{info['price']}/{info['period']}"
        if founder:
            price_line += f" (Founder: ฿{founder} เดือนแรก)"
        lines.append(price_line)
        for feat in info["features"]:
            lines.append(f"    • {feat}")

    return {"answer": "\n".join(lines)}


def subscribe(payload: dict[str, Any]) -> dict[str, Any]:
    package = payload.get("package", "pro")
    if package not in PACKAGES:
        return {"answer": f"Unknown package: {package}. Choose: basic, pro, vip"}

    info = PACKAGES[package]
    founder = FOUNDER_PRICES.get(package)
    price = founder or info["price"]

    return {
        "answer": (
            f"สมัคร {package.title()} ฿{price}/{info['period']}\n"
            f"{'Founder Price เดือนแรก!' if founder else ''}\n"
            f"DM สมัคร: https://t.me/paopaonyza"
        ),
    }


ACTIONS: dict[str, callable] = {
    "help": help_command,
    "status": status_command,
    "package_info": package_info,
    "subscribe": subscribe,
}


def bot_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Main worker entry point."""
    action = payload.get("action", "help")

    handler = ACTIONS.get(action)
    if handler is None:
        return {"answer": f"Unknown command: {action}. Type /help for commands."}

    return handler(payload)
