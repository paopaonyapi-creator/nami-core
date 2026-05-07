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

from nami_core.mcp_client import McpClientError, McpClientManager
from nami_core.mcp_config import McpConfig, load_mcp_config
from nami_core.runtime_v2 import (
    ExecutionPolicy,
    RuntimeEvent,
    RuntimeJobStore,
    ToolRegistry,
    build_mutating_tool_diagnostics,
    capture_git_worktree_snapshot,
    recovery_git_diff_preview,
    restore_git_worktree_files,
    run_runtime_diagnostics,
)

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
    approved: bool = False

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

class McpToolInvokeRequest(BaseModel):
    tool: str
    payload: dict[str, Any] = {}
    approved: bool = False
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
        version="0.13.0",
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
    app.state.tool_registry = ToolRegistry.from_hermes(hermes)
    app.state.runtime_jobs = RuntimeJobStore(os.environ.get("NAMI_RUNTIME_JOBS_FILE") or None)
    app.state.runtime_events = []
    mcp_config_file = os.environ.get("NAMI_MCP_CONFIG_FILE")
    app.state.mcp_config = load_mcp_config(mcp_config_file) if mcp_config_file else McpConfig()
    app.state.mcp_client = McpClientManager(app.state.mcp_config)

    @app.on_event("shutdown")
    async def shutdown_mcp_client():
        await app.state.mcp_client.close()

    def record_runtime_event(event: RuntimeEvent) -> None:
        app.state.runtime_events.append(event)
        if len(app.state.runtime_events) > 500:
            app.state.runtime_events = app.state.runtime_events[-500:]
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

    @app.get("/runtime/health")
    async def runtime_health(request: Request):
        Metrics.request_count += 1
        return {
            "status": "ok",
            "service": "nami-runtime-v2",
            "core_status": "ok",
            "workers": app.state.hermes.list_workers() if app.state.hermes else [],
            "tools": len(app.state.tool_registry.list()),
            "jobs": len(app.state.runtime_jobs.list()),
            "scheduler": app.state.scheduler.status() if app.state.scheduler else {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/runtime/tools")
    async def runtime_tools(request: Request):
        Metrics.request_count += 1
        ip = request.client.host if request.client else "-"
        if not read_limiter.is_allowed(ip):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        await app.state.mcp_client.discover()
        registry_tools = [tool.to_dict() for tool in app.state.tool_registry.list()]
        mcp_tools = [tool.to_metadata().to_dict() for tool in app.state.mcp_client.tools()]
        tools = sorted([*registry_tools, *mcp_tools], key=lambda tool: tool["name"])
        return {"tools": tools}

    @app.get("/runtime/mcp/servers")
    async def runtime_mcp_servers(request: Request):
        Metrics.request_count += 1
        ip = request.client.host if request.client else "-"
        if not read_limiter.is_allowed(ip):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        servers = app.state.mcp_config.servers
        enabled = app.state.mcp_config.enabled_servers()
        return {
            "servers": [server.to_dict() for server in servers],
            "enabled": [server.name for server in enabled],
            "count": len(servers),
            "enabled_count": len(enabled),
        }

    @app.post("/runtime/mcp/servers/{server_name}/reconnect")
    async def runtime_mcp_server_reconnect(server_name: str, request: Request, authorization: str = Header(default="")):
        Metrics.request_count += 1
        authenticated = False
        if app.state.api_key:
            key = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
            authenticated = key == app.state.api_key
        if app.state.api_key and not authenticated:
            raise HTTPException(status_code=401, detail="api key required")
        try:
            server = await app.state.mcp_client.reconnect(server_name)
            return {"ok": True, "server": server.to_dict()}
        except McpClientError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/runtime/mcp/tools")
    async def runtime_mcp_tools(request: Request):
        Metrics.request_count += 1
        ip = request.client.host if request.client else "-"
        if not read_limiter.is_allowed(ip):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        await app.state.mcp_client.discover()
        servers = [server.to_dict() for server in app.state.mcp_client.servers()]
        tools = [tool.to_dict() for tool in app.state.mcp_client.tools()]
        connected = any(server["status"] == "connected" for server in servers)
        errored = any(server["status"] == "error" for server in servers)
        return {
            "servers": servers,
            "tools": tools,
            "tool_count": len(tools),
            "discovery_status": "connected" if connected else "error" if errored else "not_connected",
        }

    @app.post("/runtime/mcp/tools/invoke")
    async def runtime_mcp_tool_invoke(req: McpToolInvokeRequest, request: Request, authorization: str = Header(default="")):
        Metrics.request_count += 1
        await app.state.mcp_client.discover()
        tool = app.state.mcp_client.get_tool(req.tool)
        if tool is None:
            raise HTTPException(status_code=404, detail=f"MCP tool not registered: {req.tool}")
        metadata = tool.to_metadata()
        authenticated = False
        if app.state.api_key:
            key = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
            authenticated = key == app.state.api_key
        decision = ExecutionPolicy.decide(metadata, authenticated)
        if decision == "require_api_key":
            raise HTTPException(status_code=401, detail="api key required")
        if decision == "require_approval":
            if not authenticated or not req.approved:
                raise HTTPException(status_code=403, detail="approval required")
        if decision == "deny":
            raise HTTPException(status_code=403, detail="tool denied by policy")
        job = app.state.runtime_jobs.create(req.tool, json.dumps(req.payload, ensure_ascii=False, default=str)[:240])
        job.status = "running"
        job.updated_at = datetime.now(timezone.utc).isoformat()
        started = RuntimeEvent(type="tool.started", job_id=job.id, data={"tool": req.tool, "server": tool.server})
        job.progress_events.append(started)
        job.audit_entries.append({"event": "tool.started", "worker": "mcp", "action": req.tool, "ok": None, "timestamp": started.timestamp})
        app.state.runtime_jobs.save(job)
        record_runtime_event(started)
        try:
            t0 = time.monotonic()
            output = await app.state.mcp_client.call_tool(req.tool, req.payload)
            latency = (time.monotonic() - t0) * 1000
            Metrics.record_dispatch(latency)
            _audit_log("mcp", req.tool, request.client.host if request.client else "-", True, latency)
            job.status = "completed"
            job.updated_at = datetime.now(timezone.utc).isoformat()
            job.result = {"ok": True, "output": output, "latency_ms": round(latency, 1)}
            completed = RuntimeEvent(type="job.completed", job_id=job.id, data=job.result)
            job.progress_events.append(RuntimeEvent(type="tool.completed", job_id=job.id, data=job.result))
            job.audit_entries.append({"event": "tool.completed", "worker": "mcp", "action": req.tool, "ok": True, "latency_ms": round(latency, 1), "timestamp": completed.timestamp})
            app.state.runtime_jobs.save(job)
            record_runtime_event(completed)
            await ws_manager.broadcast("runtime.event", completed.to_dict())
            return {"ok": True, "job": job.to_dict(), "output": output, "latency_ms": round(latency, 1)}
        except McpClientError as exc:
            Metrics.record_error()
            _audit_log("mcp", req.tool, request.client.host if request.client else "-", False, 0)
            job.status = "failed"
            job.updated_at = datetime.now(timezone.utc).isoformat()
            job.error = str(exc)
            failed = RuntimeEvent(type="job.failed", job_id=job.id, data={"error": str(exc)})
            job.progress_events.append(RuntimeEvent(type="tool.failed", job_id=job.id, data={"error": str(exc)}))
            job.audit_entries.append({"event": "tool.failed", "worker": "mcp", "action": req.tool, "ok": False, "error": str(exc), "timestamp": failed.timestamp})
            app.state.runtime_jobs.save(job)
            record_runtime_event(failed)
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/runtime/tools/invoke")
    async def runtime_tool_invoke(req: DispatchRequest, request: Request, authorization: str = Header(default="")):
        Metrics.request_count += 1
        tool_name = f"{req.worker}.{req.action}"
        tool = app.state.tool_registry.get(tool_name)
        if tool is None:
            raise HTTPException(status_code=404, detail=f"tool not registered: {tool_name}")
        authenticated = False
        if app.state.api_key:
            key = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
            authenticated = key == app.state.api_key
        decision = ExecutionPolicy.decide(tool, authenticated)
        if decision == "require_api_key":
            raise HTTPException(status_code=401, detail="api key required")
        if decision == "require_approval":
            if not authenticated or not req.approved:
                raise HTTPException(status_code=403, detail="approval required")
        if decision == "deny":
            raise HTTPException(status_code=403, detail="tool denied by policy")
        job = app.state.runtime_jobs.create(tool_name, json.dumps(req.payload, ensure_ascii=False, default=str)[:240])
        job.status = "running"
        job.updated_at = datetime.now(timezone.utc).isoformat()
        started = RuntimeEvent(type="tool.started", job_id=job.id, data={"tool": tool_name})
        job.progress_events.append(started)
        job.audit_entries.append({"event": "tool.started", "worker": req.worker, "action": req.action, "ok": None, "timestamp": started.timestamp})
        app.state.runtime_jobs.save(job)
        record_runtime_event(started)
        try:
            snapshot_before = capture_git_worktree_snapshot() if tool.permission_level == "mutating" else None
            t0 = time.monotonic()
            result = app.state.hermes.dispatch(req.worker, req.action, req.payload)
            latency = (time.monotonic() - t0) * 1000
            snapshot_after = capture_git_worktree_snapshot() if snapshot_before is not None else None
            diagnostic_checks = run_runtime_diagnostics() if snapshot_before is not None else None
            diagnostics = build_mutating_tool_diagnostics(snapshot_before, snapshot_after, diagnostic_checks) if snapshot_before is not None and snapshot_after is not None else None
            Metrics.record_dispatch(latency)
            _audit_log(req.worker, req.action, request.client.host if request.client else "-", True, latency)
            job.status = "completed"
            job.updated_at = datetime.now(timezone.utc).isoformat()
            job.result = {"ok": True, "output": result.output, "latency_ms": round(latency, 1)}
            if snapshot_before is not None and snapshot_after is not None and diagnostics is not None:
                job.result["snapshot"] = {"before": snapshot_before, "after": snapshot_after}
                job.result["diagnostics"] = diagnostics
            completed = RuntimeEvent(type="job.completed", job_id=job.id, data=job.result)
            job.progress_events.append(RuntimeEvent(type="tool.completed", job_id=job.id, data=job.result))
            completed_audit = {"event": "tool.completed", "worker": req.worker, "action": req.action, "ok": True, "latency_ms": round(latency, 1), "timestamp": completed.timestamp}
            if diagnostics is not None:
                completed_audit["diagnostics"] = diagnostics
            job.audit_entries.append(completed_audit)
            app.state.runtime_jobs.save(job)
            record_runtime_event(completed)
            await ws_manager.broadcast("runtime.event", completed.to_dict())
            return {"ok": True, "job": job.to_dict(), "output": result.output, "latency_ms": round(latency, 1)}
        except ValueError as exc:
            Metrics.record_error()
            _audit_log(req.worker, req.action, request.client.host if request.client else "-", False, 0)
            job.status = "failed"
            job.updated_at = datetime.now(timezone.utc).isoformat()
            job.error = str(exc)
            failed = RuntimeEvent(type="job.failed", job_id=job.id, data={"error": str(exc)})
            job.progress_events.append(RuntimeEvent(type="tool.failed", job_id=job.id, data={"error": str(exc)}))
            job.audit_entries.append({"event": "tool.failed", "worker": req.worker, "action": req.action, "ok": False, "error": str(exc), "timestamp": failed.timestamp})
            app.state.runtime_jobs.save(job)
            record_runtime_event(failed)
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            Metrics.record_error()
            _audit_log(req.worker, req.action, request.client.host if request.client else "-", False, 0)
            job.status = "failed"
            job.updated_at = datetime.now(timezone.utc).isoformat()
            job.error = str(exc)
            failed = RuntimeEvent(type="job.failed", job_id=job.id, data={"error": str(exc)})
            job.progress_events.append(RuntimeEvent(type="tool.failed", job_id=job.id, data={"error": str(exc)}))
            job.audit_entries.append({"event": "tool.failed", "worker": req.worker, "action": req.action, "ok": False, "error": str(exc), "timestamp": failed.timestamp})
            app.state.runtime_jobs.save(job)
            record_runtime_event(failed)
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/runtime/jobs")
    async def runtime_jobs(request: Request):
        Metrics.request_count += 1
        return {"jobs": [job.to_dict() for job in app.state.runtime_jobs.list()]}

    @app.get("/runtime/jobs/{job_id}")
    async def runtime_job_detail(job_id: str):
        Metrics.request_count += 1
        job = app.state.runtime_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        return job.to_dict()

    @app.get("/runtime/jobs/{job_id}/recovery/preview")
    async def runtime_job_recovery_preview(job_id: str):
        Metrics.request_count += 1
        job = app.state.runtime_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        diagnostics = (job.result or {}).get("diagnostics") or {}
        recovery = diagnostics.get("recovery") or {}
        candidate_files = recovery.get("candidate_files") or []
        return {
            "job_id": job.id,
            "requested_action": job.requested_action,
            "manual_review_required": bool(recovery.get("manual_review_required")),
            "candidate_files": candidate_files,
            "new_candidate_files": recovery.get("new_candidate_files") or [],
            "suggested_commands": recovery.get("suggested_commands") or [],
            "restore_supported": bool(candidate_files),
        }

    @app.get("/runtime/jobs/{job_id}/recovery/diff")
    async def runtime_job_recovery_diff(job_id: str):
        Metrics.request_count += 1
        job = app.state.runtime_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        diagnostics = (job.result or {}).get("diagnostics") or {}
        recovery = diagnostics.get("recovery") or {}
        candidate_files = recovery.get("candidate_files") or []
        if not candidate_files:
            raise HTTPException(status_code=409, detail="no recovery candidate files")
        return {"job_id": job.id, "requested_action": job.requested_action, **recovery_git_diff_preview(candidate_files)}

    @app.post("/runtime/jobs/{job_id}/recovery/restore")
    async def runtime_job_recovery_restore(job_id: str, authorization: str = Header(default="")):
        Metrics.request_count += 1
        if not app.state.api_key:
            raise HTTPException(status_code=403, detail="restore requires api key configuration")
        key = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        if not hmac.compare_digest(key, app.state.api_key):
            raise HTTPException(status_code=401, detail="api key required")
        job = app.state.runtime_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        diagnostics = (job.result or {}).get("diagnostics") or {}
        recovery = diagnostics.get("recovery") or {}
        candidate_files = recovery.get("candidate_files") or []
        if not candidate_files:
            raise HTTPException(status_code=409, detail="no recovery candidate files")
        current_snapshot = capture_git_worktree_snapshot()
        current_changed = set(current_snapshot.get("changed_files") or [])
        missing_candidates = [path for path in candidate_files if path not in current_changed]
        if missing_candidates:
            raise HTTPException(status_code=409, detail={"error": "recovery candidates no longer match worktree", "missing_candidate_files": missing_candidates})
        result = restore_git_worktree_files(candidate_files)
        event = RuntimeEvent(type="job.recovery_restored" if result.get("ok") else "job.recovery_failed", job_id=job.id, data=result)
        job.progress_events.append(event)
        job.audit_entries.append({"event": event.type, "worker": "runtime", "action": "recovery.restore", "ok": result.get("ok"), "timestamp": event.timestamp, "result": result})
        app.state.runtime_jobs.save(job)
        record_runtime_event(event)
        await ws_manager.broadcast("runtime.event", event.to_dict())
        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result)
        return {"ok": True, "job_id": job.id, **result}

    @app.get("/runtime/events")
    async def runtime_events(request: Request, test: bool = False):
        from starlette.responses import StreamingResponse

        async def event_generator():
            ready = RuntimeEvent(type="runtime.ready", data={"tools": len(app.state.tool_registry.list())})
            yield f"event: {ready.type}\ndata: {json.dumps(ready.to_dict(), ensure_ascii=False, default=str)}\n\n"
            sent = 0
            while sent < len(app.state.runtime_events):
                event = app.state.runtime_events[sent]
                sent += 1
                yield f"event: {event.type}\nid: {sent}\ndata: {json.dumps(event.to_dict(), ensure_ascii=False, default=str)}\n\n"
            if test:
                return
            while True:
                if await request.is_disconnected():
                    break
                while sent < len(app.state.runtime_events):
                    event = app.state.runtime_events[sent]
                    sent += 1
                    yield f"event: {event.type}\nid: {sent}\ndata: {json.dumps(event.to_dict(), ensure_ascii=False, default=str)}\n\n"
                await asyncio.sleep(15)
                ping = RuntimeEvent(type="runtime.ready", data={"event_id": sent})
                yield f": heartbeat\n\nevent: {ping.type}\nid: {sent}\ndata: {json.dumps(ping.to_dict(), ensure_ascii=False, default=str)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
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
