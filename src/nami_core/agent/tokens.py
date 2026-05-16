"""Lightweight prompt-token estimation for safety detectors.

This is intentionally a coarse heuristic (chars / 4) — adequate for SAFETY §7
threshold detectors like D12 that fire at >=80% of `model_context_window`.
Callers that need exact counts (billing, routing) should use the LLM
provider's tokenizer instead of this module.
"""

from __future__ import annotations

from typing import Any, Iterable

from nami_core.agent.state import AgentState


_CHARS_PER_TOKEN = 4


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: Iterable[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        for value in msg.values():
            if isinstance(value, str):
                total += estimate_text_tokens(value)
            elif value is not None:
                total += estimate_text_tokens(str(value))
    return total


def estimate_state_prompt_tokens(state: AgentState) -> int:
    """Estimate tokens the planner would send if it were called now.

    Sums goal + messages + per-step content. Intentionally over-counts a
    little so D12 fires conservatively (false-positive bias is safe; the
    detector only emits a `truncate` advisory, never a halt).
    """
    total = estimate_text_tokens(state.goal or "")
    total += estimate_messages_tokens(state.messages)
    for step in state.steps:
        total += estimate_text_tokens(step.content or "")
    for chunk in state.rag_chunks:
        total += estimate_text_tokens(chunk)
    return total


__all__ = [
    "estimate_messages_tokens",
    "estimate_state_prompt_tokens",
    "estimate_text_tokens",
]
