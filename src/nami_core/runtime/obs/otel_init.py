"""OpenTelemetry initialization for Nami Core."""

from __future__ import annotations

import os
from functools import lru_cache

_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "nami-core")


@lru_cache(maxsize=1)
def configure_otel() -> bool:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        return False

    provider = trace.get_tracer_provider()
    if not endpoint:
        if provider.__class__.__name__ == "ProxyTracerProvider":
            trace.set_tracer_provider(TracerProvider(resource=Resource.create({"service.name": _SERVICE_NAME})))
        return False

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except Exception:
        return False

    if provider.__class__.__name__ == "ProxyTracerProvider":
        provider = TracerProvider(resource=Resource.create({"service.name": _SERVICE_NAME}))
        trace.set_tracer_provider(provider)

    if getattr(provider, "_nami_otlp_configured", False):
        return True

    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    setattr(provider, "_nami_otlp_configured", True)
    return True


def get_tracer(name: str = "nami-core"):
    try:
        from opentelemetry import trace
    except Exception:
        return _NoopTracer()
    configure_otel()
    return trace.get_tracer(name)


class _NoopSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def set_attribute(self, key: str, value):
        return None

    def record_exception(self, exc: BaseException):
        return None


class _NoopTracer:
    def start_as_current_span(self, name: str, **kwargs):
        return _NoopSpan()


__all__ = ["configure_otel", "get_tracer"]
