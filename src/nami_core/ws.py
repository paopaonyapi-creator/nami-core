"""Nami WebSocket server — real-time push to dashboard clients."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import websockets

logger = logging.getLogger("nami.ws")

# Global set of connected clients
_clients: set[websockets.ServerConnection] = []
_loop: asyncio.AbstractEventLoop | None = None
_server: websockets.WebSocketServer | None = None


async def _handler(conn: websockets.ServerConnection) -> None:
    """Handle a new WebSocket client connection."""
    _clients.append(conn)
    logger.info("WS client connected (%d total)", len(_clients))
    try:
        # Keep connection alive; discard any incoming messages
        async for msg in conn:
            pass
    except websockets.ConnectionClosed:
        pass
    finally:
        if conn in _clients:
            _clients.remove(conn)
        logger.info("WS client disconnected (%d total)", len(_clients))


def broadcast(event: str, data: dict[str, Any]) -> None:
    """Broadcast an event to all connected WS clients (thread-safe)."""
    if not _loop or not _clients:
        return
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
    asyncio.run_coroutine_threadsafe(_broadcast(payload), _loop)


async def _broadcast(payload: str) -> None:
    """Async broadcast — send to all clients, drop disconnected ones."""
    to_remove = []
    for conn in list(_clients):
        try:
            await conn.send(payload)
        except websockets.ConnectionClosed:
            to_remove.append(conn)
    for conn in to_remove:
        if conn in _clients:
            _clients.remove(conn)


def start_ws_server(host: str = "127.0.0.1", port: int = 8093) -> None:
    """Start the WebSocket server in its own thread with its own event loop."""
    import threading

    def _run() -> None:
        global _loop, _server
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

        async def _serve() -> None:
            global _server
            _server = await websockets.serve(_handler, host, port)
            logger.info("WS server listening on %s:%d", host, port)
            await asyncio.Future()  # run forever

        _loop.run_until_complete(_serve())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info("WS server thread started")


def stop_ws_server() -> None:
    """Stop the WebSocket server."""
    if _loop and _server:
        asyncio.run_coroutine_threadsafe(_server.close(), _loop)
