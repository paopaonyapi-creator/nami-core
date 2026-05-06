#!/usr/bin/env python3
"""Test WebSocket connection to nami-core."""
import asyncio, sys
try:
    import websockets
except ImportError:
    print("websockets not installed"); sys.exit(1)

async def test():
    uri = "ws://127.0.0.1:8093"
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            print("WS connected OK")
            # Wait briefly for any messages
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                print(f"Received: {msg[:100]}")
            except asyncio.TimeoutError:
                print("No message within 2s (expected for idle connection)")
    except Exception as e:
        print(f"WS error: {e}")

asyncio.run(test())
