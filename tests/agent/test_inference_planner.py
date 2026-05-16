"""Phase 27 PR-B follow-up: InferencePlanner JSON parsing tests.

Validates the LLM-as-planner contract: structured JSON input -> typed
PlanDecision output, with defensive parsing for malformed responses.

Uses a FakeGateway so tests are offline + deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from nami_core.agent import AgentState, InferencePlanner
from nami_core.agent.planner import (
    DEFAULT_SYSTEM_PROMPT,
    _extract_json_object,
    _strip_fences,
)
from nami_core.inference_gateway import InferenceRequest, InferenceResponse


@dataclass
class FakeGateway:
    """Returns scripted InferenceResponse content. No network."""

    content: str = "{}"
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    raise_exc: Exception | None = None
    last_request: InferenceRequest | None = field(default=None, init=False)

    def complete(self, request: InferenceRequest) -> InferenceResponse:
        self.last_request = request
        if self.raise_exc is not None:
            raise self.raise_exc
        return InferenceResponse(
            content=self.content,
            model_used=request.model,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            cost_usd=self.cost_usd,
            latency_ms=10,
        )


def _state(goal: str = "summarize the report") -> AgentState:
    return AgentState(
        job_id="job-p1",
        trace_id="00-deadbeef-cafef00d-01",
        parent_id=None,
        goal=goal,
    )


# ─── helpers ───────────────────────────────────────────────────────────


def test_strip_fences_removes_json_block_markers() -> None:
    assert _strip_fences("```json\n{\"a\":1}\n```") == '{"a":1}'
    assert _strip_fences("```\nplain\n```") == "plain"
    assert _strip_fences('{"x":1}') == '{"x":1}'


def test_extract_json_object_finds_first_balanced_block() -> None:
    text = 'prose before {"a": {"b": 1}} trailing prose'
    assert _extract_json_object(text) == '{"a": {"b": 1}}'


def test_extract_json_object_returns_empty_when_no_brace() -> None:
    assert _extract_json_object("nothing here") == ""


def test_extract_json_object_handles_unbalanced() -> None:
    assert _extract_json_object("{not json") == ""


# ─── happy path ────────────────────────────────────────────────────────


def test_inference_planner_parses_done_decision() -> None:
    gw = FakeGateway(
        content='{"action":"done","final_answer":"42","reasoning":"got it"}',
        cost_usd=0.001,
        tokens_in=10,
        tokens_out=5,
    )
    p = InferencePlanner(gateway=gw, model="maxplus:default", available_tools=["echo"])
    decision = p.plan(_state())
    assert decision.action == "done"
    assert decision.final_answer == "42"
    assert decision.reasoning == "got it"
    assert decision.cost_usd == 0.001
    assert decision.tokens_in == 10
    assert decision.tokens_out == 5


def test_inference_planner_parses_tool_decision() -> None:
    gw = FakeGateway(
        content='{"action":"tool","tool":"echo","tool_args":{"x":1},"reasoning":"call echo"}',
    )
    p = InferencePlanner(gateway=gw, available_tools=["echo"])
    decision = p.plan(_state())
    assert decision.action == "tool"
    assert decision.tool == "echo"
    assert decision.tool_args == {"x": 1}
    assert decision.reasoning == "call echo"


def test_inference_planner_strips_markdown_fences() -> None:
    gw = FakeGateway(content='```json\n{"action":"done","final_answer":"hi","reasoning":""}\n```')
    p = InferencePlanner(gateway=gw)
    decision = p.plan(_state())
    assert decision.action == "done"
    assert decision.final_answer == "hi"


def test_inference_planner_handles_prose_around_json() -> None:
    gw = FakeGateway(
        content='Sure, here is my plan: {"action":"done","final_answer":"x","reasoning":"y"} OK?'
    )
    decision = InferencePlanner(gateway=gw).plan(_state())
    assert decision.action == "done"
    assert decision.final_answer == "x"


# ─── defensive parsing ─────────────────────────────────────────────────


def test_inference_planner_garbage_returns_done_with_parse_failure() -> None:
    gw = FakeGateway(content="totally not json")
    decision = InferencePlanner(gateway=gw).plan(_state())
    assert decision.action == "done"
    assert decision.final_answer is None
    assert "parse_failure" in decision.reasoning


def test_inference_planner_invalid_json_returns_done() -> None:
    gw = FakeGateway(content="{not valid json")
    decision = InferencePlanner(gateway=gw).plan(_state())
    assert decision.action == "done"
    assert "parse_failure" in decision.reasoning


def test_inference_planner_unknown_action_returns_done() -> None:
    gw = FakeGateway(content='{"action":"sing","reasoning":"oops"}')
    decision = InferencePlanner(gateway=gw).plan(_state())
    assert decision.action == "done"
    assert "unknown_action" in decision.reasoning


def test_inference_planner_tool_without_name_returns_done() -> None:
    gw = FakeGateway(content='{"action":"tool","tool":"","tool_args":{}}')
    decision = InferencePlanner(gateway=gw).plan(_state())
    assert decision.action == "done"
    assert "no_tool" in decision.reasoning


def test_inference_planner_tool_with_bad_args_returns_done() -> None:
    gw = FakeGateway(content='{"action":"tool","tool":"echo","tool_args":"oops"}')
    decision = InferencePlanner(gateway=gw).plan(_state())
    assert decision.action == "done"
    assert "bad_args" in decision.reasoning


def test_inference_planner_gateway_failure_returns_done() -> None:
    gw = FakeGateway(raise_exc=RuntimeError("backend down"))
    decision = InferencePlanner(gateway=gw).plan(_state())
    assert decision.action == "done"
    assert "gateway_failure" in decision.reasoning


# ─── prompt construction ───────────────────────────────────────────────


def test_inference_planner_prompt_includes_tool_list() -> None:
    gw = FakeGateway(content='{"action":"done","final_answer":"x"}')
    p = InferencePlanner(gateway=gw, available_tools=["echo", "search"])
    p.plan(_state())
    assert gw.last_request is not None
    sys_msg = gw.last_request.messages[0]
    assert sys_msg["role"] == "system"
    assert "echo, search" in sys_msg["content"]


def test_inference_planner_prompt_includes_goal() -> None:
    gw = FakeGateway(content='{"action":"done","final_answer":"x"}')
    p = InferencePlanner(gateway=gw)
    p.plan(_state(goal="my unique goal token"))
    assert gw.last_request is not None
    user_msgs = [m for m in gw.last_request.messages if m["role"] == "user"]
    assert any("my unique goal token" in m["content"] for m in user_msgs)


def test_default_system_prompt_includes_schema() -> None:
    assert "STRICT JSON" in DEFAULT_SYSTEM_PROMPT
    assert "tool_args" in DEFAULT_SYSTEM_PROMPT


# ─── end-to-end with AgentLoop ─────────────────────────────────────────


def test_loop_with_inference_planner_completes_via_done() -> None:
    """Inject a gateway that always says done; loop should terminate after 1 plan."""
    from nami_core.agent import AgentLoop

    gw = FakeGateway(
        content='{"action":"done","final_answer":"summary","reasoning":"trivial"}',
        cost_usd=0.002,
        tokens_in=20,
        tokens_out=10,
    )
    planner = InferencePlanner(gateway=gw)
    outcome = AgentLoop(planner=planner).run(_state())
    assert outcome.halted is False
    assert outcome.final_answer == "summary"
    assert outcome.state.cost_usd_total == pytest.approx(0.002)
    assert outcome.state.tokens_in_total == 20
    assert outcome.state.tokens_out_total == 10
