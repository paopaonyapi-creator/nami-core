"""MCP safety wiring helpers (SAFETY §7 D18 + D15).

D18 — Forbidden file access: validate `request.args` paths against the
server spec's `allowed_paths` before invoking the bridge. The sandbox
already enforces this at the OS layer (Phase 28 `validate_path_args`);
this helper surfaces it as an observable `Detection` so callers can
emit the `nami_safety_detection_total` metric and abort cleanly.

D15 — MCP server unhealthy: track consecutive timeouts per server in
a small in-process counter. On 3+ consecutive timeouts to one server,
emit a D15 alert (and let the caller mark the server unhealthy in
its registry).

Both helpers are pure data — no bridge mutation. The MCP bridge stays
exactly as Phase 28 shipped it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from nami_core.mcp.types import MCPRequest, MCPServerSpec
from nami_core.safety.detectors import d15, d18
from nami_core.safety.types import Detection, DetectorContext


# ── D18 — file-access pre-check ────────────────────────────────────────


_PATH_ARG_KEYS = ("path", "file", "filename", "dest", "src", "source")


def _extract_paths(args: dict[str, Any]) -> list[str]:
    """Best-effort: pull anything that looks like a file path out of args."""
    out: list[str] = []
    for key, value in args.items():
        if not isinstance(value, str):
            continue
        if key in _PATH_ARG_KEYS or key.endswith("_path") or key.endswith("_file"):
            out.append(value)
    return out


def check_file_access(
    request: MCPRequest,
    spec: MCPServerSpec,
) -> list[Detection]:
    """Run D18 against every path-shaped arg in the request. Returns all firings."""
    paths = _extract_paths(request.args or {})
    if not paths:
        return []
    allowed = list(spec.allowed_paths)
    detections: list[Detection] = []
    for path in paths:
        ctx = DetectorContext(
            job_id=request.job_id or "",
            role=request.role,
            iteration=0,
            file_access_path=path,
            file_access_allowed_roots=allowed,
        )
        det = d18(ctx)
        if det is not None:
            det.metadata.setdefault("server", spec.name)
            det.metadata.setdefault("tool", request.tool)
            detections.append(det)
    return detections


# ── D15 — consecutive-timeout tracker ─────────────────────────────────


@dataclass
class MCPTimeoutTracker:
    """Tracks consecutive timeouts per MCP server.

    Caller invokes `record(server, status)` after every bridge call:
      status='ok'      → reset counter
      status='timeout' → increment
      anything else    → reset (treat as non-timeout outcome)

    After recording, call `check(server)` to get a D15 Detection if the
    server has hit the 3-consecutive-timeout threshold. The tracker
    does NOT auto-mark servers unhealthy — that's the caller's policy.
    """

    consecutive: dict[str, int] = field(default_factory=dict)

    def record(self, server: str, status: str) -> None:
        if status == "timeout":
            self.consecutive[server] = self.consecutive.get(server, 0) + 1
        else:
            self.consecutive[server] = 0

    def streak(self, server: str) -> int:
        return self.consecutive.get(server, 0)

    def reset(self, server: str) -> None:
        self.consecutive[server] = 0

    def check(self, server: str) -> Detection | None:
        ctx = DetectorContext(
            job_id="",
            role="mcp",
            iteration=0,
            mcp_server_name=server,
            mcp_consecutive_timeouts=self.streak(server),
        )
        return d15(ctx)

    def unhealthy_servers(self, candidates: Iterable[str] | None = None) -> list[str]:
        """Return the set of servers currently flagged by D15."""
        names = list(candidates) if candidates is not None else list(self.consecutive.keys())
        return [s for s in names if self.check(s) is not None]


__all__ = [
    "MCPTimeoutTracker",
    "check_file_access",
]
