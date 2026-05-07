# DeepSeek TUI Adaptation Plan for Nami

## Goal

Use `Hmbown/DeepSeek-TUI` as an architecture reference for improving Nami's agent runtime, dashboard control surface, and tool execution system without importing the full Rust TUI stack into production.

## Decision

Do not vendor or embed the full `DeepSeek-TUI` project into Nami right now.

Use it as a blueprint for these Nami-native systems instead:

- Runtime API
- Tool registry
- Execution policy
- Persistent task queue
- MCP integration
- Live event streaming
- Rollback and diagnostics flow

## Why Not Import the Whole Project

`DeepSeek-TUI` is a Rust terminal coding agent. Nami currently uses a Python backend and a Next.js dashboard. Importing the whole project would add a second runtime stack, more deployment complexity, and a larger operational surface before Nami needs it.

The useful parts are mostly architectural patterns, not the terminal UI itself.

## Reference Features to Adapt

### 1. Runtime API

DeepSeek TUI exposes an app server style API around threads, prompts, tools, jobs, and health checks.

Nami should add a `Runtime API v2` with endpoints shaped around:

- `GET /runtime/health`
- `POST /runtime/threads`
- `GET /runtime/threads/{thread_id}`
- `POST /runtime/threads/{thread_id}/messages`
- `GET /runtime/jobs`
- `GET /runtime/jobs/{job_id}`
- `POST /runtime/tools/invoke`
- `GET /runtime/events`

The dashboard should consume this via SSE or WebSocket for live status.

### 2. Tool Registry

Create a central registry for all executable Nami actions.

Each tool should define:

- Name
- Description
- Input schema
- Output schema
- Required permission level
- Timeout
- Audit category
- Whether it is read-only or mutating

This should replace scattered action handling over time.

### 3. Execution Policy

Add a policy layer before any tool runs.

Policy should decide:

- Allow immediately
- Require API key
- Require explicit approval
- Deny

Initial policy categories:

- `read_only`
- `protected_read`
- `mutating`
- `dangerous`
- `admin_only`

This should be enforced server-side, not only in the dashboard.

### 4. Persistent Task Queue

Long-running Nami work should become durable jobs.

A job should keep:

- Job ID
- Status
- Created time
- Updated time
- Requested action
- Input summary
- Progress events
- Result or error
- Associated audit entries

The dashboard should show job progress and allow refresh after restart.

### 5. Live Event Stream

Add a consistent event envelope for SSE/WebSocket.

Suggested event shape:

```json
{
  "type": "job.updated",
  "timestamp": "2026-05-06T00:00:00Z",
  "job_id": "job_123",
  "data": {}
}
```

Important event types:

- `runtime.ready`
- `worker.health.updated`
- `tool.started`
- `tool.output`
- `tool.completed`
- `tool.failed`
- `job.created`
- `job.updated`
- `job.completed`
- `job.failed`
- `approval.required`

### 6. MCP Integration

Add MCP support after the runtime and tool registry are stable.

Phase 1:

- Nami acts as an MCP client.
- Nami can discover external MCP tools.
- Discovered tools are shown in the dashboard.

Phase 2:

- Nami exposes selected Nami tools as an MCP server.
- Other agents can call Nami through MCP.

### 7. Rollback Snapshots

For mutating actions, add a lightweight snapshot flow.

Initial scope:

- Git worktree status before action
- Files changed by action
- Tool output
- Post-action verification result

Later scope:

- Side snapshot storage
- One-click restore for safe file changes
- Dashboard diff preview

### 8. Diagnostics Loop

After code-editing actions, run relevant diagnostics and attach results to the job.

Examples:

- Python: `pytest`, `ruff`, `mypy` when configured
- Dashboard: `npm run build`, lint when configured
- TypeScript diagnostics from build output

The dashboard should display diagnostics as structured results instead of raw logs only.

## Implementation Phases

### Phase 1: Runtime API v2 Foundation

Deliverables:

- Add runtime router/module
- Add health endpoint
- Add thread/job data models
- Add event envelope model
- Add dashboard API client wrapper

Acceptance checks:

- Runtime health endpoint returns `200`
- Dashboard can fetch runtime status
- Existing dashboard/API behavior remains working

### Phase 2: Tool Registry

Deliverables:

- Define tool metadata schema
- Register existing worker actions through the registry
- Add `/runtime/tools` list endpoint
- Add `/runtime/tools/invoke` endpoint
- Record audit events for every invocation

Acceptance checks:

- Existing dispatch still works
- Registered tools are visible in dashboard
- Protected tools reject unauthenticated requests

### Phase 3: Persistent Jobs

Deliverables:

- Add job storage
- Convert long-running actions to jobs
- Add job list/detail endpoints
- Stream job updates to dashboard

Acceptance checks:

- Job survives service restart if storage is enabled
- Dashboard shows queued/running/completed/failed states
- Errors are visible and actionable

### Phase 4: Dashboard Control UX

Deliverables:

- Add runtime status panel
- Add jobs panel
- Add tool explorer panel
- Add approval-required UI state
- Improve event log filtering

Acceptance checks:

- User can inspect tools before running them
- User can track job progress live
- Protected/mutating actions are visibly separated

### Phase 5: MCP Client

Deliverables:

- Add MCP config format
- Add MCP server discovery
- Add MCP tool listing
- Expose MCP tools through Nami tool registry

Acceptance checks:

- Nami can connect to at least one local MCP server
- Discovered MCP tools appear in dashboard
- MCP tool invocation is policy-gated

### Phase 6: Rollback and Diagnostics

Deliverables:

- Add pre/post action snapshots for mutating tools
- Attach diagnostic results to jobs
- Add dashboard diff/result view

Acceptance checks:

- Mutating action records changed files
- Failed diagnostics are visible in dashboard
- User can see enough context to recover safely

## Suggested First Task

Start with Phase 1 and Phase 2 together in a narrow form:

- Create `Runtime API v2` module
- Add `ToolRegistry`
- Register only current safe/read-only actions first
- Wire dashboard to display runtime/tool status

This gives Nami a clean foundation without disrupting current production behavior.

## Implementation Status

Completed narrow Runtime API v2 foundation on 2026-05-06:

- Added `nami_core.runtime_v2` primitives for runtime events, tool metadata, execution policy, tool registry, and runtime jobs.
- Added Runtime API v2 endpoints under `/runtime/*` for health, tool listing, tool invocation, jobs, and events.
- Registered existing Hermes worker actions as runtime tools with policy classification for read-only, protected-read, mutating, and dangerous actions.
- Persisted runtime jobs in a narrow JSON-backed store when `NAMI_RUNTIME_JOBS_FILE` is configured.
- Added server-side approval enforcement for mutating runtime tool invokes and denial for dangerous/admin tools.
- Added buffered runtime job events through `/runtime/events` and WebSocket `runtime.event` broadcasts.
- Added dashboard Runtime API v2 panel with runtime status, registered tools, staged mutating-tool approval, recent jobs, and live event feed.
- Added TypeScript SDK helpers for Runtime API v2.
- Added YAML-backed MCP config loading and validation for `stdio`, `sse`, and `websocket` server definitions, plus `config/mcp_servers.example.yaml`.
- Added `/runtime/mcp/servers` discovery for configured MCP servers with safe config-level status reporting.
- Added `nami_core.mcp_client` with live `stdio` MCP JSON-RPC sessions for `initialize`, `tools/list`, and `tools/call`.
- Replaced the `/runtime/mcp/tools` skeleton with live `stdio`, `sse`, and `websocket` discovery, per-server connection status, and discovered tool metadata.
- Added `/runtime/mcp/tools/invoke` for policy-gated MCP tool calls with runtime jobs, audit entries, buffered events, and WebSocket `runtime.event` broadcasts.
- Added dashboard and TypeScript SDK support for discovered MCP tool counts, server status, tool selection, and MCP invocation.
- Added MCP server health fields with last-check timestamps, failure counts, retry scheduling, and explicit reconnect support.
- Added dashboard MCP lifecycle controls for reconnecting enabled servers and surfacing failure/retry status.
- Exposed discovered MCP tools through `/runtime/tools` so worker and MCP tools share one runtime registry surface.
- Added regression coverage for Runtime API v2, MCP config loading, MCP `stdio`, `sse`, and `websocket` discovery/invocation, protected MCP tool policy enforcement, MCP reconnect/health reporting, and central MCP tool listing.

Remaining next work:

- Continue Phase 6 rollback snapshots and diagnostics when mutating tool execution needs recovery support.

## Notes

`DeepSeek-TUI` is MIT licensed, so code reuse is legally possible if attribution is preserved. Still, the preferred path is to reimplement the relevant architecture in Nami's existing stack first.
