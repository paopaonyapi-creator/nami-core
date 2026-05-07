from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

_log = logging.getLogger(__name__)
_warned_paths: set[str] = set()


@dataclass(frozen=True)
class SensorEvent:
    event_type: str
    payload: dict[str, Any]
    status: str = "info"
    agent: str | None = None
    action: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = "1.0"


class JsonlSensor:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        status: str = "info",
        agent: str | None = None,
        action: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SensorEvent:
        event = SensorEvent(
            event_type=event_type,
            payload=payload,
            status=status,
            agent=agent,
            action=action,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True))
                file.write("\n")
        except OSError as exc:
            key = str(self.path)
            if key not in _warned_paths:
                _warned_paths.add(key)
                _log.warning(
                    "sensor write failed for %s: %s (further failures suppressed)",
                    self.path,
                    exc,
                )
        return event
