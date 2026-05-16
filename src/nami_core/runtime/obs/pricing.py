"""Model token pricing utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_1k: float
    output_usd_per_1k: float


PRICING_TABLE: dict[str, ModelPricing] = {
    "ollama": ModelPricing(0.0, 0.0),
    "maxplus": ModelPricing(0.002, 0.002),
    "openai:gpt-4o-mini": ModelPricing(0.00015, 0.0006),
    "openai:gpt-4o": ModelPricing(0.005, 0.015),
    "default": ModelPricing(0.0, 0.0),
}


def _pricing_for_model(model: str) -> ModelPricing:
    if model in PRICING_TABLE:
        return PRICING_TABLE[model]
    prefix = model.split(":", 1)[0] if model else "default"
    return PRICING_TABLE.get(prefix, PRICING_TABLE["default"])


def estimate_cost_usd(model: str, tokens_in: int = 0, tokens_out: int = 0) -> float:
    pricing = _pricing_for_model(model)
    cost = (max(tokens_in, 0) / 1000.0 * pricing.input_usd_per_1k) + (max(tokens_out, 0) / 1000.0 * pricing.output_usd_per_1k)
    return round(cost, 6)


__all__ = ["ModelPricing", "PRICING_TABLE", "estimate_cost_usd"]
