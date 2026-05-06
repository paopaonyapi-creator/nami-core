#!/usr/bin/env python3
"""Patch nami-bot to add /dispatch command."""
import re

BOT_FILE = "/opt/nami-bot/nami_bot.py"

with open(BOT_FILE, "r") as f:
    code = f.read()

# Add cmd_dispatch function before main()
dispatch_func = '''
async def cmd_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🚀 Dispatch a worker action via nami-core API"""
    if not await require_auth(update, context):
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "*🚀 Dispatch — ส่งคำสั่งไปยัง worker*\\n\\n"
            "Usage: `/dispatch <worker> <action> [payload]`\\n\\n"
            "Examples:\\n"
            "`/dispatch lottery vip`\\n"
            "`/dispatch gold prices`\\n"
            "`/dispatch status services`\\n"
            "`/dispatch miroshark status`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    worker = args[0]
    action = args[1]
    payload = {}
    if len(args) > 2:
        try:
            payload = json.loads(" ".join(args[2:]))
        except json.JSONDecodeError:
            payload = {"extra": " ".join(args[2:])}

    msg = await update.message.reply_text(f"🚀 Dispatching `{worker}/{action}`...", parse_mode=ParseMode.MARKDOWN)
    result = nami_core_dispatch(worker, action, payload)

    if result.get("ok"):
        output = result.get("output", {})
        text = f"✅ *{worker}/{action}*\\n```\\n{json.dumps(output, indent=2, ensure_ascii=False)[:3000]}\\n```"
        if result.get("latency_ms"):
            text += f"\\n⏱ {result['latency_ms']}ms"
    else:
        text = f"❌ *{worker}/{action}*\\n`{result.get('error', 'unknown error')}`"

    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)

'''

if "cmd_dispatch" not in code:
    code = code.replace("def main():", dispatch_func + "def main():")
    print("Added cmd_dispatch function")

# Add handler registration
if 'CommandHandler("dispatch"' not in code:
    code = code.replace(
        'app.add_handler(CommandHandler("vip", cmd_vip))',
        'app.add_handler(CommandHandler("vip", cmd_vip))\n    app.add_handler(CommandHandler("dispatch", cmd_dispatch))'
    )
    print("Added /dispatch handler")

with open(BOT_FILE, "w") as f:
    f.write(code)

print("Patch complete!")
