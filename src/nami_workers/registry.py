"""Worker registry — discover and manage worker plugins.

Workers are registered by name with their task function and
harness config path. The registry can auto-discover workers
from a config directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from nami_core.config import HarnessConfig, load_harness_config
from nami_core.hermes import Hermes

Task = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class WorkerEntry:
    name: str
    task: Task
    config: HarnessConfig | None = None


class WorkerRegistry:
    """Central registry for worker plugins.

    Workers can be registered manually or loaded from config files.
    Once registered, they can be wired into Hermes with their
    HarnessRuntime built from config.
    """

    def __init__(self) -> None:
        self._workers: dict[str, WorkerEntry] = {}

    def register(
        self,
        name: str,
        task: Task,
        config: HarnessConfig | None = None,
    ) -> None:
        if name in self._workers:
            raise ValueError(f"worker already registered: {name}")
        self._workers[name] = WorkerEntry(name=name, task=task, config=config)

    def get(self, name: str) -> WorkerEntry:
        if name not in self._workers:
            raise KeyError(f"worker not found: {name}")
        return self._workers[name]

    def list_workers(self) -> list[str]:
        return list(self._workers.keys())

    def wire_into_hermes(self, hermes: Hermes) -> None:
        """Register all workers into a Hermes instance.

        For each worker with a config, builds a HarnessRuntime
        and registers it with Hermes.
        """
        for name, entry in self._workers.items():
            if entry.config is not None:
                runtime = entry.config.build_runtime()
            else:
                from nami_harness.quality import QualityGate
                from nami_harness.rails import RailPolicy
                from nami_harness.runtime import HarnessRuntime as HR

                runtime = HR(rails=RailPolicy(), quality=QualityGate([]))

            hermes.register(
                name=name,
                runtime=runtime,
                task=entry.task,
                actions=entry.config.allowed_actions if entry.config else set(),
            )

    def load_from_directory(self, config_dir: str | Path) -> None:
        """Auto-discover workers from YAML config files.

        Each .yaml file in the directory is treated as a worker config.
        The worker name comes from the 'name' field or the file stem.
        Workers must be registered separately with their task functions.
        """
        config_dir = Path(config_dir)
        if not config_dir.exists():
            return

        for yaml_file in sorted(config_dir.glob("*.yaml")):
            config = load_harness_config(yaml_file)
            if config.name not in self._workers:
                self._workers[config.name] = WorkerEntry(
                    name=config.name,
                    task=lambda payload: {"status": "not_implemented"},
                    config=config,
                )
            else:
                self._workers[config.name].config = config


# Module-level convenience
_default_registry = WorkerRegistry()


def register_worker(name: str, task: Task, config: HarnessConfig | None = None) -> None:
    _default_registry.register(name, task, config)


def get_worker(name: str) -> WorkerEntry:
    return _default_registry.get(name)
