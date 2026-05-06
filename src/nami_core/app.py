"""Nami Core FastAPI application — async HTTP + WebSocket server."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("nami_core.app")

# ── Audit trail ──

AUDIT_DB = os.environ.get("NAMI_AUDIT_DB", "/tmp/nami_audit.db")

def _audit_log(worker: str, action: str, caller_ip: str, ok: bool, latency_ms: float) -> None:
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker TEXT, action TEXT, caller_ip TEXT,
                ok BOOLEAN, latency_ms REAL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO audit_log (worker, action, caller_ip, ok, latency_ms, timestamp) VALUES (?,?,?,?,?,?)",
            (worker, action, caller_ip, ok, latency_ms, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Audit log failed: %s", exc)


# ── Pydantic models ──

class DispatchRequest(BaseModel):
    worker: str
    action: str
    payload: dict[str, Any] = {}

class WebhookRequest(BaseModel):
    source: str = "unknown"
    event: str = "ping"
    data: dict[str, Any] = {}

class DispatchResponse(BaseModel):
    ok: bool
    output: dict[str, Any] | None = None
    latency_ms: float | None = None
    error: str | None = None

class BatchDispatchItem(BaseModel):
    worker: str
    action: str
    payload: dict[str, Any] = {}

class BatchDispatchRequest(BaseModel):
    items: list[BatchDispatchItem]

class RotateKeyRequest(BaseModel):
    new_key: str

# ── Metrics state ──

class Metrics:
    request_count: int = 0
    dispatch_count: int = 0
    dispatch_errors: int = 0
    dispatch_latency_ms: list[float] = []  # last 100

    @classmethod
    def record_dispatch(cls, latency_ms: float) -> None:
        cls.dispatch_count += 1
        cls.dispatch_latency_ms.append(latency_ms)
        if len(cls.dispatch_latency_ms) > 100:
            cls.dispatch_latency_ms = cls.dispatch_latency_ms[-100:]

    @classmethod
    def record_error(cls) -> None:
        cls.dispatch_errors += 1

    @classmethod
    def snapshot(cls, hermes: Any, scheduler: Any) -> dict[str, Any]:
        latencies = cls.dispatch_latency_ms[-100:]
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies) if latencies else 0
        return {
            "nami_core_requests_total": cls.request_count,
            "nami_core_dispatch_total": cls.dispatch_count,
            "nami_core_dispatch_errors_total": cls.dispatch_errors,
            "nami_core_dispatch_latency_avg_ms": round(avg_lat, 1),
            "nami_core_dispatch_latency_p95_ms": round(p95_lat, 1),
            "nami_core_workers_count": len(hermes.list_workers()) if hermes else 0,
            "nami_core_scheduler_running": scheduler.status().get("running", False) if scheduler else False,
            "nami_core_scheduler_jobs": scheduler.status().get("jobs", 0) if scheduler else 0,
        }

    @classmethod
    def prometheus_text(cls, hermes: Any, scheduler: Any) -> str:
        """Generate Prometheus text format output."""
        s = cls.snapshot(hermes, scheduler)
        lines = []
        for key, value in s.items():
            metric_type = "counter" if "total" in key else "gauge"
            lines.append(f"# TYPE {key} {metric_type}")
            lines.append(f"{key} {value}")
        return "\n".join(lines) + "\n"


# ── WebSocket manager ──

class WSManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self) -> None:
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)
        logger.info("WS client connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._clients:
            self._clients.remove(ws)
        logger.info("WS client disconnected (%d total)", len(self._clients))

    async def broadcast(self, event: str, data: dict[str, Any]) -> None:
        if not self._clients:
            return
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
        to_remove = []
        for client in list(self._clients):
            try:
                await client.send_text(payload)
            except Exception:
                to_remove.append(client)
        for client in to_remove:
            self.disconnect(client)

    def broadcast_sync(self, event: str, data: dict[str, Any]) -> None:
        """Thread-safe broadcast from sync code (scheduler thread)."""
        import asyncio
        if not self._clients:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.broadcast(event, data))
        except RuntimeError:
            pass


# ── Rate limiter (in-memory, per-IP) ──

class RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits.get(key, [])
        hits = [t for t in hits if now - t < self._window]
        hits.append(now)
        self._hits[key] = hits
        return len(hits) <= self._max


# ── App factory ──

def create_app(hermes: Any = None, scheduler: Any = None, api_key: str = "") -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Nami Core API",
        description="Unified agentic system — Hermes brain + Harness control + worker plugins.",
        version="0.11.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS: restrict to nami domains
    allowed_origins = os.environ.get("NAMI_CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ws_manager = WSManager()
    dispatch_limiter = RateLimiter(max_requests=60, window_seconds=60)
    read_limiter = RateLimiter(max_requests=120, window_seconds=60)
    worker_limiters: dict[str, RateLimiter] = {}
    worker_rate_max = int(os.environ.get("NAMI_DISPATCH_RATE_LIMIT", "30"))
    webhook_secret = os.environ.get("NAMI_WEBHOOK_SECRET", "")
    if not webhook_secret:
        webhook_secret = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
        logger.info("Generated NAMI_WEBHOOK_SECRET (set env var to customize)")

    # Store references in app state
    app.state.hermes = hermes
    app.state.scheduler = scheduler
    app.state.api_key = api_key
    app.state.ws_manager = ws_manager

    # ── Request logging middleware ──

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        latency = round((time.monotonic() - t0) * 1000, 1)
        logger.info(
            "REQUEST method=%s path=%s status=%d latency=%s ip=%s",
            request.method, request.url.path, response.status_code, latency,
            request.client.host if request.client else "-",
        )
        return response

    # ── Auth dependency ──

    async def verify_api_key(authorization: str = Header(default="")) -> str:
        if not app.state.api_key:
            return ""  # No auth configured
        key = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        if key != app.state.api_key:
            raise HTTPException(status_code=401, detail="unauthorized")
        return key

    # ── Routes ──

    @app.get("/health")
    async def health(request: Request):
        Metrics.request_count += 1
        return {
            "status": "ok",
            "service": "nami-core",
            "workers": app.state.hermes.list_workers() if app.state.hermes else [],
            "scheduler": app.state.scheduler.status() if app.state.scheduler else {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/workers")
    async def workers(request: Request):
        Metrics.request_count += 1
        ip = request.client.host if request.client else "-"
        if not read_limiter.is_allowed(ip):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        result = []
        if app.state.hermes:
            for name in app.state.hermes.list_workers():
                actions = app.state.hermes.worker_actions(name)
                result.append({"name": name, "actions": sorted(actions)})
        return {"workers": result}

    @app.get("/scheduler")
    async def scheduler_status(request: Request):
        Metrics.request_count += 1
        if app.state.scheduler:
            return app.state.scheduler.status()
        return {"running": False, "jobs": 0}

    @app.get("/metrics", response_model=None)
    async def metrics():
        Metrics.request_count += 1
        return Metrics.snapshot(app.state.hermes, app.state.scheduler)

    @app.get("/metrics/prometheus")
    async def metrics_prometheus():
        """Prometheus text format output."""
        Metrics.request_count += 1
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            Metrics.prometheus_text(app.state.hermes, app.state.scheduler),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.post("/dispatch", response_model=DispatchResponse)
    async def dispatch(req: DispatchRequest, request: Request, _auth: str = Depends(verify_api_key)):
        Metrics.request_count += 1
        ip = request.client.host if request.client else "-"
        if not dispatch_limiter.is_allowed(ip):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        if not req.worker or not req.action:
            raise HTTPException(status_code=400, detail="worker and action required")

        # Per-worker rate limit
        if req.worker not in worker_limiters:
            worker_limiters[req.worker] = RateLimiter(max_requests=worker_rate_max, window_seconds=60)
        if not worker_limiters[req.worker].is_allowed(ip):
            raise HTTPException(status_code=429, detail=f"rate limit exceeded for worker '{req.worker}'")

        try:
            t0 = time.monotonic()
            result = app.state.hermes.dispatch(req.worker, req.action, req.payload)
            latency = (time.monotonic() - t0) * 1000
            Metrics.record_dispatch(latency)
            _audit_log(req.worker, req.action, ip, True, latency)
            await ws_manager.broadcast("dispatch", {"worker": req.worker, "action": req.action, "latency_ms": round(latency, 1)})
            return DispatchResponse(ok=True, output=result.output, latency_ms=round(latency, 1))
        except ValueError as exc:
            Metrics.record_error()
            _audit_log(req.worker, req.action, ip, False, 0)
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            Metrics.record_error()
            _audit_log(req.worker, req.action, ip, False, 0)
            raise HTTPException(status_code=500, detail=str(exc))

    # ── Batch dispatch ──

    @app.post("/dispatch/batch")
    async def dispatch_batch(req: BatchDispatchRequest, request: Request, _auth: str = Depends(verify_api_key)):
        """Dispatch multiple worker actions in one request (max 10)."""
        Metrics.request_count += 1
        if len(req.items) > 10:
            raise HTTPException(status_code=400, detail="batch size limited to 10 items")
        if not req.items:
            raise HTTPException(status_code=400, detail="items cannot be empty")

        ip = request.client.host if request.client else "-"
        results = []
        for item in req.items:
            if not item.worker or not item.action:
                results.append({"worker": item.worker, "action": item.action, "ok": False, "error": "worker and action required", "latency_ms": 0})
                continue
            # Per-worker rate limit
            if item.worker not in worker_limiters:
                worker_limiters[item.worker] = RateLimiter(max_requests=worker_rate_max, window_seconds=60)
            if not worker_limiters[item.worker].is_allowed(ip):
                results.append({"worker": item.worker, "action": item.action, "ok": False, "error": f"rate limit exceeded for worker '{item.worker}'", "latency_ms": 0})
                continue
            try:
                t0 = time.monotonic()
                result = app.state.hermes.dispatch(item.worker, item.action, item.payload)
                latency = (time.monotonic() - t0) * 1000
                Metrics.record_dispatch(latency)
                _audit_log(item.worker, item.action, ip, True, latency)
                await ws_manager.broadcast("dispatch", {"worker": item.worker, "action": item.action, "latency_ms": round(latency, 1)})
                results.append({"worker": item.worker, "action": item.action, "ok": True, "output": result.output, "latency_ms": round(latency, 1)})
            except Exception as exc:
                Metrics.record_error()
                _audit_log(item.worker, item.action, ip, False, 0)
                results.append({"worker": item.worker, "action": item.action, "ok": False, "error": str(exc), "latency_ms": 0})
        return {"results": results}

    # ── Webhook with signing ──

    def _sign_payload(body: bytes) -> str:
        """Sign a payload with HMAC-SHA256 using webhook secret."""
        return hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    @app.post("/webhook")
    async def webhook(req: WebhookRequest):
        Metrics.request_count += 1
        logger.info("Webhook: source=%s event=%s", req.source, req.event)
        raw_body = json.dumps({"source": req.source, "event": req.event, "data": req.data}, ensure_ascii=False, default=str).encode()
        signature = _sign_payload(raw_body)
        await ws_manager.broadcast("webhook", {"source": req.source, "event": req.event, "data": req.data, "signature": f"sha256={signature}"})
        return {"ok": True, "source": req.source, "event": req.event, "signature": f"sha256={signature}"}

    @app.get("/webhook/verify")
    async def webhook_verify():
        """Returns webhook signing instructions and current secret fingerprint."""
        return {
            "algorithm": "HMAC-SHA256",
            "header": "X-Nami-Signature",
            "format": "sha256=<hex>",
            "verify": "HMAC-SHA256(secret, raw_request_body) == signature",
            "secret_fingerprint": hashlib.sha256(webhook_secret.encode()).hexdigest()[:16],
        }

    # ── Worker health check ──

    @app.get("/workers/{name}/health")
    async def worker_health(name: str):
        """Run a worker's health action and return detailed status."""
        Metrics.request_count += 1
        if not app.state.hermes:
            raise HTTPException(status_code=503, detail="no hermes available")
        workers = app.state.hermes.list_workers()
        if name not in workers:
            raise HTTPException(status_code=404, detail=f"worker '{name}' not found")
        actions = app.state.hermes.worker_actions(name)
        health_action = "health" if "health" in actions else "health_check" if "health_check" in actions else None
        if not health_action:
            return {"worker": name, "healthy": None, "message": "no health action defined", "actions": sorted(actions)}
        try:
            t0 = time.monotonic()
            result = app.state.hermes.dispatch(name, health_action, {})
            latency = (time.monotonic() - t0) * 1000
            return {"worker": name, "healthy": True, "response": result.output, "latency_ms": round(latency, 1), "actions": sorted(actions)}
        except Exception as exc:
            return {"worker": name, "healthy": False, "error": str(exc), "latency_ms": 0, "actions": sorted(actions)}

    # ── SSE streaming ──

    @app.get("/events")
    async def sse_events(request: Request, test: bool = False):
        """Server-Sent Events stream for real-time updates."""
        from starlette.responses import StreamingResponse

        async def event_generator():
            # Send initial connection event
            yield f"event: connected\ndata: {{\"status\": \"ok\"}}\n\n"
            if test:
                return
            # Keep connection alive with heartbeat
            last_id = request.headers.get("Last-Event-ID", "0")
            event_id = int(last_id)
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                event_id += 1
                # Heartbeat every 15 seconds
                await asyncio.sleep(15)
                yield f": heartbeat\n\nevent: ping\nid: {event_id}\ndata: {{\"ts\": \"{datetime.now(timezone.utc).isoformat()}\"}}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/rotate-key")
    async def rotate_key(req: RotateKeyRequest, _auth: str = Depends(verify_api_key)):
        """Rotate the API key. Requires current key auth."""
        if not req.new_key or len(req.new_key) < 8:
            raise HTTPException(status_code=400, detail="new_key must be at least 8 characters")
        app.state.api_key = req.new_key
        logger.info("API key rotated")
        return {"ok": True, "message": "API key rotated successfully"}

    @app.get("/audit")
    async def audit_trail(limit: int = 50):
        """Get recent audit log entries (public read for dashboard)."""
        try:
            conn = sqlite3.connect(AUDIT_DB)
            cur = conn.execute(
                "SELECT worker, action, caller_ip, ok, latency_ms, timestamp FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = [{"worker": r[0], "action": r[1], "caller_ip": r[2], "ok": bool(r[3]), "latency_ms": r[4], "timestamp": r[5]} for r in cur.fetchall()]
            conn.close()
            return {"entries": rows}
        except Exception:
            return {"entries": []}

    @app.get("/cache")
    async def cache_stats(_auth: str = Depends(verify_api_key)):
        """Get cache statistics."""
        from nami_core.cache import stats as cache_stats_fn
        return cache_stats_fn()

    @app.get("/db")
    async def db_stats(_auth: str = Depends(verify_api_key)):
        """Get database pool statistics."""
        from nami_core.db import sqlite_stats
        return sqlite_stats()

    @app.post("/cache/flush")
    async def cache_flush(_auth: str = Depends(verify_api_key)):
        """Flush all cached entries."""
        from nami_core.cache import flush as cache_flush_fn
        cache_flush_fn()
        return {"ok": True, "message": "cache flushed"}

    @app.post("/restart")
    async def graceful_restart(_auth: str = Depends(verify_api_key)):
        """Graceful restart: drain connections and restart."""
        import signal
        logger.info("Graceful restart requested")
        # Schedule restart after a short delay to allow response to be sent
        import threading
        def _restart():
            import time
            time.sleep(1)
            os.kill(os.getpid(), signal.SIGTERM)
        threading.Thread(target=_restart, daemon=True).start()
        return {"ok": True, "message": "restart scheduled in 1s"}

    @app.post("/reload-workers")
    async def reload_workers(_auth: str = Depends(verify_api_key)):
        """Hot-reload workers from config directory."""
        if not app.state.hermes:
            raise HTTPException(status_code=400, detail="no hermes available")
        try:
            from nami_core.scheduler import build_core
            hermes, _ = build_core()
            app.state.hermes = hermes
            workers = hermes.list_workers()
            logger.info("Workers hot-reloaded: %d workers", len(workers))
            return {"ok": True, "workers": len(workers)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/workers/{name}/rate-limit")
    async def worker_rate_limit(name: str, _auth: str = Depends(verify_api_key)):
        """Get rate limit status for a specific worker."""
        limiter = worker_limiters.get(name)
        return {
            "worker": name,
            "max_requests": worker_rate_max,
            "window_seconds": 60,
            "active": limiter is not None,
            "current_hits": len(limiter._hits) if limiter else 0,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    # Expose ws_manager for scheduler to broadcast from sync code
    app.state.ws_broadcast = ws_manager.broadcast_sync

    return app
