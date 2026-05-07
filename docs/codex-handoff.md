# Codex Handoff

Current branch has completed the Runtime API v2 and MCP foundation work through these commits:

- `dbd0f07 Add Runtime API v2 MCP foundation`
- `184e448 Add remote MCP transports`
- `81ffdc1 Add MCP reconnect health controls`
- `537d81b Expose MCP tools in runtime registry`

Completed:

- Runtime API v2 health, tools, invoke, jobs, and events endpoints.
- Runtime jobs with JSON-backed persistence when `NAMI_RUNTIME_JOBS_FILE` is configured.
- Server-side execution policy for read-only, protected-read, mutating, dangerous, and admin-only tools.
- MCP config loading for `stdio`, `sse`, and `websocket` servers.
- Live MCP discovery/invocation with policy-gated jobs and audit entries.
- MCP health fields, reconnect endpoint, retry/backoff status, and dashboard reconnect controls.
- Discovered MCP tools exposed through `/runtime/tools` as part of the central runtime registry surface.
- Dashboard runtime panel support for tools, jobs, events, MCP status, MCP invocation, and reconnect.

Verified locally:

- `python -m pytest -q tests\test_runtime_api_v2.py tests\test_mcp_config.py tests\test_scheduler_api.py` -> `43 passed`
- `python -m py_compile src\nami_core\app.py src\nami_core\mcp_client.py src\nami_core\mcp_config.py src\nami_core\runtime_v2.py`
- `npm run build` in `nami-dashboard`
- `git diff --check`

Next recommended work:

- Continue Phase 6 from `docs/deepseek-tui-adaptation-plan.md`.
- Add rollback snapshots and diagnostics for mutating runtime tool execution.
- Start with a narrow implementation: capture pre/post git worktree status for approved mutating worker tool invokes, attach snapshot/diagnostic summary to the runtime job result and audit entries, then add focused tests in `tests/test_runtime_api_v2.py`.

Suggested prompt for Codex on VPS:

```text
อ่าน docs/codex-handoff.md และ docs/deepseek-tui-adaptation-plan.md แล้วทำ Phase 6 ต่อ: เพิ่ม rollback snapshots และ diagnostics สำหรับ mutating runtime tools แบบแคบ ๆ พร้อม tests และ commit
```
