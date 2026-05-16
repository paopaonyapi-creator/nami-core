"""D12 — Prompt size explosion: tokens > 80% of model context window."""

from __future__ import annotations

from nami_core.safety.types import Detection, DetectorContext


def detect(ctx: DetectorContext) -> Detection | None:
    if ctx.model_context_window <= 0 or ctx.prompt_tokens <= 0:
        return None
    ratio = ctx.prompt_tokens / ctx.model_context_window
    if ratio < 0.80:
        return None
    return Detection(
        pattern="D12",
        action="truncate",
        reason=f"prompt {ctx.prompt_tokens}/{ctx.model_context_window} tokens ({ratio:.0%}) ≥ 80%",
        severity="medium",
        metadata={"prompt_tokens": ctx.prompt_tokens, "ctx_window": ctx.model_context_window, "ratio": ratio},
    )
