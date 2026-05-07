# Codex Handoff

Current branch has completed the Runtime API v2, MCP foundation, and narrow Phase 6 rollback diagnostics work through these commits:

- `dbd0f07 Add Runtime API v2 MCP foundation`
- `184e448 Add remote MCP transports`
- `81ffdc1 Add MCP reconnect health controls`
- `537d81b Expose MCP tools in runtime registry`
- `e6afa81 Add Codex handoff notes`

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

Verified locally:

- `python -m pytest -q tests\test_runtime_api_v2.py tests\test_mcp_config.py tests\test_scheduler_api.py` -> `43 passed`
- `python -m py_compile src\nami_core\app.py src\nami_core\mcp_client.py src\nami_core\mcp_config.py src\nami_core\runtime_v2.py`
- `npm run build` in `nami-dashboard`
- `git diff --check`

Next recommended work:

- Continue Phase 6 from `docs/deepseek-tui-adaptation-plan.md`.
- Expand diagnostics selection beyond the narrow default checks and make runner configuration explicit.

Suggested prompt for Codex on VPS:

```text
อ่าน docs/codex-handoff.md และ docs/deepseek-tui-adaptation-plan.md แล้วทำ Phase 6 ต่อ: ทำ diagnostics runner configuration ให้ explicit และขยายการเลือก checks แบบปลอดภัย พร้อม tests และ commit
```
