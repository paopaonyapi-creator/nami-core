from __future__ import annotations

import pytest

from nami_core.runtime.queue.jobs_dao import validate_transition


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("queued", "running"),
        ("queued", "cancelled"),
        ("running", "succeeded"),
        ("running", "failed"),
        ("running", "dead"),
        ("running", "cancelled"),
        ("failed", "queued"),
        ("failed", "dead"),
    ],
)
def test_validate_transition_allows_state_machine_edges(current_status, next_status):
    validate_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("queued", "succeeded"),
        ("queued", "failed"),
        ("failed", "succeeded"),
        ("succeeded", "queued"),
        ("dead", "queued"),
        ("cancelled", "running"),
    ],
)
def test_validate_transition_rejects_illegal_edges(current_status, next_status):
    with pytest.raises(ValueError, match="illegal job status transition"):
        validate_transition(current_status, next_status)


def test_validate_transition_rejects_unknown_status():
    with pytest.raises(ValueError, match="invalid current status"):
        validate_transition("unknown", "queued")
    with pytest.raises(ValueError, match="invalid next status"):
        validate_transition("queued", "unknown")
