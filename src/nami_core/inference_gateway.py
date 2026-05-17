from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from nami_core.runtime.obs import cost_span, record_cost_metric
from nami_core.runtime.obs.pricing import estimate_cost_usd

logger = logging.getLogger("nami_core.inference_gateway")


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
    enabled: bool = False  # T4: feature flag — must be explicitly enabled
    dry_run: bool = True   # T6: log requests but don't call API
    max_concurrent: int = 3  # T7: concurrency semaphore cap

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
    enabled = bool(raw.get("enabled", False))
    if "NAMI_REAL_INFERENCE_ENABLED" in os.environ:
        enabled = os.environ["NAMI_REAL_INFERENCE_ENABLED"].lower() in {"true", "1", "yes"}
    dry_run = bool(raw.get("dry_run", True))
    max_concurrent = int(raw.get("max_concurrent", 3))
    if "NAMI_MAX_PARALLEL_INFERENCES" in os.environ:
        max_concurrent = int(os.environ["NAMI_MAX_PARALLEL_INFERENCES"])
    return InferencePolicy(
        routes=routes,
        fallback_order=[str(item) for item in fallback] if isinstance(fallback, list) else [],
        cache=cache if isinstance(cache, dict) else {},
        enabled=enabled,
        dry_run=dry_run,
        max_concurrent=max(1, max_concurrent),
    )


_INFERENCE_METRICS: dict[str, dict[Any, Any]] = {
    "requests_total": {},
    "failures_total": {},
    "cost_estimate_usd": {},
    "latency_seconds": {},
    "timeout_total": {}
}

def inference_metrics_prometheus_lines() -> list[str]:
    lines = [
        "# TYPE nami_inference_requests_total counter",
        "# TYPE nami_inference_failures_total counter",
        "# TYPE nami_inference_cost_estimate_usd counter",
        "# TYPE nami_inference_timeout_total counter",
        "# TYPE nami_inference_latency_seconds_avg gauge"
    ]
    for model, count in _INFERENCE_METRICS["requests_total"].items():
        lines.append(f'nami_inference_requests_total{{model="{model}"}} {count}')
    for (model, reason), count in _INFERENCE_METRICS["failures_total"].items():
        lines.append(f'nami_inference_failures_total{{model="{model}",reason="{reason}"}} {count}')
    for model, cost in _INFERENCE_METRICS["cost_estimate_usd"].items():
        lines.append(f'nami_inference_cost_estimate_usd{{model="{model}"}} {cost:.6f}')
    for model, count in _INFERENCE_METRICS["timeout_total"].items():
        lines.append(f'nami_inference_timeout_total{{model="{model}"}} {count}')
    for model, lat_data in _INFERENCE_METRICS["latency_seconds"].items():
        avg = lat_data["sum"] / lat_data["count"] if lat_data["count"] > 0 else 0.0
        lines.append(f'nami_inference_latency_seconds_avg{{model="{model}"}} {avg:.3f}')
    return lines


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
    # Hard cap on per-model rolling-stats entries. Prevents an attacker
    # (or misconfigured client) sending random model strings from filling
    # _call_stats unbounded. 100 distinct models is well above any realistic
    # T1 deployment; eviction is FIFO insertion-order on overflow.
    _STATS_CAP = 100

    def __init__(self, policy: InferencePolicy | None = None) -> None:
        self.policy = policy or load_inference_policy()
        # Per-model rolling cost+latency window for D10/D11 anomaly detection.
        # Process-local; fine for T1 single-node. Resets on restart.
        # Type kept as `Any` to avoid importing `nami_core.agent.safety_metrics`
        # at module load (circular: agent.planner imports this module).
        self._call_stats: dict[str, Any] = {}
        # T7: concurrency limiter — prevents burst API spend.
        self._semaphore = threading.Semaphore(self.policy.max_concurrent)
        self._dry_run_counter = 0
        self._hourly_spend = 0.0
        self._spend_hour = datetime.now(timezone.utc).hour

    def _stats_for(self, model: str):
        from nami_core.agent.safety_metrics import InferenceCallStats

        stats = self._call_stats.get(model)
        if stats is None:
            stats = InferenceCallStats()
            self._call_stats[model] = stats
            # Bounded: evict oldest (FIFO) if we crossed the cap. Python 3.7+
            # dicts preserve insertion order; popitem(last=False)-equivalent
            # is iter(...).__next__().
            if len(self._call_stats) > self._STATS_CAP:
                oldest = next(iter(self._call_stats))
                self._call_stats.pop(oldest, None)
        return stats

    def complete(self, request: InferenceRequest) -> InferenceResponse:
        if request.stream:
            raise ValueError("streaming inference is not supported by this endpoint")

        # T4: feature flag — block all inference when disabled
        if not self.policy.enabled:
            logger.warning("inference BLOCKED: policy.enabled=false (model=%s)", request.model)
            raise RuntimeError(
                "inference is disabled via feature flag (inference_policy.yaml enabled: false). "
                "Set enabled: true and restart to allow LLM calls."
            )

        _INFERENCE_METRICS["requests_total"][request.model] = _INFERENCE_METRICS["requests_total"].get(request.model, 0) + 1

        # Budget check
        current_hour = datetime.now(timezone.utc).hour
        if current_hour != self._spend_hour:
            self._hourly_spend = 0.0
            self._spend_hour = current_hour
        
        max_cost = float(os.environ.get("NAMI_MAX_COST_PER_HOUR", 9999.0))
        if self._hourly_spend >= max_cost:
            logger.warning("inference budget exceeded: $%.2f >= $%.2f", self._hourly_spend, max_cost)
            raise RuntimeError(f"ResourceExhausted: Hourly inference budget of ${max_cost:.2f} exceeded")

        traffic_pct = int(os.environ.get("NAMI_INFERENCE_TRAFFIC_PERCENT", 100))
        force_dry_run = self.policy.dry_run or (random.randint(1, 100) > traffic_pct)

        # T6: dry-run mode — log request, return stub response, no API call
        if force_dry_run:
            self._dry_run_counter += 1
            logger.info(
                "DRY-RUN #%d: would call model=%s, messages=%d, temp=%.1f (no API call made)",
                self._dry_run_counter, request.model, len(request.messages), request.temperature,
            )
            return InferenceResponse(
                content="[DRY-RUN] Inference is in dry-run mode. No API call was made.",
                model_used=f"dry-run:{request.model}",
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                latency_ms=0,
                cached=False,
            )

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

        # T7: concurrency limiter — block if too many parallel calls
        acquired = self._semaphore.acquire(timeout=30)
        if not acquired:
            raise RuntimeError(
                f"inference concurrency limit ({self.policy.max_concurrent}) exceeded; "
                f"request for model={request.model} timed out waiting for a slot"
            )
        try:
            started = time.monotonic()
            with cost_span("nami.llm.chat", role="inference", model=request.model, attributes={"model.requested": request.model, "cache.hit": False}) as span:
                try:
                    with urllib.request.urlopen(http_request, timeout=90) as response:
                        data = json.loads(response.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    _INFERENCE_METRICS["failures_total"][(request.model, "http_error")] = _INFERENCE_METRICS["failures_total"].get((request.model, "http_error"), 0) + 1
                    detail = exc.read().decode("utf-8", errors="replace")[:500]
                    raise RuntimeError(f"inference backend HTTP {exc.code}: {detail}") from exc
                except TimeoutError as exc:
                    _INFERENCE_METRICS["failures_total"][(request.model, "timeout")] = _INFERENCE_METRICS["failures_total"].get((request.model, "timeout"), 0) + 1
                    _INFERENCE_METRICS["timeout_total"][request.model] = _INFERENCE_METRICS["timeout_total"].get(request.model, 0) + 1
                    raise RuntimeError(f"inference backend timeout: {exc}") from exc
                except (urllib.error.URLError, OSError) as exc:
                    _INFERENCE_METRICS["failures_total"][(request.model, "connection_error")] = _INFERENCE_METRICS["failures_total"].get((request.model, "connection_error"), 0) + 1
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
                
                self._hourly_spend += cost_usd
                _INFERENCE_METRICS["cost_estimate_usd"][request.model] = _INFERENCE_METRICS["cost_estimate_usd"].get(request.model, 0.0) + cost_usd
                lat_stats = _INFERENCE_METRICS["latency_seconds"].setdefault(request.model, {"sum": 0.0, "count": 0})
                lat_stats["sum"] += (latency_ms / 1000.0)
                lat_stats["count"] += 1

                record_cost_metric("inference", request.model, cost_usd=cost_usd, tokens_in=tokens_in, tokens_out=tokens_out)
                self._record_call_anomalies(request.model, cost_usd, latency_ms)
                return InferenceResponse(
                    content=content,
                    model_used=model_used,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    cached=False,
                )
        finally:
            self._semaphore.release()

    def _record_call_anomalies(self, model: str, cost_usd: float, latency_ms: int) -> None:
        """D10/D11: feed call into rolling stats; emit detections to the
        safety metric counter. Best-effort: any failure here is swallowed
        so the inference path never crashes on observability issues.
        """
        try:
            from nami_core.agent.safety_metrics import check_call_anomaly
            from nami_core.safety.runner import _emit as _emit_safety_metric

            stats = self._stats_for(model)
            stats.record(cost_usd=cost_usd, latency_ms=float(latency_ms))
            for det in check_call_anomaly(
                role=model, cost_usd=cost_usd, latency_ms=float(latency_ms), stats=stats
            ):
                _emit_safety_metric(det.pattern, det.action)
        except Exception as exc:  # noqa: BLE001 — observability never blocks inference
            logger.debug("call-anomaly recording failed: %s", exc)
            return


__all__ = ["InferenceGateway", "InferencePolicy", "InferenceRequest", "InferenceResponse", "InferenceRoute", "load_inference_policy", "inference_metrics_prometheus_lines"]
