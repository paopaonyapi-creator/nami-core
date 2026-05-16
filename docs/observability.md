# Observability Bedrock

Phase 26.2 adds local-only Tempo, Loki, Prometheus, and Grafana wiring for Nami Core runtime observability.

## Stack

Run the stack from the `nami-core` directory:

```bash
docker compose -f docker-compose.obs.yml up -d
```

All externally exposed observability ports bind to `127.0.0.1`:

- Prometheus: `127.0.0.1:9090`
- Loki: `127.0.0.1:3100`
- Tempo: `127.0.0.1:3200`
- OTLP HTTP: `127.0.0.1:4318`
- Grafana: `127.0.0.1:3000`

Grafana provisions Prometheus, Loki, Tempo, and the Nami dashboards from `obs/grafana/provisioning`.

## Runtime configuration

Set OTLP for `nami-core` and `nami-worker` when the stack is running:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318/v1/traces
OTEL_SERVICE_NAME=nami-core
```

Without `OTEL_EXPORTER_OTLP_ENDPOINT`, OpenTelemetry initialization is a no-op and runtime code continues without exporting spans.

## Cost metrics

Cost spans attach these attributes when available:

- `model.requested`
- `tokens.in`
- `tokens.out`
- `cost.usd`
- `nami.role`

The Prometheus endpoint also exposes in-process counters used by the dashboards:

- `nami_cost_usd_total{role="..."}`
- `nami_tokens_in_total{role="..."}`
- `nami_tokens_out_total{role="..."}`
- `nami_cost_spans_total{role="..."}`

## Validation

Local validation:

```bash
python -m pytest tests/obs tests/test_inference_gateway.py tests/test_runtime_api_v2.py -q
python -m pytest -q
```

Production validation from the Phase 26.2 plan:

- Submit a queued job and verify Tempo shows a span tree with `cost.usd`.
- Verify Grafana `cost-by-role` renders the last 24h cost metrics.
- Verify `tier-triggers` dashboard panels are green.
- Verify Loki query `{service="nami-worker"} |= "ERROR"` returns recent worker logs.
- Verify external port scan for `3000`, `3100`, and `9090` is closed.

## Rollback

```bash
docker compose -f docker-compose.obs.yml down
```

Remove `OTEL_*` variables from `nami-core` and `nami-worker`; the SDK remains no-op without the endpoint.
