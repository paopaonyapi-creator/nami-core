from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from nami_core.runtime.obs import cost_span, record_cost_metric
from nami_core.runtime.obs.pricing import estimate_cost_usd


class InferenceRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False


class InferenceResponse(BaseModel):
    content: str
    model_used: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cached: bool = False


@dataclass(frozen=True)
class InferenceRoute:
    pattern: str
    backend: str
    budget_per_hour: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class InferencePolicy:
    routes: list[InferenceRoute]
    fallback_order: list[str] = field(default_factory=list)
    cache: dict[str, Any] = field(default_factory=dict)

    def backend_for(self, model: str) -> str:
        for route in self.routes:
            if fnmatch(model, route.pattern):
                return _expand_backend(route.backend)
        raise ValueError(f"no inference route for model: {model}")


def _expand_backend(value: str) -> str:
    expanded = os.path.expandvars(value)
    if "${MAXPLUS_URL}" in expanded:
        expanded = expanded.replace("${MAXPLUS_URL}", os.environ.get("MAXPLUS_URL", "http://127.0.0.1:5001"))
    return expanded


def _default_policy_path() -> Path:
    return Path(os.environ.get("NAMI_INFERENCE_POLICY_FILE", "config/inference_policy.yaml"))


def load_inference_policy(path: str | Path | None = None) -> InferencePolicy:
    policy_path = Path(path) if path else _default_policy_path()
    if not policy_path.exists():
        return InferencePolicy(
            routes=[
                InferenceRoute(pattern="ollama:*", backend="http://127.0.0.1:11434/v1/chat/completions"),
                InferenceRoute(pattern="maxplus:*", backend="${MAXPLUS_URL}/v1/chat/completions"),
            ],
            fallback_order=["ollama:qwen2.5:3b", "maxplus:default"],
            cache={"enabled": False},
        )
    with policy_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"inference policy must be a mapping: {policy_path}")
    routes_raw = raw.get("routes", [])
    if not isinstance(routes_raw, list):
        raise ValueError("inference policy routes must be a list")
    routes = []
    for route in routes_raw:
        if not isinstance(route, dict):
            raise ValueError("inference route must be a mapping")
        pattern = str(route.get("pattern") or "")
        backend = str(route.get("backend") or "")
        if not pattern or not backend:
            raise ValueError("inference route requires pattern and backend")
        budget = route.get("budget_per_hour") or {}
        routes.append(InferenceRoute(pattern=pattern, backend=backend, budget_per_hour=budget if isinstance(budget, dict) else {}))
    fallback = raw.get("fallback_order", [])
    cache = raw.get("cache", {})
    return InferencePolicy(
        routes=routes,
        fallback_order=[str(item) for item in fallback] if isinstance(fallback, list) else [],
        cache=cache if isinstance(cache, dict) else {},
    )


def _backend_model(model: str) -> str:
    if model.startswith("maxplus:default"):
        return os.environ.get("MAXPLUS_MODEL", "gpt-4o-mini")
    if ":" in model:
        return model.split(":", 1)[1]
    return model


def _auth_headers(backend: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if "api.openai.com" in backend and os.environ.get("OPENAI_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['OPENAI_API_KEY']}"
    if "maxplus" in backend.lower() and os.environ.get("MAXPLUS_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['MAXPLUS_API_KEY']}"
    return headers


def _usage_tokens(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") if isinstance(data, dict) else {}
    if not isinstance(usage, dict):
        return 0, 0
    tokens_in = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    tokens_out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return tokens_in, tokens_out


class InferenceGateway:
    def __init__(self, policy: InferencePolicy | None = None) -> None:
        self.policy = policy or load_inference_policy()

    def complete(self, request: InferenceRequest) -> InferenceResponse:
        if request.stream:
            raise ValueError("streaming inference is not supported by this endpoint")
        backend = self.policy.backend_for(request.model)
        payload = {
            "model": _backend_model(request.model),
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        http_request = urllib.request.Request(backend, data=body, headers=_auth_headers(backend), method="POST")
        started = time.monotonic()
        with cost_span("nami.llm.chat", role="inference", model=request.model, attributes={"model.requested": request.model, "cache.hit": False}) as span:
            try:
                with urllib.request.urlopen(http_request, timeout=90) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"inference backend HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, OSError) as exc:
                raise RuntimeError(f"inference backend unavailable: {exc}") from exc
            latency_ms = int((time.monotonic() - started) * 1000)
            choices = data.get("choices") if isinstance(data, dict) else []
            content = ""
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else {}
                if isinstance(message, dict):
                    content = str(message.get("content") or "")
            tokens_in, tokens_out = _usage_tokens(data)
            model_used = str(data.get("model") or request.model) if isinstance(data, dict) else request.model
            cost_usd = estimate_cost_usd(request.model, tokens_in=tokens_in, tokens_out=tokens_out)
            span.set_attribute("model.used", model_used)
            span.set_attribute("tokens.in", tokens_in)
            span.set_attribute("tokens.out", tokens_out)
            span.set_attribute("cost.usd", cost_usd)
            span.set_attribute("latency.ms", latency_ms)
            record_cost_metric("inference", request.model, cost_usd=cost_usd, tokens_in=tokens_in, tokens_out=tokens_out)
            return InferenceResponse(
                content=content,
                model_used=model_used,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                cached=False,
            )


__all__ = ["InferenceGateway", "InferencePolicy", "InferenceRequest", "InferenceResponse", "InferenceRoute", "load_inference_policy"]
