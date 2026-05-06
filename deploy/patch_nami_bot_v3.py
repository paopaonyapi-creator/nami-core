#!/usr/bin/env python3
"""Patch nami-bot to add nami-core to PROJECTS and /logs /restart."""
import re

BOT_FILE = "/opt/nami-bot/nami_bot.py"

with open(BOT_FILE, "r") as f:
    code = f.read()

# 1. Add nami-core to PROJECTS dict (after oracle line)
if '"nami_core"' not in code and '"nami-core"' not in code:
    code = code.replace(
        '"oracle": {"name": "🔮 Nami Oracle", "port": 8003,',
        '"oracle": {"name": "🔮 Nami Oracle", "port": 8003,'
    )
    # Add after agent_hq entry
    code = code.replace(
        '"agent_hq": {"name": "🏢 Agent HQ", "port": None, "url": f"http://hq.{VPS_IP}.nip.io", "service": None},\n}',
        '"agent_hq": {"name": "🏢 Agent HQ", "port": None, "url": f"http://hq.{VPS_IP}.nip.io", "service": None},\n    "nami_core": {"name": "🌸 Nami Core", "port": 8092, "url": f"http://nami-api.{VPS_IP}.nip.io", "service": "nami-core"},\n}'
    )
    print("Added nami_core to PROJECTS")

# 2. Add nami-core to /logs nami section (include nami-core service)
if "nami-core" not in code.split("cmd_logs")[1].split("cmd_vip")[0] if "cmd_vip" in code else "":
    code = code.replace(
        'for svc in ["nami-bridge", "nami-api-gateway", "nami-status-api"]:',
        'for svc in ["nami-core", "nami-bridge", "nami-api-gateway", "nami-status-api"]:'
    )
    print("Added nami-core to /logs nami")

# 3. Add nami-core health to /logs options
if "/logs nami-core" not in code:
    code = code.replace(
        'lines.append("`/logs nami` — All Nami services")',
        'lines.append("`/logs nami-core` — Nami Core daemon")\n        lines.append("`/logs nami` — All Nami services")'
    )
    print("Added /logs nami-core option")

with open(BOT_FILE, "w") as f:
    f.write(code)

print("Patch complete!")
