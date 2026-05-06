#!/usr/bin/env python3
"""Patch nami-bot cmd_status, cmd_health, cmd_agents to use nami-core API."""
import re

with open("/opt/nami-bot/nami_bot.py", "r") as f:
    content = f.read()

# Ensure NAMI_CORE_API is defined
if "NAMI_CORE_API" not in content:
    content = content.replace(
        'VPS_IP = "178.104.181.132"',
        'VPS_IP = "178.104.181.132"\nNAMI_CORE_API = "http://127.0.0.1:8092"'
    )

# Ensure urllib.request is imported
if "import urllib.request" not in content:
    content = content.replace(
        "import json\n",
        "import json\nimport urllib.request\n"
    )

# Helper function for nami-core API calls
HELPER_FUNC = '''

def nami_core_dispatch(worker, action, payload=None):
    """Call nami-core API dispatch endpoint."""
    try:
        data = json.dumps({"worker": worker, "action": action, "payload": payload or {}}).encode("utf-8")
        req = urllib.request.Request(
            f"{NAMI_CORE_API}/dispatch",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def nami_core_get(path):
    """Call nami-core API GET endpoint."""
    try:
        req = urllib.request.Request(f"{NAMI_CORE_API}{path}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

'''

if "def nami_core_dispatch" not in content:
    # Insert before the auth_check function
    content = content.replace(
        "async def auth_check",
        HELPER_FUNC + "async def auth_check"
    )

# Patch cmd_status — replace the whole function
old_status = re.search(
    r'async def cmd_status\(update: Update.*?\n(?=\nasync def cmd_|\n# ───)',
    content,
    re.DOTALL
)

if old_status:
    new_status = '''async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📊 Show system status via nami-core API"""
    if not await require_auth(update, context):
        return

    msg = await update.message.reply_text("📊 กำลังตรวจสอบ...")

    try:
        health = nami_core_get("/health")
        workers = health.get("workers", [])
        sched = health.get("scheduler", {})

        text = f"""📊 *Nami Core Status*
━━━━━━━━━━━━━━

🟢 Workers: {len(workers)}
⏰ Scheduler: {"running" if sched.get("running") else "stopped"}
📋 Jobs: {sched.get("jobs", 0)}

*Workers:* {', '.join(workers[:8])}{'...' if len(workers) > 8 else ''}

━━━━━━━━━━━━━━
🌸 @namiByPao_bot"""

        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:200]}", parse_mode=ParseMode.MARKDOWN)

'''
    content = content[:old_status.start()] + new_status + content[old_status.end():]
    print("✅ cmd_status patched")

# Patch cmd_health — replace the whole function
old_health = re.search(
    r'async def cmd_health\(update: Update.*?\n(?=\nasync def cmd_|\n# ───)',
    content,
    re.DOTALL
)

if old_health:
    new_health = '''async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🏥 Health check via nami-core API"""
    if not await require_auth(update, context):
        return

    msg = await update.message.reply_text("🏥 กำลังตรวจสุขภาพ...")

    try:
        result = nami_core_dispatch("status", "services")
        if result.get("ok") and result.get("output"):
            svcs = result["output"].get("services", [])
            active = result["output"].get("active", 0)
            failed = result["output"].get("failed", 0)

            lines = []
            for s in svcs[:15]:
                icon = "🟢" if s.get("active") else "🔴"
                lines.append(f"{icon} {s['service']}")

            text = f"""🏥 *Health Check*
━━━━━━━━━━━━━━

✅ Active: {active}
❌ Failed: {failed}

{chr(10).join(lines)}

━━━━━━━━━━━━━━
🌸 @namiByPao_bot"""

            await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.edit_text("❌ nami-core unavailable", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:200]}", parse_mode=ParseMode.MARKDOWN)

'''
    content = content[:old_health.start()] + new_health + content[old_health.end():]
    print("✅ cmd_health patched")

# Patch cmd_agents — replace the whole function
old_agents = re.search(
    r'async def cmd_agents\(update: Update.*?\n(?=\nasync def cmd_|\n# ───)',
    content,
    re.DOTALL
)

if old_agents:
    new_agents = '''async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🤖 List nami-core workers and agents via API"""
    if not await require_auth(update, context):
        return

    msg = await update.message.reply_text("🤖 กำลังดึงข้อมูล...")

    try:
        workers_resp = nami_core_get("/workers")
        workers = workers_resp.get("workers", [])

        lines = []
        for w in workers:
            actions = ', '.join(w.get("actions", []))
            lines.append(f"⚙️ *{w['name']}*: {actions}")

        text = f"""🤖 *Nami Workers*
━━━━━━━━━━━━━━

{chr(10).join(lines)}

━━━━━━━━━━━━━━
🌸 @namiByPao_bot"""

        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:200]}", parse_mode=ParseMode.MARKDOWN)

'''
    content = content[:old_agents.start()] + new_agents + content[old_agents.end():]
    print("✅ cmd_agents patched")

with open("/opt/nami-bot/nami_bot.py", "w") as f:
    f.write(content)

print("Done! Restart nami-bot to apply.")
