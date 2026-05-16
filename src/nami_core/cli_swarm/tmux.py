"""Phase 32 — tmux session manager.

Real backend wraps `libtmux` (deferred import). FakeTmux backend stores
sessions in dicts for tests. Both expose the same `TmuxBackend` Protocol.
"""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger("nami_core.cli_swarm.tmux")


class TmuxBackend(Protocol):
    def new_session(self, name: str, cwd: str, argv: list[str]) -> bool: ...
    def kill_session(self, name: str) -> bool: ...
    def list_sessions(self) -> list[str]: ...
    def capture_pane(self, name: str) -> str: ...
    def send_keys(self, name: str, text: str) -> bool: ...


class LibTmux:
    """Real backend — defers libtmux import so tests don't require it installed."""

    def __init__(self) -> None:
        import libtmux  # noqa: F401 — imported lazily so test envs can skip it

        self._libtmux = __import__("libtmux")
        self._server = self._libtmux.Server()

    def _find(self, name: str):
        for s in self._server.sessions:
            if s.name == name:
                return s
        return None

    def new_session(self, name: str, cwd: str, argv: list[str]) -> bool:
        if self._find(name) is not None:
            return False
        command = " ".join(shlex.quote(a) for a in argv)
        self._server.new_session(
            session_name=name, start_directory=cwd, window_command=command, attach=False
        )
        return True

    def kill_session(self, name: str) -> bool:
        s = self._find(name)
        if s is None:
            return False
        s.kill_session()
        return True

    def list_sessions(self) -> list[str]:
        return [s.name for s in self._server.sessions]

    def capture_pane(self, name: str) -> str:
        s = self._find(name)
        if s is None:
            return ""
        pane = s.windows[0].panes[0]
        return "\n".join(pane.capture_pane())

    def send_keys(self, name: str, text: str) -> bool:
        s = self._find(name)
        if s is None:
            return False
        pane = s.windows[0].panes[0]
        pane.send_keys(text, enter=True)
        return True


@dataclass
class FakeTmux:
    """Test backend. Records sessions + pane buffers."""

    sessions: dict[str, dict] = field(default_factory=dict)
    fail_new: bool = False

    def new_session(self, name: str, cwd: str, argv: list[str]) -> bool:
        if self.fail_new:
            return False
        if name in self.sessions:
            return False
        self.sessions[name] = {"cwd": cwd, "argv": argv, "buffer": "", "killed": False}
        return True

    def kill_session(self, name: str) -> bool:
        if name not in self.sessions:
            return False
        self.sessions[name]["killed"] = True
        del self.sessions[name]
        return True

    def list_sessions(self) -> list[str]:
        return sorted(self.sessions.keys())

    def capture_pane(self, name: str) -> str:
        return self.sessions.get(name, {}).get("buffer", "")

    def send_keys(self, name: str, text: str) -> bool:
        if name not in self.sessions:
            return False
        self.sessions[name]["buffer"] += text + "\n"
        return True

    def emit(self, name: str, text: str) -> None:
        """Test helper — append simulated CLI output to the pane buffer."""
        if name in self.sessions:
            self.sessions[name]["buffer"] += text


__all__ = ["TmuxBackend", "LibTmux", "FakeTmux"]
