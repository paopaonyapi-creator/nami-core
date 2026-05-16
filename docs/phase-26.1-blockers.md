# Phase 26.1 Validation Notes

## Current gate status

- Phase 26.1 scoped validation passed:
  - `python -m py_compile src/nami_core/runtime/queue/worker.py src/nami_core/runtime/queue/redis_stream.py src/nami_core/runtime/queue/jobs_dao.py src/nami_core/app.py`
  - `$env:NAMI_WORKER='status'; python -m nami_core.runtime.queue.worker --dry-run` produced `worker ready`
  - `python -m pytest tests/runtime/queue tests/integration/test_backtest_async_path.py tests/test_runtime_api_v2.py tests/obs tests/test_inference_gateway.py -q` produced `53 passed, 5 skipped, 59 warnings`
- Phase 26.1 gap patch:
  - `src/nami_core/runtime/queue/worker.py` adds `--dry-run` and Windows-safe signal handling fallback
  - `src/nami_core/runtime/queue/jobs_dao.py` enforces the locked job lifecycle state machine before status updates
  - `src/nami_core/app.py` lets `/runtime/jobs/{job_id}` fall back to the queue-backed `jobs` table for async dispatch polling
  - `tests/runtime/queue/test_worker_cli.py` covers `worker ready`
  - `tests/runtime/queue/test_jobs_dao.py` covers legal and illegal state transitions
  - `tests/runtime/queue/test_queue_job_polling.py` covers queue job polling through the runtime jobs endpoint
  - `docs/async-queue.md` documents worker dry-run validation and state-machine guarding
- Full repository validation passed:
  - `python -m pytest -q` produced `297 passed, 5 skipped, 77 warnings`

## Resolved blocker

The full-suite gate was previously blocked by `tests/test_inference_gateway.py` after `tests/obs/test_cost_span_emission.py` left OpenTelemetry's global tracer provider in a recursive proxy state.

The isolation issue was fixed by restoring the raw `trace._TRACER_PROVIDER` value in the observability test. The gateway tests now pass in both minimal repro and full-suite order.

## Commit readiness

- `git diff --check` must pass before commit.
- Phase 26.1 patch is ready for a small scoped commit after final diff review.
