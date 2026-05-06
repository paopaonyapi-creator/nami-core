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
