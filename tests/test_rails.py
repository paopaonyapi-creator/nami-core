import pytest

from nami_harness.exceptions import RailDenied
from nami_harness.rails import RailPolicy, RateLimitRail


def test_rail_policy_allows_known_agent_action() -> None:
    policy = RailPolicy(allowed_agents={"hermes"}, allowed_actions={"summarize"})

    policy.assert_allowed(agent="hermes", action="summarize")


def test_rail_policy_denies_unknown_agent() -> None:
    policy = RailPolicy(allowed_agents={"hermes"})

    with pytest.raises(RailDenied):
        policy.assert_allowed(agent="unknown", action="summarize")


def test_rail_policy_enforces_quota() -> None:
    policy = RailPolicy(max_daily_actions=1)

    policy.assert_allowed(agent="hermes", action="summarize")

    with pytest.raises(RailDenied):
        policy.assert_allowed(agent="hermes", action="summarize")


def test_rate_limit_rail_enforces_agent_action_window() -> None:
    now = 1000.0
    rail = RateLimitRail(max_events=2, window_seconds=10, clock=lambda: now)
    policy = RailPolicy(rate_limit=rail)

    policy.assert_allowed(agent="hermes", action="summarize")
    policy.assert_allowed(agent="hermes", action="summarize")

    with pytest.raises(RailDenied):
        policy.assert_allowed(agent="hermes", action="summarize")


def test_rate_limit_rail_expires_old_events() -> None:
    current_time = 1000.0
    rail = RateLimitRail(max_events=1, window_seconds=10, clock=lambda: current_time)
    policy = RailPolicy(rate_limit=rail)

    policy.assert_allowed(agent="hermes", action="summarize")
    current_time = 1011.0

    policy.assert_allowed(agent="hermes", action="summarize")
