#!/usr/bin/env python3
"""Test WS broadcast: connect, then trigger a dispatch, see if message arrives."""
import asyncio, json, urllib.request

async def test():
    import websockets
    uri = "ws://127.0.0.1:8093"
    async with websockets.connect(uri, open_timeout=5) as ws:
        print("WS connected, triggering dispatch...")
        # Trigger a dispatch via HTTP
        data = json.dumps({"worker": "status", "action": "health", "payload": {}}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8092/dispatch", data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                print("Dispatch HTTP:", resp.status)
        except urllib.error.HTTPError as e:
            print(f"Dispatch HTTP error {e.code} (expected if auth required)")

        # Wait for WS broadcast
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            parsed = json.loads(msg)
            print(f"WS received: event={parsed.get('event')}, data={json.dumps(parsed.get('data', {}))[:200]}")
        except asyncio.TimeoutError:
            print("No WS broadcast within 5s")

asyncio.run(test())
