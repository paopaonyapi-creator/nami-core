"""Nami Core Scheduler — periodic job runner and HTTP API server.

Runs as a long-lived daemon that:
  1. Serves an HTTP API on port 8092 for worker dispatch
  2. Runs scheduled jobs (lottery predict, signal generate, etc.)
  3. Reports health via /health endpoint
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse, parse_qs

from nami_core.hermes import Hermes
from nami_core import ws as nami_ws
from nami_workers.registry import WorkerRegistry

logger = logging.getLogger("nami_core.scheduler")

# ── Schedule definitions ──
# Each job: worker, action, payload, interval_seconds, description
SCHEDULES: list[dict[str, Any]] = [
    {
        "worker": "status",
        "action": "health",
        "payload": {},
        "interval": 300,
        "description": "Health check every 5min",
    },
    {
        "worker": "lottery",
        "action": "fetch_results",
        "payload": {"region": "lao"},
        "interval": 14400,
        "offset": 300,
        "description": "Lao draw results every 4h (offset 5min)",
    },
    {
        "worker": "lottery",
        "action": "vip",
        "payload": {"region": "lao", "send": True},
        "interval": 86400,
        "hour": 18,
        "description": "VIP lottery send daily at 18:00",
    },
    {
        "worker": "signal",
        "action": "generate_signal",
        "payload": {},
        "interval": 1800,
        "description": "Signal generation every 30min",
    },
    {
        "worker": "gold",
        "action": "prices",
        "payload": {},
        "interval": 300,
        "offset": 60,
        "description": "Gold prices check every 5min",
    },
    {
        "worker": "miroshark",
        "action": "status",
        "payload": {},
        "interval": 600,
        "offset": 30,
        "description": "MiroShark Oracle health every 10min",
    },
]


class NamiScheduler:
    """Periodic job scheduler for nami-core workers."""

    def __init__(self, hermes: Hermes) -> None:
        self.hermes = hermes
        self._running = False
        self._last_run: dict[str, float] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        self._running = True
        logger.info("Scheduler started with %d jobs", len(SCHEDULES))
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            now = time.time()
            now_hour = datetime.now(timezone.utc).hour

            for job in SCHEDULES:
                key = f"{job['worker']}:{job['action']}"
                interval = job.get("interval", 3600)
                offset = job.get("offset", 0)
                hour = job.get("hour")

                last = self._last_run.get(key, 0)

                # Hour-based jobs: run only at specified hour
                if hour is not None:
                    if now_hour != hour:
                        continue
                    # Already ran this hour?
                    last_dt = datetime.fromtimestamp(last, tz=timezone.utc)
                    if last_dt.hour == hour and (now - last) < 3600:
                        continue

                # Interval-based jobs
                if now - last >= interval + offset:
                    self._run_job(job, key)
                    self._last_run[key] = now

            time.sleep(60)  # Check every minute

    def _run_job(self, job: dict[str, Any], key: str) -> None:
        worker = job["worker"]
        action = job["action"]
        payload = job.get("payload", {})
        desc = job.get("description", key)

        try:
            result = self.hermes.dispatch(worker, action, payload)
            logger.info("Scheduled job %s: OK — %s", desc, str(result.output)[:200])
            nami_ws.broadcast("scheduler", {"job": key, "worker": worker, "action": action, "status": "ok"})
        except Exception as exc:
            logger.warning("Scheduled job %s: ERROR — %s", desc, exc)
            nami_ws.broadcast("scheduler", {"job": key, "worker": worker, "action": action, "status": "error", "error": str(exc)})

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "jobs": len(SCHEDULES),
                "last_runs": {
                    k: datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
                    for k, v in self._last_run.items()
                },
            }


class NamiAPIHandler(BaseHTTPRequestHandler):
    """HTTP API handler for nami-core."""

    hermes: Hermes = None  # type: ignore
    scheduler: NamiScheduler = None  # type: ignore
    api_key: str = ""  # type: ignore
    # Metrics counters
    _request_count: int = 0
    _dispatch_count: int = 0
    _dispatch_errors: int = 0
    _dispatch_latency_ms: list[float] = []  # last 100

    def do_GET(self) -> None:
        NamiAPIHandler._request_count += 1
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/health":
            self._json(200, {
                "status": "ok",
                "service": "nami-core",
                "workers": self.hermes.list_workers(),
                "scheduler": self.scheduler.status(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif path == "/workers":
            workers = []
            for name in self.hermes.list_workers():
                actions = self.hermes.worker_actions(name)
                workers.append({"name": name, "actions": sorted(actions)})
            self._json(200, {"workers": workers})
        elif path == "/scheduler":
            self._json(200, self.scheduler.status())
        elif path == "/metrics":
            self._json(200, self._prometheus_metrics())
        else:
            self._json(404, {"error": f"not found: {path}"})

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/dispatch":
            # API key auth for dispatch (skip if no key configured)
            if self.api_key:
                auth = self.headers.get("Authorization", "")
                key = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else auth
                if key != self.api_key:
                    self._json(401, {"error": "unauthorized"})
                    return

            body = self._read_body()
            if body is None:
                return

            worker = body.get("worker", "")
            action = body.get("action", "")
            payload = body.get("payload", {})

            if not worker or not action:
                self._json(400, {"error": "worker and action required"})
                return

            try:
                t0 = time.monotonic()
                result = self.hermes.dispatch(worker, action, payload)
                latency = (time.monotonic() - t0) * 1000
                NamiAPIHandler._dispatch_count += 1
                NamiAPIHandler._dispatch_latency_ms.append(latency)
                if len(NamiAPIHandler._dispatch_latency_ms) > 100:
                    NamiAPIHandler._dispatch_latency_ms = NamiAPIHandler._dispatch_latency_ms[-100:]
                self._json(200, {"ok": True, "output": result.output, "latency_ms": round(latency, 1)})
                nami_ws.broadcast("dispatch", {"worker": worker, "action": action, "latency_ms": round(latency, 1)})
            except ValueError as exc:
                NamiAPIHandler._dispatch_errors += 1
                self._json(404, {"error": str(exc)})
            except Exception as exc:
                NamiAPIHandler._dispatch_errors += 1
                self._json(500, {"error": str(exc)})
        elif path == "/webhook":
            body = self._read_body()
            if body is None:
                return
            source = body.get("source", "unknown")
            event = body.get("event", "ping")
            data = body.get("data", {})
            logger.info("Webhook: source=%s event=%s", source, event)
            nami_ws.broadcast("webhook", {"source": source, "event": event, "data": data})
            self._json(200, {"ok": True, "source": source, "event": event})
        else:
            self._json(404, {"error": f"not found: {path}"})

    def _read_body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            data = self.rfile.read(length)
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(400, {"error": f"invalid JSON: {exc}"})
            return None

    def _json(self, code: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("API: %s", format % args)

    @classmethod
    def _prometheus_metrics(cls) -> dict[str, Any]:
        latencies = cls._dispatch_latency_ms[-100:]
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies) if latencies else 0
        return {
            "nami_core_requests_total": cls._request_count,
            "nami_core_dispatch_total": cls._dispatch_count,
            "nami_core_dispatch_errors_total": cls._dispatch_errors,
            "nami_core_dispatch_latency_avg_ms": round(avg_lat, 1),
            "nami_core_dispatch_latency_p95_ms": round(p95_lat, 1),
            "nami_core_workers_count": len(cls.hermes.list_workers()),
            "nami_core_scheduler_running": cls.scheduler.status().get("running", False),
            "nami_core_scheduler_jobs": cls.scheduler.status().get("jobs", 0),
        }


def run_server(host: str = "127.0.0.1", port: int = 8092) -> None:
    """Start the nami-core daemon: API server + scheduler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Build Hermes + workers
    hermes = Hermes()
    registry = WorkerRegistry()
    config_dir = os.environ.get("NAMI_CONFIG_DIR", "config")

    # Import all workers and register them
    from nami_workers.lottery_worker import lottery_worker
    from nami_workers.signal_worker import signal_worker
    from nami_workers.status_worker import status_worker
    from nami_workers.proxy_worker import proxy_worker
    from nami_workers.trading_worker import trading_worker
    from nami_workers.gateway_worker import gateway_worker
    from nami_workers.bridge_worker import bridge_worker
    from nami_workers.graphify_worker import graphify_worker
    from nami_workers.bot_worker import bot_worker
    from nami_workers.miroshark_worker import miroshark_worker
    from nami_workers.gold_worker import gold_worker

    registry.register("lottery", lottery_worker)
    registry.register("signal", signal_worker)
    registry.register("status", status_worker)
    registry.register("proxy", proxy_worker)
    registry.register("trading", trading_worker)
    registry.register("gateway", gateway_worker)
    registry.register("bridge", bridge_worker)
    registry.register("graphify", graphify_worker)
    registry.register("bot", bot_worker)
    registry.register("miroshark", miroshark_worker)
    registry.register("gold", gold_worker)

    # Load harness configs
    registry.load_from_directory(config_dir)
    registry.wire_into_hermes(hermes)

    workers = hermes.list_workers()
    logger.info("Nami Core started — %d workers: %s", len(workers), ", ".join(workers))

    # Start scheduler
    scheduler = NamiScheduler(hermes)
    scheduler.start()

    # Wire handler references
    NamiAPIHandler.hermes = hermes
    NamiAPIHandler.scheduler = scheduler
    # Read API key: if env var points to a file, read it; otherwise use as-is
    api_key_raw = os.environ.get("NAMI_API_KEY", "")
    if api_key_raw and os.path.isfile(api_key_raw):
        try:
            with open(api_key_raw) as f:
                api_key = f.read().strip()
        except (OSError, PermissionError):
            api_key = api_key_raw
    else:
        api_key = api_key_raw
    NamiAPIHandler.api_key = api_key

    # Start WebSocket server
    ws_port = int(os.environ.get("NAMI_WS_PORT", "8093"))
    nami_ws.start_ws_server(host, ws_port)

    # Start HTTP server
    server = HTTPServer((host, port), NamiAPIHandler)
    logger.info("API server listening on %s:%d", host, port)

    # Graceful shutdown
    def _shutdown(signum: int, frame: Any) -> None:
        logger.info("Shutting down...")
        scheduler.stop()
        nami_ws.stop_ws_server()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _shutdown(0, None)


if __name__ == "__main__":
    run_server()
