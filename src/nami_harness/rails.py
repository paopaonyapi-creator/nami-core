from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from time import time

from .exceptions import RailDenied


@dataclass(frozen=True)
class RailDecision:
    allowed: bool
    reason: str


@dataclass
class RateLimitRail:
    max_events: int
    window_seconds: float
    clock: Callable[[], float] = time
    _events: dict[tuple[str, str], deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def check(self, *, agent: str, action: str) -> RailDecision:
        now = self.clock()
        key = (agent, action)
        events = self._events[key]
        while events and now - events[0] >= self.window_seconds:
            events.popleft()
        if len(events) >= self.max_events:
            return RailDecision(False, f"rate limit exceeded for {agent}:{action}")
        return RailDecision(True, "allowed")

    def record(self, *, agent: str, action: str) -> None:
        self._events[(agent, action)].append(self.clock())

    def assert_allowed(self, *, agent: str, action: str) -> None:
        decision = self.check(agent=agent, action=action)
        if not decision.allowed:
            raise RailDenied(decision.reason)
        self.record(agent=agent, action=action)


@dataclass
class RailPolicy:
    allowed_agents: set[str] = field(default_factory=set)
    allowed_actions: set[str] = field(default_factory=set)
    max_daily_actions: int | None = None
    rate_limit: RateLimitRail | None = None
    _action_count: int = 0

    def check(self, *, agent: str, action: str) -> RailDecision:
        if self.allowed_agents and agent not in self.allowed_agents:
            return RailDecision(False, f"agent not allowed: {agent}")

        if self.allowed_actions and action not in self.allowed_actions:
            return RailDecision(False, f"action not allowed: {action}")

        if self.max_daily_actions is not None and self._action_count >= self.max_daily_actions:
            return RailDecision(False, "daily action quota exceeded")

        if self.rate_limit:
            decision = self.rate_limit.check(agent=agent, action=action)
            if not decision.allowed:
                return decision

        return RailDecision(True, "allowed")

    def assert_allowed(self, *, agent: str, action: str) -> None:
        decision = self.check(agent=agent, action=action)
        if not decision.allowed:
            raise RailDenied(decision.reason)
        self._action_count += 1
        if self.rate_limit:
            self.rate_limit.record(agent=agent, action=action)
