"""Nami Core Python SDK — async client and WebSocket listener."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

logger = logging.getLogger("nami_sdk.async_client")

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]


class NamiAsyncClient:
    """Async client for the nami-core API using httpx."""

    def __init__(self, base_url: str = "http://127.0.0.1:8092", api_key: str = "", timeout: int = 30) -> None:
        if httpx is None:
            raise ImportError("httpx is required for NamiAsyncClient: pip install httpx")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def _get(self, path: str) -> dict[str, Any]:
        resp = await self._client.get(path, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(path, json=data, headers=self._headers())
        if resp.status_code >= 400:
            try:
                err = resp.json()
                return {"error": err.get("detail", err), "status": resp.status_code}
            except Exception:
                return {"error": resp.text, "status": resp.status_code}
        return resp.json()

    async def health(self) -> dict[str, Any]:
        return await self._get("/health")

    async def workers(self) -> list[dict[str, Any]]:
        return (await self._get("/workers")).get("workers", [])

    async def scheduler(self) -> dict[str, Any]:
        return await self._get("/scheduler")

    async def metrics(self) -> dict[str, Any]:
        return await self._get("/metrics")

    async def dispatch(self, worker: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._post("/dispatch", {"worker": worker, "action": action, "payload": payload or {}})

    async def webhook(self, source: str, event: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._post("/webhook", {"source": source, "event": event, "data": data or {}})

    async def audit(self, limit: int = 50) -> dict[str, Any]:
        return await self._get(f"/audit?limit={limit}")

    async def rotate_key(self, new_key: str) -> dict[str, Any]:
        return await self._post("/rotate-key", {"new_key": new_key})

    async def scheduler_run_now(self, job: str) -> dict[str, Any]:
        return await self.dispatch("scheduler", "run_now", {"job": job})

    async def cron_schedule(self, worker: str, action: str, run_at: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.dispatch("cron", "schedule", {
            "worker": worker, "cron_action": action, "run_at": run_at, "job_payload": payload or {},
        })

    async def cron_list(self, status: str = "pending") -> dict[str, Any]:
        return await self.dispatch("cron", "list", {"status": status})

    async def cron_cancel(self, job_id: int) -> dict[str, Any]:
        return await self.dispatch("cron", "cancel", {"job_id": job_id})

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "NamiAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


class NamiWSListener:
    """WebSocket listener for nami-core real-time events with auto-reconnect."""

    def __init__(
        self,
        base_url: str = "ws://127.0.0.1:8092/ws",
        on_dispatch: Callable[[dict[str, Any]], None] | None = None,
        on_webhook: Callable[[dict[str, Any]], None] | None = None,
        on_scheduler: Callable[[dict[str, Any]], None] | None = None,
        on_any: Callable[[str, dict[str, Any]], None] | None = None,
        retry_delay: float = 3.0,
        max_retry: float = 30.0,
    ) -> None:
        self.base_url = base_url
        self.on_dispatch = on_dispatch
        self.on_webhook = on_webhook
        self.on_scheduler = on_scheduler
        self.on_any = on_any
        self._retry_delay = retry_delay
        self._max_retry = max_retry
        self._running = False

    async def listen(self) -> None:
        """Start listening for WebSocket events with auto-reconnect."""
        self._running = True
        delay = self._retry_delay

        while self._running:
            try:
                import websockets
                async with websockets.connect(self.base_url) as ws:
                    logger.info("WS connected to %s", self.base_url)
                    delay = self._retry_delay
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            event = msg.get("event", "")
                            data = msg.get("data", {})

                            if self.on_any:
                                self.on_any(event, data)
                            if event == "dispatch" and self.on_dispatch:
                                self.on_dispatch(data)
                            elif event == "webhook" and self.on_webhook:
                                self.on_webhook(data)
                            elif event == "scheduler" and self.on_scheduler:
                                self.on_scheduler(data)
                        except json.JSONDecodeError:
                            logger.warning("WS: invalid JSON from server")
            except ImportError:
                logger.error("websockets package required: pip install websockets")
                break
            except Exception as exc:
                logger.warning("WS disconnected: %s, retrying in %.0fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, self._max_retry)

    def stop(self) -> None:
        """Stop the listener."""
        self._running = False
