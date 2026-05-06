#!/usr/bin/env python3
"""Patch hanoi-bot to use nami-core API for results and predictions."""
import re

with open("/opt/hanoi-bot/hanoi_bot.py", "r") as f:
    content = f.read()

# Add nami-core API helpers
if "NAMI_CORE_API" not in content:
    content = content.replace(
        "HANOI_API = os.getenv",
        'NAMI_CORE_API = os.getenv("NAMI_CORE_API_URL", "http://127.0.0.1:8092")\nHANOI_API = os.getenv'
    )

if "import urllib.request" not in content:
    content = content.replace(
        "import json\n",
        "import json\nimport urllib.request as urllib_req\n"
    )

HELPER = '''

def _nami_core_dispatch(worker, action, payload=None):
    """Call nami-core API."""
    try:
        data = json.dumps({"worker": worker, "action": action, "payload": payload or {}}).encode("utf-8")
        req = urllib_req.Request(
            f"{NAMI_CORE_API}/dispatch",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib_req.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("nami-core dispatch failed: %s", e)
        return {"ok": False, "error": str(e)}

'''

if "def _nami_core_dispatch" not in content:
    content = content.replace(
        "async def fetch_results",
        HELPER + "async def fetch_results"
    )

# Patch fetch_results to try nami-core first, fallback to direct API
old_fetch = re.search(
    r'async def fetch_results\(limit=10\):.*?return \[\]',
    content,
    re.DOTALL
)

if old_fetch:
    new_fetch = '''async def fetch_results(limit=10):
    """Fetch latest draw results — try nami-core first, fallback to direct API."""
    # Try nami-core
    result = _nami_core_dispatch("lottery", "fetch_results", {"region": "hanoi"})
    if result.get("ok") and result.get("output", {}).get("results"):
        return result["output"]["results"][:limit]

    # Fallback to direct API
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(f"{HANOI_API}/results", params={"limit": limit})
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []'''
    content = content[:old_fetch.start()] + new_fetch + content[old_fetch.end():]
    print("✅ fetch_results patched")

with open("/opt/hanoi-bot/hanoi_bot.py", "w") as f:
    f.write(content)

print("Done! Restart hanoi-bot to apply.")
