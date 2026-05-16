"""Orphan-worker detector — Phase 30.

Workers refresh `nami:worker:{consumer_id}` in Redis with TTL=60s
(see runtime/queue/worker.py `_heartbeat_loop`). After a worker
exits unexpectedly, the key expires and the entry vanishes from
Redis — but the corresponding consumer can still hold a XPENDING
entry on the stream. This detector flags consumers that XPENDING
shows but no live heartbeat key matches, so an operator (or future
auto-claim job) can reclaim the messages.

This is read-only / advisory — Phase 30 ships detection only. The
auto-claim path (XCLAIM) already exists in worker.py and runs every
loop iteration; this detector exists for ops visibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger("nami_core.runtime.reconcile.orphan")


@dataclass(frozen=True)
class OrphanWorker:
    consumer_id: str
    pending_count: int


@dataclass
class OrphanReport:
    live: list[str] = field(default_factory=list)
    orphans: list[OrphanWorker] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class _RedisLike(Protocol):
    """Subset of `RedisStream` needed for orphan detection."""

    def list_worker_heartbeats(self) -> list[str]: ...
    def list_consumers(self, group: str) -> list[dict[str, Any]]: ...


def detect_orphan_workers(redis: _RedisLike, group: str = "workers") -> OrphanReport:
    report = OrphanReport()
    try:
        live = set(redis.list_worker_heartbeats())
    except Exception as exc:  # noqa: BLE001 — advisory only
        report.errors.append(f"list_worker_heartbeats: {exc}")
        return report
    report.live = sorted(live)

    try:
        consumers = redis.list_consumers(group)
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"list_consumers: {exc}")
        return report

    for entry in consumers:
        name = str(entry.get("name") or "")
        pending = int(entry.get("pending") or 0)
        if not name:
            continue
        # Heartbeat key looks like "nami:worker:<consumer_id>" — match by suffix.
        live_match = any(hb.endswith(name) for hb in live)
        if not live_match and pending > 0:
            report.orphans.append(OrphanWorker(consumer_id=name, pending_count=pending))
            logger.warning("orphan consumer detected: %s pending=%s", name, pending)

    return report


__all__ = ["OrphanReport", "OrphanWorker", "detect_orphan_workers"]
