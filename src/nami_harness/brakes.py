from dataclasses import dataclass
from pathlib import Path

from .exceptions import BrakeEngaged


class FileKillSwitch:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def engaged(self) -> bool:
        return self.path.exists()

    def assert_open(self) -> None:
        if self.engaged():
            raise BrakeEngaged(f"kill switch engaged: {self.path}")


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    failures: int = 0
    forced_open: bool = False

    def record_success(self) -> None:
        self.failures = 0

    def record_failure(self) -> None:
        self.failures += 1

    def open(self) -> bool:
        return self.forced_open or self.failures >= self.failure_threshold

    def assert_closed(self) -> None:
        if self.open():
            raise BrakeEngaged("circuit breaker open")


@dataclass
class BudgetGuard:
    max_cost: float
    spent: float = 0.0
    forced_closed: bool = False

    def remaining(self) -> float:
        return max(0.0, self.max_cost - self.spent)

    def record_spend(self, cost: float) -> None:
        self.spent += cost

    def open(self, estimated_cost: float = 0.0) -> bool:
        return not self.forced_closed and self.spent + estimated_cost > self.max_cost

    def assert_within_budget(self, estimated_cost: float = 0.0) -> None:
        if self.open(estimated_cost):
            raise BrakeEngaged("budget guard open")
