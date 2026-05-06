#!/usr/bin/env python3
"""Test WS broadcast via webhook (no auth required)."""
import asyncio, json, urllib.request

async def test():
    import websockets
    uri = "ws://127.0.0.1:8093"
    async with websockets.connect(uri, open_timeout=5) as ws:
        print("WS connected, triggering webhook...")
        data = json.dumps({"source": "test", "event": "deploy", "data": {"v": "0.3.0"}}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8092/webhook", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            print("Webhook HTTP:", resp.status)

        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            parsed = json.loads(msg)
            print(f"WS received: event={parsed.get('event')}, data={json.dumps(parsed.get('data', {}))[:200]}")
        except asyncio.TimeoutError:
            print("No WS broadcast within 5s")

asyncio.run(test())
