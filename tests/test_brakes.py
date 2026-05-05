import pytest

from nami_harness.brakes import BudgetGuard, CircuitBreaker, FileKillSwitch
from nami_harness.exceptions import BrakeEngaged


def test_file_kill_switch_open_when_file_missing(tmp_path) -> None:
    kill_switch = FileKillSwitch(tmp_path / "kill")

    kill_switch.assert_open()


def test_file_kill_switch_engages_when_file_exists(tmp_path) -> None:
    path = tmp_path / "kill"
    path.write_text("stop", encoding="utf-8")
    kill_switch = FileKillSwitch(path)

    with pytest.raises(BrakeEngaged):
        kill_switch.assert_open()


def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure()
    breaker.assert_closed()
    breaker.record_failure()

    with pytest.raises(BrakeEngaged):
        breaker.assert_closed()


def test_budget_guard_allows_spend_inside_budget() -> None:
    guard = BudgetGuard(max_cost=1.0)

    guard.assert_within_budget(0.4)
    guard.record_spend(0.4)

    assert guard.remaining() == 0.6


def test_budget_guard_stops_when_estimated_cost_exceeds_budget() -> None:
    guard = BudgetGuard(max_cost=1.0, spent=0.8)

    with pytest.raises(BrakeEngaged):
        guard.assert_within_budget(0.3)
