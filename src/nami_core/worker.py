"""Nami Core worker runner — starts a single worker by name.

Usage: python -m nami_core.worker <worker_name>

This is used by the systemd template unit nami-worker@.service.
"""

from __future__ import annotations

import os
import sys
import time

from nami_core.config import load_harness_config
from nami_core.hermes import Hermes
from nami_workers.registry import WorkerRegistry


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m nami_core.worker <worker_name>")
        sys.exit(1)

    worker_name = sys.argv[1]
    config_dir = os.environ.get("NAMI_CONFIG_DIR", "config")

    hermes = Hermes()
    registry = WorkerRegistry()
    registry.load_from_directory(config_dir)
    registry.wire_into_hermes(hermes)

    if worker_name not in hermes.list_workers():
        print(f"ERROR: worker '{worker_name}' not found")
        print(f"Available: {', '.join(hermes.list_workers())}")
        sys.exit(1)

    print(f"Worker '{worker_name}' started")

    # Keep running until killed
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print(f"Worker '{worker_name}' stopped")


if __name__ == "__main__":
    main()
