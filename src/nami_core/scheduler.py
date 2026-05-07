"""Nami Core Scheduler — periodic job runner and FastAPI server.

Runs as a long-lived daemon that:
  1. Serves a FastAPI HTTP+WS API on port 8092
  2. Runs scheduled jobs (lottery predict, signal generate, etc.)
  3. Reports health via /health endpoint
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
import threading
from datetime import datetime, timezone
from typing import Any

from nami_core.hermes import Hermes
from nami_core.app import create_app, Metrics
from nami_workers.registry import WorkerRegistry
from nami_workers.scheduler_worker import set_scheduler_ref
from nami_workers.cron_worker import set_hermes_ref, start_cron_checker

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

    def __init__(self, hermes: Hermes, ws_broadcast=None) -> None:
        self.hermes = hermes
        self._running = False
        self._last_run: dict[str, float] = {}
        self._lock = threading.Lock()
        self._ws_broadcast = ws_broadcast

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
            if self._ws_broadcast:
                self._ws_broadcast("scheduler", {"job": key, "worker": worker, "action": action, "status": "ok"})
        except Exception as exc:
            logger.warning("Scheduled job %s: ERROR — %s", desc, exc)
            if self._ws_broadcast:
                self._ws_broadcast("scheduler", {"job": key, "worker": worker, "action": action, "status": "error", "error": str(exc)})

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


def build_core(config_dir: str | None = None) -> tuple:
    """Build Hermes + workers + registry. Returns (hermes, None)."""
    hermes = Hermes()
    registry = WorkerRegistry()
    cdir = config_dir or os.environ.get("NAMI_CONFIG_DIR", "config")

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
    from nami_workers.notification_worker import notification_worker
    from nami_workers.analytics_worker import analytics_worker
    from nami_workers.scheduler_worker import scheduler_worker
    from nami_workers.cron_worker import cron_worker
    from nami_workers.email_worker import email_worker
    from nami_workers.relay_worker import relay_worker
    from nami_workers.pipeline_worker import pipeline_worker
    from nami_workers.ai_chat_worker import ai_chat_worker
    from nami_workers.sentiment_worker import sentiment_worker
    from nami_workers.search_worker import search_worker
    from nami_workers.image_worker import image_worker
    from nami_workers.clipboardbypao_worker import clipboardbypao_worker
    from nami_workers.hanoi_stats_worker import hanoi_stats_worker
    from nami_workers.laopatana_lab_worker import laopatana_lab_worker
    from nami_workers.miroshark_oracle_worker import miroshark_oracle_worker
    from nami_workers.open_design_worker import open_design_worker

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
    registry.register("notification", notification_worker)
    registry.register("scheduler", scheduler_worker)
    registry.register("cron", cron_worker)
    registry.register("email", email_worker)
    registry.register("relay", relay_worker)
    registry.register("pipeline", pipeline_worker)
    registry.register("ai_chat", ai_chat_worker)
    registry.register("sentiment", sentiment_worker)
    registry.register("search", search_worker)
    registry.register("image", image_worker)
    registry.register("clipboardbypao", clipboardbypao_worker)
    registry.register("hanoi_stats", hanoi_stats_worker)
    registry.register("laopatana_lab", laopatana_lab_worker)
    registry.register("miroshark_oracle", miroshark_oracle_worker)
    registry.register("open_design", open_design_worker)

    registry.load_from_directory(cdir)
    registry.wire_into_hermes(hermes)

    set_hermes_ref(hermes)
    return hermes, None


def run_server(host: str = "127.0.0.1", port: int = 8092) -> None:
    """Start the nami-core daemon: FastAPI server + scheduler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Build Hermes + workers
    hermes, _ = build_core()

    workers = hermes.list_workers()
    logger.info("Nami Core started — %d workers: %s", len(workers), ", ".join(workers))

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

    # Create FastAPI app
    app = create_app(hermes=hermes, scheduler=None, api_key=api_key)

    # Start scheduler (with WS broadcast reference)
    scheduler = NamiScheduler(hermes, ws_broadcast=app.state.ws_broadcast)
    scheduler.start()
    app.state.scheduler = scheduler

    # Set worker refs
    set_scheduler_ref(scheduler)
    set_hermes_ref(hermes)
    start_cron_checker()

    # Start uvicorn
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="info", ws_ping_interval=30, ws_ping_timeout=10)
    server = uvicorn.Server(config)

    logger.info("API server listening on %s:%d", host, port)

    # Graceful shutdown
    def _shutdown(signum: int, frame: Any) -> None:
        logger.info("Shutting down...")
        scheduler.stop()
        server.should_exit = True
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.run()
    except KeyboardInterrupt:
        _shutdown(0, None)


if __name__ == "__main__":
    run_server()
