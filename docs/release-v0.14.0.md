# nami-core v0.14.0

## Highlights

- New **Runtime API v2** (`/runtime/health`, `/runtime/tools`, `/runtime/jobs`, `/runtime/events`) inspired by the DeepSeek-TUI agent runtime architecture.
- **Tool registry + execution policy** classifies every Hermes worker action as `read_only`, `protected_read`, `mutating`, `dangerous`, or `admin_only`, with server-side enforcement before any tool runs.
- **Persistent runtime jobs** with optional JSON-backed storage (`NAMI_RUNTIME_JOBS_FILE`) so long-running work survives restarts.
- **MCP client** for `stdio`, `sse`, and `websocket` MCP servers, with discovery, policy-gated invocation, reconnect controls, and central exposure through `/runtime/tools`.
- **Phase 6 rollback diagnostics**: every approved mutating tool invoke captures pre/post git snapshots, attaches diagnostics (Runtime API pytest, dashboard build), and exposes recovery preview, diff, and authenticated restore through the dashboard and TypeScript SDK.

## Changes

### Added
- `src/nami_core/runtime_v2.py` — runtime events, tool metadata, execution policy, tool registry, jobs.
- `/runtime/health`, `/runtime/tools`, `/runtime/tools/invoke`, `/runtime/jobs`, `/runtime/jobs/{job_id}`, `/runtime/events`.
- `src/nami_core/mcp_config.py` and `config/mcp_servers.example.yaml` for declarative MCP server config (`stdio`, `sse`, `websocket`).
- `src/nami_core/mcp_client.py` — live MCP JSON-RPC sessions (`initialize`, `tools/list`, `tools/call`).
- `/runtime/mcp/servers`, `/runtime/mcp/tools`, `/runtime/mcp/tools/invoke`, `/runtime/mcp/reconnect` with health/retry status.
- Server-side approval enforcement for mutating runtime tool invokes; denial for dangerous/admin tools.
- Buffered runtime events through `/runtime/events` and WebSocket `runtime.event` broadcasts.
- Pre/post git worktree snapshots and changed-file diagnostics on approved mutating tool invokes.
- Diagnostics runners (Runtime API pytest, dashboard production build) selected through `NAMI_RUNTIME_DIAGNOSTIC_CHECKS`.
- Environment-specific diagnostics policies through `NAMI_RUNTIME_ENV` and `NAMI_RUNTIME_DIAGNOSTIC_POLICY_<ENV>`.
- Recovery metadata, manual-review flags, candidate file lists, and safe inspection commands attached to mutation diagnostics.
- `/runtime/jobs/{job_id}/recovery/preview` (read-only) and `/runtime/jobs/{job_id}/recovery/diff` for reviewing changes before restore.
- `/runtime/jobs/{job_id}/recovery/restore` (authenticated) with audit/event records and stale-candidate safety gate.
- Runtime recovery events broadcast through the WebSocket channel.
- Dashboard Runtime API v2 panel: tools list, jobs feed, mutation diagnostics summaries, snapshot detail view, recovery preview/diff/restore, MCP server status, MCP tool invocation, MCP reconnect.
- TypeScript SDK helpers: `runtimeHealth`, `runtimeTools`, `runtimeJobs`, `runtimeEvents`, `runtimeRecoveryPreview`, `runtimeRecoveryDiff`, `runtimeRecoveryRestore`, MCP helpers.
- Tests: `tests/test_runtime_api_v2.py` (772 lines), `tests/test_mcp_config.py` (67 lines).
- `docs/codex-handoff.md`, `docs/deepseek-tui-adaptation-plan.md`.

### Changed
- App version moved from 0.13.0 to 0.14.0.
- `pyproject.toml` version moved from 0.3.0 to 0.14.0 to match the runtime app version.
- Dashboard `page.tsx` extended (+462 lines) with Runtime API v2 + MCP control surface.
- Discovered MCP tools share `/runtime/tools` with worker tools (single registry surface).
- Test count moved from 225 to 258 (+33 tests).

## Upgrade Notes

- Runtime API v2 endpoints are additive — existing dispatch / workers / events behavior is unchanged.
- Mutating tool invokes that previously returned plain results now also return git snapshot + recovery metadata; clients can ignore unknown fields.
- MCP support is opt-in: no servers are configured by default. Copy `config/mcp_servers.example.yaml` to enable.
- Diagnostics runners are gated by `NAMI_RUNTIME_DIAGNOSTIC_CHECKS`. Default value runs `runtime_pytest,dashboard_build` only when project files are present; set to `none` to disable.

## Verification

- `python -m pytest` -> **258 passed** in ~43s.
- `python -m py_compile src/nami_core/app.py src/nami_core/runtime_v2.py src/nami_core/mcp_client.py src/nami_core/mcp_config.py` clean.
- `npm run build` in `nami-dashboard` clean.
- VPS endpoints verified after deploy: `/health`, `/workers`, `/runtime/health` all `200`.

## What's Next

- Operational hardening: monitor runtime job persistence in production, add log-aggregation hook for runtime events.
- Once 1+ external developer or paid user signal arrives, re-prioritize candidate items in `ROADMAP.md` v0.15.0+.
