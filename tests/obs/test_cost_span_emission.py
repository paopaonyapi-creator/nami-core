"""Tests for cost span emission."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from nami_core.runtime.obs.cost_span import cost_metrics_prometheus_lines, cost_span, record_cost_metric, reset_cost_metrics
from nami_core.runtime.obs.pricing import estimate_cost_usd


def test_estimate_cost_usd_known_model():
    assert estimate_cost_usd("openai:gpt-4o-mini", tokens_in=1000, tokens_out=1000) == 0.00075


def test_cost_span_emits_attributes():
    reset_cost_metrics()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    previous_provider = trace._TRACER_PROVIDER
    trace._TRACER_PROVIDER = provider
    try:
        with cost_span("test.cost", model="openai:gpt-4o-mini", tokens_in=1000, tokens_out=1000, role="tester"):
            pass
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = spans[0].attributes
        assert attrs["model.requested"] == "openai:gpt-4o-mini"
        assert attrs["tokens.in"] == 1000
        assert attrs["tokens.out"] == 1000
        assert attrs["cost.usd"] == 0.00075
        assert attrs["nami.role"] == "tester"
    finally:
        trace._TRACER_PROVIDER = previous_provider
        reset_cost_metrics()


def test_cost_metrics_prometheus_lines_record_role_totals():
    reset_cost_metrics()
    try:
        record_cost_metric("inference", "openai:gpt-4o-mini", tokens_in=1000, tokens_out=1000)
        lines = "\n".join(cost_metrics_prometheus_lines())
        assert 'nami_cost_usd_total{role="inference"} 0.00075' in lines
        assert 'nami_tokens_in_total{role="inference"} 1000' in lines
        assert 'nami_tokens_out_total{role="inference"} 1000' in lines
        assert 'nami_cost_spans_total{role="inference"} 1' in lines
    finally:
        reset_cost_metrics()
