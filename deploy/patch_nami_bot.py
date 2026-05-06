"""Patch nami-bot cmd_vip to use nami-core API instead of direct DB queries."""
import re

with open("/opt/nami-bot/nami_bot.py", "r") as f:
    content = f.read()

# Add urllib import after existing imports
if "import urllib.request" not in content:
    content = content.replace(
        "import json\n",
        "import json\nimport urllib.request\n"
    )

# Add NAMI_CORE_API constant
if "NAMI_CORE_API" not in content:
    content = content.replace(
        'VPS_IP = "178.104.181.132"',
        'VPS_IP = "178.104.181.132"\nNAMI_CORE_API = "http://127.0.0.1:8092"'
    )

# Replace cmd_vip function
old_vip_start = 'async def cmd_vip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:'
old_vip_end = 'await msg.edit_text(f"❌ Error: {str(e)[:200]}", parse_mode=ParseMode.MARKDOWN)'

old_vip_match = re.search(
    r'async def cmd_vip\(update: Update.*?\n.*?await msg\.edit_text\(f"❌ Error.*?ParseMode\.MARKDOWN\)',
    content,
    re.DOTALL
)

if old_vip_match:
    new_vip = '''async def cmd_vip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🎯 Show latest VIP lottery picks via nami-core API"""
    if not await require_auth(update, context):
        return

    msg = await update.message.reply_text("🎯 กำลังดึงเลข VIP...")

    try:
        # Call nami-core API
        req = urllib.request.Request(
            f"{NAMI_CORE_API}/dispatch",
            data=json.dumps({"worker": "lottery", "action": "vip", "payload": {"region": "lao"}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not data.get("ok"):
            await msg.edit_text("❌ nami-core VIP error", parse_mode=ParseMode.MARKDOWN)
            return

        vip = data.get("output", {})
        picks = vip.get("db_picks", vip)
        date = vip.get("target_date", vip.get("date", "—"))[:10]
        engine = picks.get("engine", "—").replace("Engine ", "")

        text = f"""🎯 *LaoPatana VIP — {date}*
🔮 Engine {engine}

━━━━━━━━━━━━━━

🔥 *1D วิ่ง:* `{', '.join(picks.get('1d', ['—']))}`
🎲 *2D หลัก:* `{', '.join(picks.get('2d_main', ['—']))}`
🎲 *2D รอง:* `{', '.join(picks.get('2d_secondary', ['—']))}`
🎰 *3D Exact:* `{', '.join(picks.get('3d', ['—']))}`

━━━━━━━━━━━━━━

📊 [ดู Dashboard](https://laopatana.178.104.181.132.nip.io)
🌸 @namiByPao_bot"""

        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:200]}", parse_mode=ParseMode.MARKDOWN)'''

    content = content[:old_vip_match.start()] + new_vip + content[old_vip_match.end():]
    print("✅ cmd_vip patched to use nami-core API")
else:
    print("❌ Could not find cmd_vip to patch")

with open("/opt/nami-bot/nami_bot.py", "w") as f:
    f.write(content)

print("Done! Restart nami-bot to apply.")
