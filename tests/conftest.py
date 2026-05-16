from __future__ import annotations

import pytest


_DOCKER_REQUIRED_NODEIDS = (
    "tests/runtime/queue/test_idempotency.py::test_idempotency_returns_existing_job",
    "tests/runtime/queue/test_redis_stream.py::",
    "tests/runtime/queue/test_worker_lifecycle.py::",
    "tests/integration/test_backtest_async_path.py::",
)


def _requires_docker(nodeid: str) -> bool:
    normalized = nodeid.replace("\\", "/")
    return any(target in normalized for target in _DOCKER_REQUIRED_NODEIDS)


def _docker_available() -> tuple[bool, str]:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    docker_items = [item for item in items if _requires_docker(item.nodeid)]
    if not docker_items:
        return

    ok, reason = _docker_available()
    if ok:
        return

    marker = pytest.mark.skip(reason=f"Docker unavailable for testcontainers: {reason}")
    for item in docker_items:
        item.add_marker(marker)
