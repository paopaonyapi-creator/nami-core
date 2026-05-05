# Contributing

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
python -m pytest
```

## Contribution areas

- Rails: policies, scopes, quotas, auth adapters.
- Brakes: kill switches, circuit breakers, budget stops.
- Sensors: traces, metrics, audit outputs.
- Quality: evals, replay, regression gates.

## Rules

- Add tests for behavior changes.
- Keep examples free of real credentials.
- Keep Hermes and Harness responsibilities separate.
