"""D18 — Forbidden file access: worker attempts to read/write outside allowed roots.

Detection: `file_access_path` is not under any prefix in `file_access_allowed_roots`,
or it contains traversal markers (`..`, NUL). AppArmor enforces this at OS level
in prod; this detector is the userspace pre-check used by MCP filesystem tools.
"""

from __future__ import annotations

import os

from nami_core.safety.types import Detection, DetectorContext


def _normalize(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/")


def detect(ctx: DetectorContext) -> Detection | None:
    path = ctx.file_access_path
    if path is None:
        return None
    if "\x00" in path or ".." in path.split("/"):
        return Detection(
            pattern="D18",
            action="halt_branch",
            reason=f"forbidden file path: traversal/null in {path!r}",
            severity="high",
            metadata={"path": path, "reason": "traversal"},
        )
    if not ctx.file_access_allowed_roots:
        return Detection(
            pattern="D18",
            action="halt_branch",
            reason=f"forbidden file access {path!r}: no allowed roots configured",
            severity="high",
            metadata={"path": path, "reason": "no_roots"},
        )
    norm = _normalize(path)
    for root in ctx.file_access_allowed_roots:
        root_norm = _normalize(root).rstrip("/")
        if norm == root_norm or norm.startswith(root_norm + "/"):
            return None
    return Detection(
        pattern="D18",
        action="halt_branch",
        reason=f"forbidden file access {path!r}: outside allowed roots",
        severity="high",
        metadata={"path": path, "allowed_roots": list(ctx.file_access_allowed_roots)},
    )
