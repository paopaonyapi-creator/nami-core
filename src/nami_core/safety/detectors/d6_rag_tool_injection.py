"""D6 — Tool injection via RAG: retrieved context contains tool-call patterns.

Detection: any RAG chunk matches injection markers commonly used by adversarial
documents (`<tool_call>`, `{"tool":`, function-call JSON, ANSI hidden text, etc.).
Response: strip patterns and tag context as filtered; surface a `filter`
detection so callers can fall back to a shorter context.
"""

from __future__ import annotations

import re

from nami_core.safety.types import Detection, DetectorContext


_INJECTION_PATTERNS = [
    re.compile(r"<\s*tool_call\s*>", re.IGNORECASE),
    re.compile(r"</\s*tool_call\s*>", re.IGNORECASE),
    re.compile(r"\{\s*[\"']tool[\"']\s*:", re.IGNORECASE),
    re.compile(r"\{\s*[\"']action[\"']\s*:\s*[\"']execute", re.IGNORECASE),
    re.compile(r"<\s*function_call\s*>", re.IGNORECASE),
    re.compile(r"ignore (all )?(previous|prior) instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*you (are|must)", re.IGNORECASE),
    re.compile(r"\x1b\[[0-9;]*m"),  # ANSI escapes — hidden prompts
]


def _strip(text: str) -> tuple[str, int]:
    hits = 0
    out = text
    for pat in _INJECTION_PATTERNS:
        new, n = pat.subn("[FILTERED]", out)
        hits += n
        out = new
    return out, hits


def detect(ctx: DetectorContext) -> Detection | None:
    if not ctx.rag_chunks:
        return None
    filtered: list[str] = []
    total_hits = 0
    affected: list[int] = []
    for i, chunk in enumerate(ctx.rag_chunks):
        new, hits = _strip(chunk)
        filtered.append(new)
        if hits > 0:
            total_hits += hits
            affected.append(i)
    if total_hits == 0:
        return None
    return Detection(
        pattern="D6",
        action="filter",
        reason=f"tool-injection patterns found in {len(affected)} RAG chunk(s)",
        severity="high",
        metadata={
            "chunks": filtered,
            "affected_indices": affected,
            "hit_count": total_hits,
        },
    )
