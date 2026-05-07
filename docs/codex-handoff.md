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

Verified locally:

- `python -m pytest -q tests\test_runtime_api_v2.py tests\test_mcp_config.py tests\test_scheduler_api.py` -> `43 passed`
- `python -m py_compile src\nami_core\app.py src\nami_core\mcp_client.py src\nami_core\mcp_config.py src\nami_core\runtime_v2.py`
- `npm run build` in `nami-dashboard`
- `git diff --check`

Next recommended work:

- Continue Phase 6 from `docs/deepseek-tui-adaptation-plan.md`.
- Add dashboard diff/result views for mutation snapshots and diagnostics.
- Add deeper diagnostics runners for configured Python and dashboard projects.

Suggested prompt for Codex on VPS:

```text
อ่าน docs/codex-handoff.md และ docs/deepseek-tui-adaptation-plan.md แล้วทำ Phase 6 ต่อ: เพิ่ม dashboard diff/result views สำหรับ snapshot diagnostics และเพิ่ม diagnostics runners แบบแคบ ๆ พร้อม tests และ commit
```
