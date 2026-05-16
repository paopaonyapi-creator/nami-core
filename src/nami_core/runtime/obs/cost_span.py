"""Cost-aware OpenTelemetry span helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from nami_core.runtime.obs.otel_init import get_tracer
from nami_core.runtime.obs.pricing import estimate_cost_usd


_COST_USD_TOTAL_BY_ROLE: dict[str, float] = {}
_TOKENS_IN_TOTAL_BY_ROLE: dict[str, int] = {}
_TOKENS_OUT_TOTAL_BY_ROLE: dict[str, int] = {}
_COST_SPANS_TOTAL_BY_ROLE: dict[str, int] = {}


def record_cost_metric(
    role: str,
    model: str = "default",
    *,
    cost_usd: float | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    amount = float(cost_usd if cost_usd is not None else estimate_cost_usd(model, tokens_in, tokens_out))
    in_tokens = max(int(tokens_in or 0), 0)
    out_tokens = max(int(tokens_out or 0), 0)
    if amount <= 0 and in_tokens <= 0 and out_tokens <= 0:
        return
    metric_role = role or "unknown"
    _COST_USD_TOTAL_BY_ROLE[metric_role] = round(_COST_USD_TOTAL_BY_ROLE.get(metric_role, 0.0) + amount, 6)
    _TOKENS_IN_TOTAL_BY_ROLE[metric_role] = _TOKENS_IN_TOTAL_BY_ROLE.get(metric_role, 0) + in_tokens
    _TOKENS_OUT_TOTAL_BY_ROLE[metric_role] = _TOKENS_OUT_TOTAL_BY_ROLE.get(metric_role, 0) + out_tokens
    _COST_SPANS_TOTAL_BY_ROLE[metric_role] = _COST_SPANS_TOTAL_BY_ROLE.get(metric_role, 0) + 1


def cost_metrics_prometheus_lines() -> list[str]:
    roles = sorted(set(_COST_USD_TOTAL_BY_ROLE) | set(_TOKENS_IN_TOTAL_BY_ROLE) | set(_TOKENS_OUT_TOTAL_BY_ROLE) | set(_COST_SPANS_TOTAL_BY_ROLE))
    lines = [
        "# TYPE nami_cost_usd_total counter",
        "# TYPE nami_tokens_in_total counter",
        "# TYPE nami_tokens_out_total counter",
        "# TYPE nami_cost_spans_total counter",
    ]
    if not roles:
        roles = ["none"]
    for role in roles:
        lines.append(f'nami_cost_usd_total{{role="{role}"}} {_COST_USD_TOTAL_BY_ROLE.get(role, 0.0)}')
        lines.append(f'nami_tokens_in_total{{role="{role}"}} {_TOKENS_IN_TOTAL_BY_ROLE.get(role, 0)}')
        lines.append(f'nami_tokens_out_total{{role="{role}"}} {_TOKENS_OUT_TOTAL_BY_ROLE.get(role, 0)}')
        lines.append(f'nami_cost_spans_total{{role="{role}"}} {_COST_SPANS_TOTAL_BY_ROLE.get(role, 0)}')
    return lines


def reset_cost_metrics() -> None:
    _COST_USD_TOTAL_BY_ROLE.clear()
    _TOKENS_IN_TOTAL_BY_ROLE.clear()
    _TOKENS_OUT_TOTAL_BY_ROLE.clear()
    _COST_SPANS_TOTAL_BY_ROLE.clear()


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
        try:
            yield span
        finally:
            record_cost_metric(role, model, cost_usd=cost, tokens_in=tokens_in, tokens_out=tokens_out)


__all__ = ["cost_metrics_prometheus_lines", "cost_span", "record_cost_metric", "reset_cost_metrics"]
