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
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse, parse_qs

from nami_core.hermes import Hermes
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
        except Exception as exc:
            logger.warning("Scheduled job %s: ERROR — %s", desc, exc)

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

    def do_GET(self) -> None:
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
                result = self.hermes.dispatch(worker, action, payload)
                self._json(200, {"ok": True, "output": result.output})
            except ValueError as exc:
                self._json(404, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
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
    NamiAPIHandler.api_key = os.environ.get("NAMI_API_KEY", "")

    # Start HTTP server
    server = HTTPServer((host, port), NamiAPIHandler)
    logger.info("API server listening on %s:%d", host, port)

    # Graceful shutdown
    def _shutdown(signum: int, frame: Any) -> None:
        logger.info("Shutting down...")
        scheduler.stop()
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
