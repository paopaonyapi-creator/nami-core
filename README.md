# Nami Core

Unified agentic system: Hermes brain + Harness control layer + worker plugins.

## Core model

```text
Hermes = brain / agentic workforce
Nami Harness = rails / brakes / sensors / quality system
Nami Workers = pluggable task handlers, each harnessed
```

## Architecture

```text
User / Task request
  -> Hermes plans and routes
  -> Harness rails authorize scope
  -> Worker executes task
  -> Harness quality validates output
  -> Harness sensors record trace
  -> Harness brakes can stop execution
  -> result shipped only if quality passes
```

## Packages

- `nami_harness` — Rails, brakes, sensors, quality, runtime (v0.1.0)
- `nami_core` — Hermes router, config loader, secrets, database
- `nami_workers` — Pluggable workers (signal, proxy, lottery, trading, etc.)

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
```

## Status

Phase 0 — Foundation. Harness v0.1.0 integrated, Hermes router and config loading implemented.
