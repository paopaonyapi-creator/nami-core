/** Nami Core TypeScript SDK — v0.12.0 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8092";

export interface WorkerInfo { name: string; actions: string[] }
export interface AuditEntry { worker: string; action: string; caller_ip: string; ok: boolean; latency_ms: number; timestamp: string }
export interface HealthResponse { status: string; service: string; workers: string[]; scheduler: Record<string, unknown>; timestamp: string }
export interface WorkersResponse { workers: WorkerInfo[] }
export type MetricsResponse = Record<string, number>
export interface AuditResponse { entries: AuditEntry[] }
export interface DispatchResponse { ok: boolean; output?: Record<string, unknown>; latency_ms?: number; error?: string }
export interface BatchItem { worker: string; action: string; payload?: Record<string, unknown> }
export interface BatchResult { worker: string; action: string; ok: boolean; output?: Record<string, unknown>; error?: string; latency_ms: number }
export interface BatchResponse { results: BatchResult[] }
export interface WorkerHealthResponse { worker: string; healthy: boolean | null; response?: Record<string, unknown>; error?: string; latency_ms: number; actions: string[]; message?: string }
export interface RateLimitResponse { worker: string; max_requests: number; window_seconds: number; active: boolean; current_hits: number }
export interface RuntimeHealthResponse { status: string; service: string; core_status: string; workers: string[]; tools: number; jobs: number; scheduler: Record<string, unknown>; timestamp: string }
export interface RuntimeTool { name: string; description: string; input_schema: Record<string, unknown>; output_schema: Record<string, unknown>; permission_level: string; timeout_seconds: number; audit_category: string; read_only: boolean; worker: string | null; action: string | null }
export interface RuntimeToolsResponse { tools: RuntimeTool[] }
export interface RuntimeJob { id: string; status: string; created_at: string; updated_at: string; requested_action: string; input_summary: string; progress_events: Record<string, unknown>[]; result?: Record<string, unknown> | null; error?: string | null; audit_entries: Record<string, unknown>[] }
export interface RuntimeJobsResponse { jobs: RuntimeJob[] }
export interface RuntimeToolInvokeResponse { ok: boolean; job: RuntimeJob; output?: Record<string, unknown>; latency_ms?: number }
export interface RuntimeToolInvokeRequest { worker: string; action: string; payload?: Record<string, unknown>; approved?: boolean }
export interface RuntimeRecoveryPreviewResponse { job_id: string; requested_action: string; manual_review_required: boolean; candidate_files: string[]; new_candidate_files: string[]; suggested_commands: string[]; restore_supported: boolean }
export interface RuntimeRecoveryRestoreResponse { ok: boolean; job_id: string; restored_files: string[]; errors: Record<string, unknown>[] }
export interface RuntimeRecoveryDiffFile { path: string; ok: boolean; diff: string; error: string }
export interface RuntimeRecoveryDiffResponse { ok: boolean; job_id: string; requested_action: string; files: RuntimeRecoveryDiffFile[] }
export interface RuntimeMcpServer { name: string; transport: string; command?: string | null; args: string[]; url?: string | null; env: Record<string, string>; enabled: boolean; tool_prefix?: string | null; tool_namespace: string; permission_level: string; status: string; status_detail: string }
export interface RuntimeMcpServersResponse { servers: RuntimeMcpServer[]; enabled: string[]; count: number; enabled_count: number }
export interface RuntimeMcpToolServer { server: string; tool_namespace: string; enabled: boolean; status: string; status_detail: string; tools: RuntimeTool[]; tool_count: number }
export interface RuntimeMcpToolsResponse { servers: RuntimeMcpToolServer[]; tools: RuntimeTool[]; tool_count: number; discovery_status: string }
export interface RuntimeMcpToolInvokeRequest { tool: string; payload?: Record<string, unknown>; approved?: boolean }

export class NamiClient {
  baseUrl: string;
  apiKey?: string;

  constructor(baseUrl: string = API_BASE, apiKey?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  private async fetchJson<T>(path: string, opts?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {};
    if (this.apiKey) headers["Authorization"] = `Bearer ${this.apiKey}`;
    if (opts?.body) headers["Content-Type"] = "application/json";
    const r = await fetch(`${this.baseUrl}${path}`, { ...opts, headers: { ...headers, ...Object.fromEntries(new Headers(opts?.headers || {}).entries()) } });
    return r.json();
  }

  async health(): Promise<HealthResponse> { return this.fetchJson<HealthResponse>("/health"); }
  async workers(): Promise<WorkersResponse> { return this.fetchJson<WorkersResponse>("/workers"); }
  async metrics(): Promise<MetricsResponse> { return this.fetchJson<MetricsResponse>("/metrics"); }
  async audit(limit = 50): Promise<AuditResponse> { return this.fetchJson<AuditResponse>(`/audit?limit=${limit}`); }
  async scheduler(): Promise<Record<string, unknown>> { return this.fetchJson("/scheduler"); }
  async workerHealth(name: string): Promise<WorkerHealthResponse> { return this.fetchJson(`/workers/${name}/health`); }
  async rateLimit(name: string): Promise<RateLimitResponse> { return this.fetchJson(`/workers/${name}/rate-limit`); }
  async runtimeHealth(): Promise<RuntimeHealthResponse> { return this.fetchJson<RuntimeHealthResponse>("/runtime/health"); }
  async runtimeTools(): Promise<RuntimeToolsResponse> { return this.fetchJson<RuntimeToolsResponse>("/runtime/tools"); }
  async runtimeJobs(): Promise<RuntimeJobsResponse> { return this.fetchJson<RuntimeJobsResponse>("/runtime/jobs"); }
  async runtimeMcpServers(): Promise<RuntimeMcpServersResponse> { return this.fetchJson<RuntimeMcpServersResponse>("/runtime/mcp/servers"); }
  async runtimeMcpTools(): Promise<RuntimeMcpToolsResponse> { return this.fetchJson<RuntimeMcpToolsResponse>("/runtime/mcp/tools"); }
  async runtimeJob(jobId: string): Promise<RuntimeJob> { return this.fetchJson<RuntimeJob>(`/runtime/jobs/${encodeURIComponent(jobId)}`); }
  async runtimeRecoveryPreview(jobId: string): Promise<RuntimeRecoveryPreviewResponse> { return this.fetchJson<RuntimeRecoveryPreviewResponse>(`/runtime/jobs/${encodeURIComponent(jobId)}/recovery/preview`); }
  async runtimeRecoveryDiff(jobId: string): Promise<RuntimeRecoveryDiffResponse> { return this.fetchJson<RuntimeRecoveryDiffResponse>(`/runtime/jobs/${encodeURIComponent(jobId)}/recovery/diff`); }
  async runtimeRecoveryRestore(jobId: string): Promise<RuntimeRecoveryRestoreResponse> { return this.fetchJson<RuntimeRecoveryRestoreResponse>(`/runtime/jobs/${encodeURIComponent(jobId)}/recovery/restore`, { method: "POST" }); }
  async runtimeToolInvoke(request: RuntimeToolInvokeRequest): Promise<RuntimeToolInvokeResponse> {
    return this.fetchJson<RuntimeToolInvokeResponse>("/runtime/tools/invoke", {
      method: "POST",
      body: JSON.stringify({ ...request, payload: request.payload || {}, approved: request.approved || false }),
    });
  }
  async runtimeMcpToolInvoke(request: RuntimeMcpToolInvokeRequest): Promise<RuntimeToolInvokeResponse> {
    return this.fetchJson<RuntimeToolInvokeResponse>("/runtime/mcp/tools/invoke", {
      method: "POST",
      body: JSON.stringify({ ...request, payload: request.payload || {}, approved: request.approved || false }),
    });
  }
  runtimeEvents(): EventSource { return new EventSource(`${this.baseUrl}/runtime/events`); }

  async dispatch(worker: string, action: string, payload?: Record<string, unknown>): Promise<DispatchResponse> {
    return this.fetchJson<DispatchResponse>("/dispatch", {
      method: "POST",
      body: JSON.stringify({ worker, action, payload: payload || {} }),
    });
  }

  async batchDispatch(items: BatchItem[]): Promise<BatchResponse> {
    return this.fetchJson<BatchResponse>("/dispatch/batch", {
      method: "POST",
      body: JSON.stringify({ items }),
    });
  }

  events(): EventSource {
    return new EventSource(`${this.baseUrl}/events`);
  }
}
