"""Redis Streams consumer worker for async job execution."""

from __future__ import annotations

import asyncio
import argparse
import importlib
import json
import logging
import os
import signal
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from nami_core.hermes import Hermes
from nami_core.runtime.obs import configure_otel, cost_span
from nami_core.runtime.queue.jobs_dao import JobsDAO
from nami_core.runtime.queue.redis_stream import RedisStream
from nami_core.runtime.queue.types import JobMessage, TaskInput, TaskOutput
from nami_workers.registry import WorkerRegistry

logger = logging.getLogger("nami_core.runtime.queue.worker")

MAX_CONCURRENCY = int(os.environ.get("NAMI_WORKER_CONCURRENCY", "4"))
WORKER_HEARTBEAT_SEC = int(os.environ.get("NAMI_WORKER_HEARTBEAT_SEC", "30"))


def _parse_action(action: str) -> tuple[str, str]:
    if "." not in action:
        raise ValueError(f"invalid action format: {action}")
    worker, action_name = action.split(".", 1)
    return worker, action_name


def _traceparent_from_trace_id(trace_id: str) -> str:
    if trace_id and trace_id.startswith("00-"):
        return trace_id
    if trace_id and len(trace_id) == 55 and trace_id.startswith("00-"):
        return trace_id
    rand = os.urandom(8).hex()
    trace = trace_id if trace_id else os.urandom(16).hex()
    return f"00-{trace}-{rand}-01"


def _build_task_payload(message: JobMessage) -> dict[str, Any]:
    task_input = TaskInput(
        job_id=message.id,
        action=message.action,
        payload=message.payload,
        trace_id=_traceparent_from_trace_id(message.trace_id),
        parent_id=message.parent_id,
        budget=message.budget,
        attempt=message.attempt,
    )
    return {**message.payload, **task_input.to_payload()}


def _build_task_output(result: dict[str, Any], duration_ms: int) -> TaskOutput:
    status = "ok" if result.get("error") is None else "error"
    return TaskOutput(
        status=status,
        result=result if status == "ok" else None,
        error=result.get("error") if status == "error" else None,
        tokens_used=int(result.get("tokens_used", 0)) if isinstance(result, dict) else 0,
        cost_usd=float(result.get("cost_usd", 0.0)) if isinstance(result, dict) else 0.0,
        duration_ms=duration_ms,
    )


class QueueWorker:
    def __init__(self, worker_name: str, redis_url: str | None = None, dbname: str | None = None) -> None:
        self.worker_name = worker_name
        self.redis = RedisStream(redis_url)
        self.jobs = JobsDAO(dbname=dbname)
        self.otel_enabled = configure_otel()
        self.hermes = Hermes()
        self.registry = WorkerRegistry()
        self._register_worker(worker_name)
        config_dir = os.environ.get("NAMI_CONFIG_DIR", "config")
        self.registry.load_from_directory(config_dir)
        self.registry.wire_into_hermes(self.hermes)
        self.consumer_id = f"nami-worker-{worker_name}-{os.getpid()}"
        self.group = "workers"
        self._stop = asyncio.Event()
        self._executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
        self._capabilities = list(self.hermes.worker_actions(worker_name))

    def _register_worker(self, worker_name: str) -> None:
        module_name = f"nami_workers.{worker_name}_worker"
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise SystemExit(f"Worker module not found for '{worker_name}': {exc}")
        task = getattr(module, f"{worker_name}_worker", None)
        if not callable(task):
            raise SystemExit(f"Worker task not found in {module_name}")
        self.registry.register(worker_name, task)

    def start(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:
                signal.signal(sig, lambda *_args: self._stop.set())

        self.redis.ensure_group(self.group)
        await asyncio.gather(self._heartbeat_loop(), self._consume_loop())
        self._executor.shutdown(wait=True)

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                payload = json.dumps(
                    {
                        "worker": self.worker_name,
                        "consumer": self.consumer_id,
                        "capabilities": self._capabilities,
                        "host": socket.gethostname(),
                        "pid": os.getpid(),
                    },
                    ensure_ascii=False,
                )
                self.redis._get_client().set(f"nami:worker:{self.consumer_id}", payload, ex=60)
            except Exception as exc:
                logger.warning("Heartbeat failed: %s", exc)
            await asyncio.sleep(WORKER_HEARTBEAT_SEC)

    async def _consume_loop(self) -> None:
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        while not self._stop.is_set():
            try:
                claimed = await asyncio.to_thread(self.redis.autoclaim, self.group, self.consumer_id)
                for msg_id, fields in claimed:
                    await self._schedule_message(msg_id, fields, semaphore)

                messages = await asyncio.to_thread(self.redis.read_group, self.group, self.consumer_id, 1)
                for msg_id, fields in messages:
                    await self._schedule_message(msg_id, fields, semaphore)
            except Exception as exc:
                logger.warning("Queue read failed: %s", exc)
                await asyncio.sleep(2)

    async def _schedule_message(self, msg_id: str, fields: dict[str, str], semaphore: asyncio.Semaphore) -> None:
        await semaphore.acquire()
        asyncio.create_task(self._handle_message(msg_id, fields, semaphore))

    async def _handle_message(self, msg_id: str, fields: dict[str, str], semaphore: asyncio.Semaphore) -> None:
        try:
            message = JobMessage.from_stream_fields(fields)
            worker, action = _parse_action(message.action)
            if worker != self.worker_name:
                await asyncio.to_thread(self._handle_mismatch, msg_id, message)
                return

            worker_id = self.consumer_id
            self.jobs.mark_running(message.id, worker_id)
            self.redis.publish_event("job.running", {"job_id": message.id, "action": message.action, "worker_id": worker_id})

            output, error, duration_ms = await self._execute_with_timeout(message, worker, action)
            await asyncio.to_thread(self._finalize_message, msg_id, message, output, error, duration_ms)
        finally:
            semaphore.release()

    async def _execute_with_timeout(
        self,
        message: JobMessage,
        worker: str,
        action: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int]:
        loop = asyncio.get_running_loop()
        started = time.monotonic()
        output: dict[str, Any] | None = None
        error: dict[str, Any] | None = None
        try:
            output = await asyncio.wait_for(
                loop.run_in_executor(self._executor, self._execute_task, message, worker, action),
                timeout=message.budget.max_seconds,
            )
        except asyncio.TimeoutError:
            error = {"error": f"timeout after {message.budget.max_seconds}s"}
        except Exception as exc:
            error = {"error": str(exc)}
        duration_ms = int((time.monotonic() - started) * 1000)
        return output, error, duration_ms

    def _execute_task(self, message: JobMessage, worker: str, action: str) -> dict[str, Any] | None:
        payload = _build_task_payload(message)
        with cost_span(
            "nami.worker.execute",
            role="worker",
            attributes={
                "job.id": message.id,
                "job.action": message.action,
                "job.attempt": message.attempt,
                "trace.id": message.trace_id,
                "nami.worker": worker,
                "nami.action": action,
            },
        ) as span:
            result = self.hermes.dispatch(worker, action, payload)
            output = result.output
            if isinstance(output, dict):
                if "tokens_used" in output:
                    span.set_attribute("tokens.used", int(output.get("tokens_used") or 0))
                if "cost_usd" in output:
                    span.set_attribute("cost.usd", float(output.get("cost_usd") or 0.0))
            return output

    def _handle_mismatch(self, msg_id: str, message: JobMessage) -> None:
        self.jobs.mark_running(message.id, self.consumer_id)
        error = {"error": f"worker mismatch for {message.action}"}
        self._finalize_message(msg_id, message, None, error, 0)

    def _finalize_message(
        self,
        msg_id: str,
        message: JobMessage,
        output: dict[str, Any] | None,
        error: dict[str, Any] | None,
        duration_ms: int,
    ) -> None:
        if output is None:
            output = {}
        output = dict(output)
        output.setdefault("duration_ms", duration_ms)

        if error:
            attempt = message.attempt + 1
            self.jobs.mark_failed(message.id, error, attempt)
            if attempt <= message.budget.max_retries:
                self.jobs.requeue(message.id, attempt)
                retry_message = JobMessage(
                    id=message.id,
                    action=message.action,
                    payload=message.payload,
                    idempotency_key=message.idempotency_key,
                    trace_id=message.trace_id,
                    parent_id=message.parent_id,
                    budget=message.budget,
                    enqueued_at=message.enqueued_at,
                    attempt=attempt,
                )
                self.redis.enqueue(retry_message)
                self.redis.publish_event("job.failed", {"job_id": message.id, "attempt": attempt, "error": error, "trace_id": message.trace_id})
            else:
                self.jobs.mark_dead(message.id, error)
                self.redis.enqueue_dead(message, error)
                self.redis.publish_event("job.dead", {"job_id": message.id, "attempt": attempt, "error": error, "trace_id": message.trace_id})
        else:
            task_output = _build_task_output(output, duration_ms)
            self.jobs.mark_succeeded(message.id, task_output.to_dict())
            self.redis.publish_event("job.succeeded", {"job_id": message.id, "duration_ms": duration_ms, "trace_id": message.trace_id, "cost_usd": task_output.cost_usd})

        self.redis.ack(self.group, msg_id)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    worker_name = os.environ.get("NAMI_WORKER")
    if not worker_name:
        raise SystemExit("NAMI_WORKER must be set (e.g. lottery)")
    if args.dry_run:
        QueueWorker(worker_name)
        print("worker ready")
        return
    worker = QueueWorker(worker_name)
    worker.start()


if __name__ == "__main__":
    main()
