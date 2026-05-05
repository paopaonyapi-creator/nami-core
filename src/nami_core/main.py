"""Nami Core — main entry point for the unified service.

When run as `python -m nami_core.main`, starts the Hermes
router with all configured workers and their harness runtimes.
"""

from __future__ import annotations

import os

from nami_core.config import load_harness_config
from nami_core.hermes import Hermes
from nami_workers.registry import WorkerRegistry


def main() -> None:
    config_dir = os.environ.get("NAMI_CONFIG_DIR", "config")
    worker_name = os.environ.get("NAMI_WORKER", "")

    hermes = Hermes()
    registry = WorkerRegistry()

    # Load all worker configs from config directory
    registry.load_from_directory(config_dir)

    # Wire workers into Hermes with their harness runtimes
    registry.wire_into_hermes(hermes)

    workers = hermes.list_workers()
    print(f"Nami Core started — {len(workers)} workers: {', '.join(workers)}")

    if worker_name:
        print(f"Running single worker: {worker_name}")
        # Single worker mode (for systemd template units)
        result = hermes.dispatch(worker_name, "health_check", {})
        print(f"Health check: {result.output}")
    else:
        # Full mode — all workers registered
        for name in workers:
            try:
                result = hermes.dispatch(name, "health_check", {})
                print(f"  {name}: OK — {result.output}")
            except Exception as exc:
                print(f"  {name}: ERROR — {exc}")


if __name__ == "__main__":
    main()
