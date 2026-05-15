"""Cost-aware OpenTelemetry span helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from nami_core.runtime.obs.otel_init import get_tracer
from nami_core.runtime.obs.pricing import estimate_cost_usd


@contextmanager
def cost_span(
    name: str,
    *,
    model: str = "default",
    tokens_in: int = 0,
    tokens_out: int = 0,
    role: str = "worker",
    attributes: dict[str, str | int | float | bool] | None = None,
) -> Iterator[object]:
    tracer = get_tracer("nami-core.runtime")
    cost = estimate_cost_usd(model, tokens_in, tokens_out)
    with tracer.start_as_current_span(name) as span:
        span.set_attribute("model.requested", model)
        span.set_attribute("tokens.in", tokens_in)
        span.set_attribute("tokens.out", tokens_out)
        span.set_attribute("cost.usd", cost)
        span.set_attribute("nami.role", role)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


__all__ = ["cost_span"]
