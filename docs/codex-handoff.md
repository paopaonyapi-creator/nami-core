# Codex Handoff

Current branch has completed the Runtime API v2, MCP foundation, and narrow Phase 6 rollback diagnostics work through these commits:

- `dbd0f07 Add Runtime API v2 MCP foundation`
- `184e448 Add remote MCP transports`
- `81ffdc1 Add MCP reconnect health controls`
- `537d81b Expose MCP tools in runtime registry`
- `e6afa81 Add Codex handoff notes`
- `379ff85 Wire dashboard recovery preview endpoint`
- Add authenticated runtime recovery restore
- Add runtime recovery diff preview
- Add environment-specific diagnostics policies
- Add stale recovery candidate restore safeguards

Completed:

- Runtime API v2 health, tools, invoke, jobs, and events endpoints.
- Runtime jobs with JSON-backed persistence when `NAMI_RUNTIME_JOBS_FILE` is configured.
- Server-side execution policy for read-only, protected-read, mutating, dangerous, and admin-only tools.
- MCP config loading for `stdio`, `sse`, and `websocket` servers.
- Live MCP discovery/invocation with policy-gated jobs and audit entries.
- MCP health fields, reconnect endpoint, retry/backoff status, and dashboard reconnect controls.
- Discovered MCP tools exposed through `/runtime/tools` as part of the central runtime registry surface.
- Dashboard runtime panel support for tools, jobs, events, MCP status, MCP invocation, and reconnect.
- Approved mutating worker tool invokes capture pre/post git worktree snapshots and attach changed-file diagnostics to runtime job results and audit entries.
- Dashboard recent jobs show mutation diagnostics summaries with changed/new file counts and first changed path.
- Dashboard Runtime API v2 panel provides selectable mutation snapshot detail views with pre/post git status output.
- Mutating worker diagnostics include narrow Runtime API pytest and dashboard build runners when project files are present.
- Diagnostics runner selection is explicit through `NAMI_RUNTIME_DIAGNOSTIC_CHECKS` with unknown checks ignored and `none` disabling runners.
- Environment-specific diagnostics policies can be selected through `NAMI_RUNTIME_ENV` and `NAMI_RUNTIME_DIAGNOSTIC_POLICY_<ENV>`, with `NAMI_RUNTIME_DIAGNOSTIC_CHECKS` still taking priority.
- Deployment docs describe runtime diagnostics check selection for VPS/runtime operations.
- Mutation diagnostics include recovery metadata for manual review, candidate files, and safe inspection commands.
- Dashboard Runtime API v2 detail view fetches and shows recovery preview metadata without automatic restore.
- `/runtime/jobs/{job_id}/recovery/preview` exposes recovery metadata as a read-only API response with `restore_supported` enabled when candidate files exist.
- TypeScript SDK exposes `runtimeRecoveryPreview(jobId)` for dashboard and future clients.
- Authenticated recovery restore is available through `POST /runtime/jobs/{job_id}/recovery/restore`, emits runtime recovery events, records audit entries, and is exposed in the dashboard and TypeScript SDK.
- Read-only recovery diff preview is available through `GET /runtime/jobs/{job_id}/recovery/diff`, surfaced in the dashboard before restore, and exposed in the TypeScript SDK.
- Recovery restore rejects stale candidate files when the current worktree no longer reports those paths as changed.

Verified locally:

- `python -m pytest -q tests\test_runtime_api_v2.py tests\test_mcp_config.py tests\test_scheduler_api.py` -> `44 passed`
- `python -m py_compile src\nami_core\app.py src\nami_core\mcp_client.py src\nami_core\mcp_config.py src\nami_core\runtime_v2.py`
- `npm run build` in `nami-dashboard`
- `git diff --check`

Next recommended work:

- Phase 6 is complete in the current narrow scope.
- Future work can focus on operational hardening.

Suggested prompt for Codex on VPS:

```text
อ่าน docs/codex-handoff.md และ docs/deepseek-tui-adaptation-plan.md แล้วเลือกงานถัดไป: เพิ่ม authenticated one-click restore workflows หรือ environment-specific diagnostics policies พร้อม tests และ commit
```
