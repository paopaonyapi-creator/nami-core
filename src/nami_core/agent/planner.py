"""InferencePlanner — Phase 27 PR-B follow-up.

Real LLM-backed planner that routes through `nami_core.inference_gateway`
(in-process; RUNTIME §6 single-dispatch contract).

Output contract — the LLM is asked to return strict JSON:

    {
      "action": "tool" | "done",
      "tool": "echo",                 // when action == "tool"
      "tool_args": {...},
      "final_answer": "string",       // when action == "done"
      "reasoning": "short rationale"
    }

Parsing is defensive:
  - strip ```json fences and surrounding prose
  - on failure -> PlanDecision(action="done") with `final_answer=None`
    and reasoning="parse_failure" so the loop terminates cleanly
    instead of looping on garbage.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from nami_core.agent.loop import PlanDecision
from nami_core.agent.state import AgentState
from nami_core.inference_gateway import InferenceGateway, InferenceRequest

logger = logging.getLogger("nami_core.agent.planner")

DEFAULT_SYSTEM_PROMPT = """You are a planning agent. Decide the next single step toward the user's goal.

Output STRICT JSON, no prose, no markdown fences. Schema:
{
  "action": "tool" or "done",
  "tool": "<tool name>" (only when action == "tool"),
  "tool_args": {<json object>} (only when action == "tool"),
  "final_answer": "<string>" (only when action == "done"),
  "reasoning": "<one short sentence>"
}

Available tools: {tool_list}
Pick "done" as soon as the goal is satisfied.
"""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def _extract_json_object(text: str) -> str:
    """Pull the first balanced {...} block out of the text."""
    text = _strip_fences(text)
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


@dataclass
class InferencePlanner:
    """LLM-backed planner using the in-process inference gateway."""

    gateway: InferenceGateway = field(default_factory=InferenceGateway)
    model: str = field(default_factory=lambda: os.environ.get("NAMI_AGENT_MODEL", "maxplus:default"))
    available_tools: list[str] = field(default_factory=lambda: ["echo"])
    temperature: float = 0.2
    max_tokens: int = 1024
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    def plan(self, state: AgentState) -> PlanDecision:
        messages = self._build_messages(state)
        request = InferenceRequest(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=False,
        )
        try:
            response = self.gateway.complete(request)
        except Exception as exc:  # noqa: BLE001 — gateway failure must not crash worker
            logger.warning("inference planner gateway failure: %s", exc)
            return PlanDecision(
                action="done",
                final_answer=None,
                reasoning=f"gateway_failure:{exc}",
            )

        decision = self._parse(response.content)
        decision.cost_usd = response.cost_usd
        decision.tokens_in = response.tokens_in
        decision.tokens_out = response.tokens_out
        return decision

    def _build_messages(self, state: AgentState) -> list[dict[str, Any]]:
        sys_prompt = self.system_prompt.replace("{tool_list}", ", ".join(self.available_tools))
        history = [{"role": "system", "content": sys_prompt}]
        history.append({"role": "user", "content": f"Goal: {state.goal}"})
        for step in state.steps[-6:]:  # last 6 steps as context window guard
            if step.kind == "plan" and step.content:
                history.append({"role": "assistant", "content": step.content})
            elif step.kind == "observe":
                history.append({"role": "tool", "content": step.content})
        history.append(
            {
                "role": "user",
                "content": "Decide the next step. Reply with the JSON object only.",
            }
        )
        return history

    def _parse(self, content: str) -> PlanDecision:
        raw = _extract_json_object(content)
        if not raw:
            return PlanDecision(action="done", final_answer=None, reasoning="parse_failure:no_json")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return PlanDecision(action="done", final_answer=None, reasoning=f"parse_failure:{exc}")

        action = str(data.get("action") or "").lower()
        reasoning = str(data.get("reasoning") or "")

        if action == "done":
            return PlanDecision(
                action="done",
                final_answer=str(data.get("final_answer") or ""),
                reasoning=reasoning,
            )
        if action == "tool":
            tool = data.get("tool")
            args = data.get("tool_args") or {}
            if not isinstance(tool, str) or not tool:
                return PlanDecision(action="done", reasoning="parse_failure:no_tool")
            if not isinstance(args, dict):
                return PlanDecision(action="done", reasoning="parse_failure:bad_args")
            return PlanDecision(
                action="tool",
                tool=tool,
                tool_args=args,
                reasoning=reasoning,
            )
        return PlanDecision(action="done", reasoning=f"parse_failure:unknown_action:{action}")


__all__ = ["InferencePlanner", "DEFAULT_SYSTEM_PROMPT"]
