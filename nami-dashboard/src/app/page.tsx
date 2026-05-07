"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import {
  Activity, Cpu, Clock, Moon, Sun, RefreshCw, Zap, Send,
  BarChart3, Shield, Database, Heart, Layers, Radio, AlertCircle, BookOpen, Gauge, Network, CheckCircle, XCircle, Wrench, Briefcase,
} from "lucide-react";
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, Title, Tooltip, Legend, Filler,
} from "chart.js";
import { Line, Bar } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Title, Tooltip, Legend, Filler);

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8092";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8092/ws";

interface WorkerInfo { name: string; actions: string[] }
interface AuditEntry { worker: string; action: string; caller_ip: string; ok: boolean; latency_ms: number; timestamp: string }
interface WorkerHealth { worker: string; healthy: boolean | null; latency_ms: number; actions: string[]; message?: string }
interface BatchResult { worker: string; action: string; ok: boolean; latency_ms: number; error?: string }
interface SSEEvent { event: string; data: Record<string, unknown> }
interface RateLimitInfo { worker: string; max_requests: number; window_seconds: number; active: boolean; current_hits: number }
interface RuntimeHealth { status: string; service: string; tools: number; jobs: number; timestamp: string }
interface RuntimeTool { name: string; description: string; permission_level: string; timeout_seconds: number; audit_category: string; read_only: boolean; worker: string | null; action: string | null }
interface RuntimeRecovery { manual_review_required?: boolean; candidate_files?: string[]; new_candidate_files?: string[]; suggested_commands?: string[] }
interface RuntimeRecoveryPreview { job_id: string; requested_action: string; manual_review_required: boolean; candidate_files: string[]; new_candidate_files: string[]; suggested_commands: string[]; restore_supported: boolean }
interface RuntimeRecoveryRestore { ok: boolean; job_id: string; restored_files: string[]; errors: Record<string, unknown>[] }
interface RuntimeRecoveryDiffFile { path: string; ok: boolean; diff: string; error: string }
interface RuntimeRecoveryDiff { ok: boolean; job_id: string; requested_action: string; files: RuntimeRecoveryDiffFile[] }
interface RuntimeDiagnostics { ok?: boolean; changed_files?: string[]; new_changed_files?: string[]; resolved_files?: string[]; before_count?: number; after_count?: number; recovery?: RuntimeRecovery }
interface RuntimeJobResult { diagnostics?: RuntimeDiagnostics; snapshot?: { before?: Record<string, unknown>; after?: Record<string, unknown> }; [key: string]: unknown }
interface RuntimeJob { id: string; status: string; requested_action: string; updated_at: string; result?: RuntimeJobResult | null; error?: string | null; audit_entries?: Record<string, unknown>[] }
interface RuntimeStreamEvent { type: string; timestamp: string; job_id?: string | null; data?: Record<string, unknown> }
interface RuntimeMcpServer { name: string; transport: string; command?: string | null; args: string[]; url?: string | null; enabled: boolean; tool_namespace: string; permission_level: string; status: string; status_detail: string }
interface RuntimeMcpToolServer { server: string; tool_namespace: string; enabled: boolean; status: string; status_detail: string; last_checked_at?: string | null; failure_count?: number; next_retry_at?: string | null; tools: RuntimeTool[]; tool_count: number }

async function apiFetch<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  return r.json();
}

function MetricCard({ label, value, icon: Icon }: { label: string; value: string | number; icon: React.ElementType }) {
  return (
    <div className="card">
      <div className="flex items-center gap-2 text-sm text-dim">
        <Icon size={14} className="text-gold-dim" /> {label}
      </div>
      <div className="text-2xl font-bold mt-1 text-gold">{value}</div>
    </div>
  );
}

function WorkerHealthCards({ workers, onAlert }: { workers: WorkerInfo[]; onAlert: (msg: string) => void }) {
  const [healthMap, setHealthMap] = useState<Record<string, WorkerHealth>>({});
  const [loading, setLoading] = useState(true);

  const checkHealth = useCallback(async (ws: WorkerInfo[]) => {
    const results: Record<string, WorkerHealth> = {};
    const unhealthy: string[] = [];
    await Promise.all(ws.map(async w => {
      try {
        const r = await fetch(`${API_BASE}/workers/${w.name}/health`);
        if (r.ok) {
          const h: WorkerHealth = await r.json();
          results[w.name] = h;
          if (h.healthy === false) unhealthy.push(w.name);
        }
      } catch { /* skip */ }
    }));
    setHealthMap(results);
    if (unhealthy.length > 0) onAlert(`Unhealthy workers: ${unhealthy.join(", ")}`);
    return results;
  }, [onAlert]);

  useEffect(() => {
    const run = async () => { setLoading(true); await checkHealth(workers); setLoading(false); };
    if (workers.length > 0) run();
  }, [workers, checkHealth]);

  useEffect(() => {
    const id = setInterval(() => checkHealth(workers), 30000);
    return () => clearInterval(id);
  }, [workers, checkHealth]);

  return (
    <div className="card">
      <h2 className="card-title">
        <Heart size={16} /> Workers ({workers.length})
      </h2>
      {loading ? <div className="text-xs text-dim">Loading health...</div> : (
        <div className="flex flex-wrap gap-1">
          {workers.map(w => {
            const h = healthMap[w.name];
            const badge = h?.healthy === true ? "bg-green-900/30 text-green-400" : h?.healthy === false ? "bg-red-900/30 text-red-400" : "bg-gray-800 text-gray-400";
            const lat = h?.latency_ms ? `${h.latency_ms.toFixed(0)}ms` : "";
            return (
              <Link key={w.name} href={`/workers/${w.name}`} className={`chip ${badge} hover:opacity-80 cursor-pointer`} title={h?.message || lat}>
                {w.name} {lat && <span className="text-[10px] opacity-60">{lat}</span>}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DispatchPanel({ workers, apiKey }: { workers: WorkerInfo[]; apiKey: string }) {
  const [worker, setWorker] = useState("");
  const [action, setAction] = useState("");
  const [payload, setPayload] = useState("{}");
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const runDispatch = async () => {
    setLoading(true);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
      const r = await fetch(`${API_BASE}/dispatch`, {
        method: "POST",
        headers,
        body: JSON.stringify({ worker, action, payload: JSON.parse(payload) }),
      });
      setResult(JSON.stringify(await r.json(), null, 2));
    } catch (e) { setResult(`Error: ${e}`); }
    setLoading(false);
  };

  return (
    <div className="card">
      <h2 className="card-title">
        <Send size={16} /> Dispatch Test
      </h2>
      <div className="flex flex-col gap-2">
        <select value={worker} onChange={e => setWorker(e.target.value)} className="input-dark" title="Select worker" aria-label="Select worker">
          <option value="">Select worker...</option>
          {workers.map(w => <option key={w.name} value={w.name}>{w.name}</option>)}
        </select>
        <input placeholder="Action" value={action} onChange={e => setAction(e.target.value)} className="input-dark" aria-label="Action" />
        <textarea placeholder="{}" value={payload} onChange={e => setPayload(e.target.value)} rows={2} className="input-dark" aria-label="Payload JSON" />
        <button onClick={runDispatch} disabled={loading || !worker || !action} className="btn-gold">
          {loading ? "Running..." : "Run"}
        </button>
        {result && <pre className="mt-2 pre-dark">{result}</pre>}
      </div>
    </div>
  );
}

function AuditTable({ entries }: { entries: AuditEntry[] }) {
  return (
    <div className="card">
      <h2 className="card-title">
        <Shield size={16} /> Audit Trail
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="table-header">
            <th className="text-left py-1 px-2">Worker</th><th className="text-left py-1 px-2">Action</th>
            <th className="text-left py-1 px-2">OK</th><th className="text-left py-1 px-2">Latency</th>
            <th className="text-left py-1 px-2">Time</th>
          </tr></thead>
          <tbody>
            {entries.slice(0, 15).map((e, i) => (
              <tr key={i} className="border-b table-row-border">
                <td className="py-1 px-2">{e.worker}</td><td className="py-1 px-2">{e.action}</td>
                <td className="py-1 px-2">{e.ok ? "OK" : "Fail"}</td>
                <td className="py-1 px-2">{e.latency_ms?.toFixed(1) ?? "--"}ms</td>
                <td className="py-1 px-2 text-dim">{new Date(e.timestamp).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LatencyChart({ entries }: { entries: AuditEntry[] }) {
  const data = {
    labels: entries.slice(0, 30).map(e => new Date(e.timestamp).toLocaleTimeString()),
    datasets: [{ label: "Latency (ms)", data: entries.slice(0, 30).map(e => e.latency_ms), borderColor: "#D4AF37", backgroundColor: "rgba(212,175,55,0.1)", fill: true, tension: 0.4 }],
  };
  return (
    <div className="card">
      <h2 className="card-title">
        <BarChart3 size={16} /> Dispatch Latency
      </h2>
      <Line data={data} options={{ responsive: true, plugins: { legend: { display: false } }, scales: { x: { display: false } } }} />
    </div>
  );
}

function WorkerBarChart({ workers }: { workers: WorkerInfo[] }) {
  const data = {
    labels: workers.map(w => w.name),
    datasets: [{ label: "Actions", data: workers.map(w => w.actions.length), backgroundColor: "rgba(212,175,55,0.6)", borderColor: "#D4AF37", borderWidth: 1 }],
  };
  return (
    <div className="card">
      <h2 className="card-title">
        <Activity size={16} /> Worker Actions
      </h2>
      <Bar data={data} options={{ responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: "#888", font: { size: 9 } } }, y: { ticks: { color: "#888" } } } }} />
    </div>
  );
}

function BatchDispatchPanel({ apiKey }: { apiKey: string }) {
  const [items, setItems] = useState('[{"worker":"status","action":"health","payload":{}}]');
  const [results, setResults] = useState<BatchResult[] | null>(null);
  const [loading, setLoading] = useState(false);

  const runBatch = async () => {
    setLoading(true);
    try {
      const parsed = JSON.parse(items);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
      const r = await fetch(`${API_BASE}/dispatch/batch`, {
        method: "POST",
        headers,
        body: JSON.stringify({ items: parsed }),
      });
      const d = await r.json();
      setResults(d.results || []);
    } catch (e) { setResults([{ worker: "error", action: "", ok: false, latency_ms: 0, error: String(e) }]); }
    setLoading(false);
  };

  return (
    <div className="card">
      <h2 className="card-title">
        <Layers size={16} /> Batch Dispatch
      </h2>
      <div className="flex flex-col gap-2">
        <textarea placeholder='[{"worker":"status","action":"health"}]' value={items} onChange={e => setItems(e.target.value)} rows={3} className="input-dark font-mono text-xs" aria-label="Batch items JSON" />
        <button onClick={runBatch} disabled={loading} className="btn-gold">
          {loading ? "Running..." : "Run batch"}
        </button>
        {results && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="table-header">
                <th className="text-left py-1 px-2">Worker</th><th className="text-left py-1 px-2">Action</th>
                <th className="text-left py-1 px-2">OK</th><th className="text-left py-1 px-2">Latency</th>
              </tr></thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className="border-b table-row-border">
                    <td className="py-1 px-2">{r.worker}</td><td className="py-1 px-2">{r.action}</td>
                    <td className="py-1 px-2">{r.ok ? "OK" : "Fail"}</td>
                    <td className="py-1 px-2">{r.latency_ms?.toFixed(1) ?? "--"}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function SSEEventLog() {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/events`);
    es.addEventListener("connected", () => setConnected(true));
    es.addEventListener("ping", () => setConnected(true));
    es.addEventListener("dispatch", (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [{ event: "dispatch", data }, ...prev].slice(0, 20));
    });
    es.addEventListener("webhook", (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [{ event: "webhook", data }, ...prev].slice(0, 20));
    });
    es.onerror = () => setConnected(false);
    return () => es.close();
  }, []);

  return (
    <div className="card">
      <h2 className="card-title">
        <Radio size={16} /> SSE Events
        <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded ${connected ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}`}>
          {connected ? "LIVE" : "OFF"}
        </span>
      </h2>
      <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
        {events.length === 0 ? <div className="text-xs text-dim">Waiting for events...</div> : (
          events.map((e, i) => (
            <div key={i} className="text-xs font-mono flex gap-2">
              <span className="text-gold-dim">{e.event}</span>
              <span className="text-dim truncate">{JSON.stringify(e.data).slice(0, 80)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function WorkerTopologyCanvas({ workers, healthOk, wsState }: { workers: WorkerInfo[]; healthOk: boolean; wsState: "on" | "off" | "wait" }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rect.width, rect.height);

    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const radius = Math.min(rect.width, rect.height) * 0.33;
    const visibleWorkers = workers.slice(0, 18);
    const accent = healthOk ? "#27e0a3" : "#ff5f6d";

    ctx.lineWidth = 1;
    visibleWorkers.forEach((worker, index) => {
      const angle = (index / Math.max(visibleWorkers.length, 1)) * Math.PI * 2 - Math.PI / 2;
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;
      ctx.strokeStyle = "rgba(148, 163, 184, 0.22)";
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(x, y);
      ctx.stroke();

      ctx.fillStyle = worker.actions.length > 0 ? "#27e0a3" : "#94a3b8";
      ctx.beginPath();
      ctx.arc(x, y, 4 + Math.min(worker.actions.length, 8) * 0.45, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#cbd5e1";
      ctx.font = "11px Segoe UI, sans-serif";
      ctx.textAlign = x > centerX ? "left" : "right";
      ctx.fillText(worker.name, x + (x > centerX ? 9 : -9), y + 4);
    });

    const pulse = wsState === "on" ? 1 : wsState === "wait" ? 0.65 : 0.35;
    const gradient = ctx.createRadialGradient(centerX, centerY, 8, centerX, centerY, 58);
    gradient.addColorStop(0, accent);
    gradient.addColorStop(1, "rgba(15, 23, 42, 0)");
    ctx.fillStyle = gradient;
    ctx.globalAlpha = pulse;
    ctx.beginPath();
    ctx.arc(centerX, centerY, 58, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.fillStyle = "#0f172a";
    ctx.strokeStyle = accent;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(centerX, centerY, 34, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#f8fafc";
    ctx.font = "600 12px Segoe UI, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Nami Core", centerX, centerY - 2);
    ctx.fillStyle = "#94a3b8";
    ctx.font = "11px Segoe UI, sans-serif";
    ctx.fillText(`${workers.length} workers`, centerX, centerY + 14);
  }, [workers, healthOk, wsState]);

  return (
    <div className="card lg:col-span-2 canvas-card">
      <h2 className="card-title">
        <Network size={16} /> Live Worker Topology
      </h2>
      <canvas ref={canvasRef} className="topology-canvas" aria-label="Worker topology canvas" />
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-dim">
        <span>{workers.length} workers</span>
        <span>{workers.reduce((sum, worker) => sum + worker.actions.length, 0)} actions</span>
        <span>WS {wsState}</span>
      </div>
    </div>
  );
}
function RateLimitsPanel({ workers, apiKey }: { workers: WorkerInfo[]; apiKey: string }) {
  const [limits, setLimits] = useState<RateLimitInfo[]>([]);

  const fetchLimits = async () => {
    if (!apiKey) return;
    const results: RateLimitInfo[] = [];
    await Promise.all(workers.slice(0, 10).map(async w => {
      try {
        const r = await fetch(`${API_BASE}/workers/${w.name}/rate-limit`, {
          headers: { Authorization: `Bearer ${apiKey}` },
        });
        if (r.ok) results.push(await r.json());
      } catch { /* skip */ }
    }));
    setLimits(results);
  };

  return (
    <div className="card">
      <h2 className="card-title">
        <Gauge size={16} /> Rate Limits
      </h2>
      <div className="flex flex-col gap-2">
        <button onClick={fetchLimits} disabled={!apiKey} className="btn-gold text-xs">Check rate limits</button>
        {limits.length > 0 && (
          <div className="flex flex-col gap-1">
            {limits.map(l => {
              const pct = l.active ? Math.min((l.current_hits / l.max_requests) * 100, 100) : 0;
              const barColor = pct > 80 ? "bg-red-500" : pct > 50 ? "bg-yellow-500" : "bg-green-500";
              return (
                <div key={l.worker} className="flex items-center gap-2 text-xs">
                  <span className="w-20 truncate">{l.worker}</span>
                  <div className="flex-1 h-2 bg-gray-800 rounded overflow-hidden">
                    <div className={`h-full ${barColor} rounded`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-dim w-16 text-right">{l.current_hits}/{l.max_requests}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function QuickActionsPanel({ apiKey }: { apiKey: string }) {
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [loading, setLoading] = useState<"cache" | "flush" | null>(null);

  const runAction = async (kind: "cache" | "flush") => {
    if (!apiKey) {
      setStatus({ ok: false, message: "Enter an API key before running protected actions." });
      return;
    }
    setLoading(kind);
    try {
      const r = await fetch(`${API_BASE}${kind === "cache" ? "/cache" : "/cache/flush"}`, {
        method: kind === "cache" ? "GET" : "POST",
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      const data = await r.json().catch(() => ({}));
      setStatus({ ok: r.ok, message: r.ok ? JSON.stringify(data).slice(0, 180) : `Request failed (${r.status})` });
    } catch (e) {
      setStatus({ ok: false, message: String(e) });
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="card">
      <h2 className="card-title">
        <Database size={16} /> Quick Actions
      </h2>
      <div className="flex flex-col gap-2">
        <button className="btn-gold-dim" disabled={loading !== null} onClick={() => runAction("cache")}>
          {loading === "cache" ? "Checking..." : "Cache Stats"}
        </button>
        <button className="btn-gold-dim" disabled={loading !== null} onClick={() => runAction("flush")}>
          {loading === "flush" ? "Flushing..." : "Flush Cache"}
        </button>
        {status && (
          <div className={`action-result ${status.ok ? "action-result-ok" : "action-result-bad"}`}>
            {status.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
            <span>{status.message}</span>
          </div>
        )}
      </div>
    </div>
  );
}
function runtimeDiagnosticsSummary(job: RuntimeJob): { label: string; files: string[]; title: string } | null {
  const diagnostics = job.result?.diagnostics;
  if (!diagnostics) return null;
  const changed = diagnostics.changed_files || [];
  const fresh = diagnostics.new_changed_files || [];
  const resolved = diagnostics.resolved_files || [];
  return {
    label: `${diagnostics.after_count ?? changed.length} changed / ${fresh.length} new`,
    files: fresh.length ? fresh : changed,
    title: [`changed: ${changed.length}`, `new: ${fresh.length}`, `resolved: ${resolved.length}`].join(" | "),
  };
}

function runtimeSnapshotRaw(snapshot: Record<string, unknown> | undefined): string {
  const raw = snapshot?.raw;
  return typeof raw === "string" && raw.trim() ? raw : "No git status output";
}

function runtimeRecoveryPreview(recovery: RuntimeRecovery | RuntimeRecoveryPreview | undefined): { files: string[]; commands: string[]; restoreSupported: boolean } {
  return {
    files: recovery?.candidate_files || [],
    commands: recovery?.suggested_commands || [],
    restoreSupported: "restore_supported" in (recovery || {}) ? Boolean((recovery as RuntimeRecoveryPreview).restore_supported) : false,
  };
}

function RuntimePanel({ health, tools, jobs, mcpServers, apiKey, onRefresh }: { health: RuntimeHealth | null; tools: RuntimeTool[]; jobs: RuntimeJob[]; mcpServers: RuntimeMcpToolServer[]; apiKey: string; onRefresh: () => void }) {
  const readOnly = tools.filter(tool => tool.read_only).length;
  const latestJobs = jobs.slice(0, 5);
  const enabledMcpServers = mcpServers.filter(server => server.enabled).length;
  const runtimeTools = [...tools, ...mcpServers.flatMap(server => server.tools || [])];
  const mcpToolCount = mcpServers.reduce((sum, server) => sum + server.tool_count, 0);
  const [selectedTool, setSelectedTool] = useState("");
  const [payload, setPayload] = useState("{}");
  const [approvedTool, setApprovedTool] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [runtimeEvents, setRuntimeEvents] = useState<RuntimeStreamEvent[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [recoveryPreview, setRecoveryPreview] = useState<RuntimeRecoveryPreview | null>(null);
  const [restoreResult, setRestoreResult] = useState<RuntimeRecoveryRestore | null>(null);
  const [recoveryDiff, setRecoveryDiff] = useState<RuntimeRecoveryDiff | null>(null);
  const activeTool = runtimeTools.find(tool => tool.name === selectedTool) || null;
  const activeIsMcp = activeTool?.worker === "mcp";
  const needsApproval = activeTool?.permission_level === "mutating";
  const denied = activeTool?.permission_level === "dangerous" || activeTool?.permission_level === "admin_only";
  const selectedJob = jobs.find(job => job.id === selectedJobId) || latestJobs.find(job => job.result?.diagnostics) || latestJobs[0] || null;
  const selectedDiagnostics = selectedJob ? runtimeDiagnosticsSummary(selectedJob) : null;
  const selectedRecovery = runtimeRecoveryPreview(recoveryPreview || selectedJob?.result?.diagnostics?.recovery);

  useEffect(() => {
    if (!selectedJob?.id || !selectedJob.result?.diagnostics) {
      setRecoveryPreview(null);
      setRestoreResult(null);
      setRecoveryDiff(null);
      return;
    }
    let active = true;
    setRestoreResult(null);
    setRecoveryDiff(null);
    fetch(`${API_BASE}/runtime/jobs/${encodeURIComponent(selectedJob.id)}/recovery/preview`)
      .then(response => response.ok ? response.json() : null)
      .then((data: RuntimeRecoveryPreview | null) => {
        if (!active) return;
        setRecoveryPreview(data);
        if (data?.restore_supported) {
          fetch(`${API_BASE}/runtime/jobs/${encodeURIComponent(selectedJob.id)}/recovery/diff`)
            .then(response => response.ok ? response.json() : null)
            .then((diff: RuntimeRecoveryDiff | null) => { if (active) setRecoveryDiff(diff); })
            .catch(() => { if (active) setRecoveryDiff(null); });
        }
      })
      .catch(() => { if (active) setRecoveryPreview(null); });
    return () => { active = false; };
  }, [selectedJob?.id, selectedJob?.result?.diagnostics]);

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/runtime/events`);
    const pushEvent = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as RuntimeStreamEvent;
        setRuntimeEvents(prev => [data, ...prev].slice(0, 8));
        if (data.type === "job.completed" || data.type === "job.failed") onRefresh();
      } catch { /* skip malformed runtime event */ }
    };
    es.addEventListener("runtime.ready", pushEvent);
    es.addEventListener("tool.started", pushEvent);
    es.addEventListener("job.completed", pushEvent);
    es.addEventListener("job.failed", pushEvent);
    es.addEventListener("job.recovery_restored", pushEvent);
    es.addEventListener("job.recovery_failed", pushEvent);
    return () => es.close();
  }, [onRefresh]);

  const reconnectMcpServer = async (serverName: string) => {
    setLoading(true);
    try {
      const headers: Record<string, string> = {};
      if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
      const response = await fetch(`${API_BASE}/runtime/mcp/servers/${encodeURIComponent(serverName)}/reconnect`, { method: "POST", headers });
      const data = await response.json().catch(() => ({}));
      setResult(JSON.stringify(data, null, 2));
      if (response.ok) onRefresh();
    } catch (e) {
      setResult(`Error: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  const restoreSelectedJob = async () => {
    if (!selectedJob?.id || !selectedRecovery.restoreSupported || !apiKey) return;
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/runtime/jobs/${encodeURIComponent(selectedJob.id)}/recovery/restore`, { method: "POST", headers: { Authorization: `Bearer ${apiKey}` } });
      const data = await response.json().catch(() => ({}));
      setRestoreResult(data as RuntimeRecoveryRestore);
      setResult(JSON.stringify(data, null, 2));
      if (response.ok) onRefresh();
    } catch (e) {
      setResult(`Error: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  const invokeTool = async () => {
    if (!activeTool?.worker || !activeTool.action || denied) return;
    if (needsApproval && approvedTool !== activeTool.name) {
      setApprovedTool(activeTool.name);
      setResult("Approval staged. Review the tool and run again to confirm.");
      return;
    }
    setLoading(true);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
      const response = await fetch(`${API_BASE}${activeIsMcp ? "/runtime/mcp/tools/invoke" : "/runtime/tools/invoke"}`, {
        method: "POST",
        headers,
        body: JSON.stringify(activeIsMcp ? { tool: activeTool.name, payload: JSON.parse(payload), approved: needsApproval } : { worker: activeTool.worker, action: activeTool.action, payload: JSON.parse(payload), approved: needsApproval }),
      });
      const data = await response.json().catch(() => ({}));
      setResult(JSON.stringify(data, null, 2));
      if (response.ok) {
        setApprovedTool("");
        onRefresh();
      }
    } catch (e) {
      setResult(`Error: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card lg:col-span-2">
      <h2 className="card-title">
        <Wrench size={16} /> Runtime API v2
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 text-xs">
        <div className="runtime-stat"><span className="text-dim">Status</span><strong>{health?.status ?? "unknown"}</strong></div>
        <div className="runtime-stat"><span className="text-dim">Tools</span><strong>{tools.length}</strong></div>
        <div className="runtime-stat"><span className="text-dim">Read-only</span><strong>{readOnly}</strong></div>
        <div className="runtime-stat"><span className="text-dim">Jobs</span><strong>{jobs.length}</strong></div>
        <div className="runtime-stat"><span className="text-dim">MCP</span><strong>{enabledMcpServers}/{mcpServers.length}</strong></div>
        <div className="runtime-stat"><span className="text-dim">MCP tools</span><strong>{mcpToolCount}</strong></div>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-gold-dim mb-2"><Wrench size={13} /> Registered tools</div>
          <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
            {runtimeTools.slice(0, 12).map(tool => (
              <button key={tool.name} type="button" onClick={() => { setSelectedTool(tool.name); setApprovedTool(""); }} className={`runtime-row runtime-tool-row ${selectedTool === tool.name ? "runtime-row-active" : ""}`}>
                <span className="truncate">{tool.name}</span>
                <span className={tool.read_only ? "text-green-400" : tool.permission_level === "dangerous" ? "text-red-400" : "text-orange-400"}>{tool.permission_level}</span>
              </button>
            ))}
            {runtimeTools.length === 0 && <div className="text-xs text-dim">No tools registered</div>}
          </div>
          <div className="mt-3 flex flex-col gap-2">
            <textarea value={payload} onChange={e => setPayload(e.target.value)} rows={2} className="input-dark font-mono text-xs" aria-label="Runtime tool payload JSON" />
            <button onClick={invokeTool} disabled={loading || !activeTool || denied || (needsApproval && !apiKey)} className={needsApproval && approvedTool !== activeTool?.name ? "btn-gold-dim" : "btn-gold"}>
              {loading ? "Running..." : denied ? "Denied by policy" : needsApproval && approvedTool !== activeTool?.name ? "Approve tool" : "Run tool"}
            </button>
            {needsApproval && !apiKey && <div className="text-xs text-orange-400">API key required for mutating tools.</div>}
            {result && <pre className="pre-dark">{result}</pre>}
          </div>
        </div>
        <div>
          <div className="flex items-center gap-2 text-xs text-gold-dim mb-2"><Briefcase size={13} /> Recent jobs</div>
          <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
            {latestJobs.map(job => {
              const diagnostics = runtimeDiagnosticsSummary(job);
              return (
                <button key={job.id} type="button" onClick={() => setSelectedJobId(job.id)} className={`runtime-row runtime-job-row ${selectedJob?.id === job.id ? "runtime-row-active" : ""}`} title={diagnostics?.title || job.error || job.id}>
                  <div className="min-w-0 text-left">
                    <div className="truncate">{job.requested_action}</div>
                    {diagnostics && <div className="runtime-job-diagnostics truncate">{diagnostics.label}{diagnostics.files[0] ? ` - ${diagnostics.files[0]}` : ""}</div>}
                  </div>
                  <span className={job.status === "completed" ? "text-green-400" : job.status === "failed" ? "text-red-400" : "text-orange-400"}>{job.status}</span>
                </button>
              );
            })}
            {latestJobs.length === 0 && <div className="text-xs text-dim">No runtime jobs yet</div>}
          </div>
          {selectedJob && selectedJob.result?.diagnostics && (
            <div className="runtime-diagnostics-detail">
              <div className="flex items-center justify-between gap-2 text-xs text-gold-dim mb-2">
                <span className="truncate">{selectedJob.requested_action}</span>
                <span>{selectedDiagnostics?.label}</span>
              </div>
              <div className="runtime-diagnostics-grid">
                <pre>{runtimeSnapshotRaw(selectedJob.result.snapshot?.before)}</pre>
                <pre>{runtimeSnapshotRaw(selectedJob.result.snapshot?.after)}</pre>
              </div>
              {(selectedRecovery.files.length > 0 || selectedRecovery.commands.length > 0) && (
                <div className="runtime-recovery-preview">
                  {selectedRecovery.files.length > 0 && <div className="truncate">Review: {selectedRecovery.files.join(", ")}</div>}
                  {selectedRecovery.commands.length > 0 && <code>{selectedRecovery.commands.join(" | ")}</code>}
                  {(recoveryDiff?.files || []).map(file => <pre key={file.path} className="pre-dark">{file.diff || file.error || `No diff for ${file.path}`}</pre>)}
                  {selectedRecovery.restoreSupported && <button type="button" onClick={restoreSelectedJob} disabled={loading || !apiKey} className="btn-gold-dim">Restore files</button>}
                  {selectedRecovery.restoreSupported && !apiKey && <div className="text-xs text-orange-400">API key required to restore files.</div>}
                  {(restoreResult?.restored_files || []).length > 0 && <div className="truncate text-green-400">Restored: {restoreResult?.restored_files.join(", ")}</div>}
                </div>
              )}
            </div>
          )}
          <div className="mt-3">
            <div className="flex items-center gap-2 text-xs text-gold-dim mb-2"><Network size={13} /> MCP servers</div>
            <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
              {mcpServers.map(server => (
                <div key={server.server} className="runtime-row" title={`${server.status_detail}${server.next_retry_at ? ` | retry ${server.next_retry_at}` : ""}`}>
                  <span className="truncate">{server.tool_namespace}</span>
                  <span className="flex items-center gap-2">
                    <span className={server.status === "connected" ? "text-green-400" : server.status === "error" ? "text-red-400" : server.enabled ? "text-orange-400" : "text-dim"}>{server.status}{server.failure_count ? ` (${server.failure_count})` : ""}</span>
                    {server.enabled && <button type="button" className="runtime-icon-btn" onClick={() => reconnectMcpServer(server.server)} disabled={loading} title="Reconnect MCP server"><RefreshCw size={12} /></button>}
                  </span>
                </div>
              ))}
              {mcpServers.length === 0 && <div className="text-xs text-dim">No MCP servers configured</div>}
            </div>
          </div>
          <div className="mt-3">
            <div className="flex items-center gap-2 text-xs text-gold-dim mb-2"><Radio size={13} /> Runtime events</div>
            <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
              {runtimeEvents.map((event, index) => (
                <div key={`${event.timestamp}-${index}`} className="runtime-event-row">
                  <span className="truncate">{event.type}</span>
                  <span className="text-dim truncate">{event.job_id ?? "runtime"}</span>
                </div>
              ))}
              {runtimeEvents.length === 0 && <div className="text-xs text-dim">Waiting for runtime events...</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
function AlertToast({ message, onClose }: { message: string; onClose: () => void }) {
  if (!message) return null;
  return (
    <div className="fixed bottom-4 right-4 bg-red-900/90 text-red-200 px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 z-50 text-sm">
      <AlertCircle size={16} />
      <span>{message}</span>
      <button onClick={onClose} className="ml-2 text-red-400 hover:text-white" aria-label="Dismiss alert">Close</button>
    </div>
  );
}

export default function Dashboard() {
  const [dark, setDark] = useState(true);
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
  const [runtimeTools, setRuntimeTools] = useState<RuntimeTool[]>([]);
  const [runtimeJobs, setRuntimeJobs] = useState<RuntimeJob[]>([]);
  const [runtimeMcpServers, setRuntimeMcpServers] = useState<RuntimeMcpToolServer[]>([]);
  const [wsState, setWsState] = useState<"on" | "off" | "wait">("wait");
  const [lastUpdate, setLastUpdate] = useState("--");
  const [healthOk, setHealthOk] = useState(false);
  const [alert, setAlert] = useState("");
  const [apiKey, setApiKey] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async () => {
    try {
      const h = await apiFetch<{ status: string; workers: string[] }>("/health");
      const w = await apiFetch<{ workers: WorkerInfo[] }>("/workers");
      const m = await apiFetch<Record<string, number>>("/metrics");
      const a = await apiFetch<{ entries: AuditEntry[] }>("/audit");
      const rh = await apiFetch<RuntimeHealth>("/runtime/health");
      const rt = await apiFetch<{ tools: RuntimeTool[] }>("/runtime/tools");
      const rj = await apiFetch<{ jobs: RuntimeJob[] }>("/runtime/jobs");
      const rms = await apiFetch<{ servers: RuntimeMcpToolServer[] }>("/runtime/mcp/tools");
      setHealthOk(h.status === "ok");
      setWorkers(w.workers);
      setMetrics(m);
      setAudit(a.entries || []);
      setRuntimeHealth(rh);
      setRuntimeTools(rt.tools || []);
      setRuntimeJobs(rj.jobs || []);
      setRuntimeMcpServers(rms.servers || []);
      setLastUpdate(new Date().toLocaleTimeString());
    } catch { setLastUpdate("error"); }
  }, []);

  useEffect(() => {
    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => setWsState("on");
      ws.onclose = () => setWsState("off");
      ws.onmessage = () => { setLastUpdate(`${new Date().toLocaleTimeString()} live`); setTimeout(refresh, 1000); };
    } catch { /* WS unavailable; wsState stays "wait" until onclose fires */ }
    return () => { wsRef.current?.close(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { const id = setInterval(refresh, 60000); return () => clearInterval(id); }, [refresh]);

  // Initial data fetch (deferred to avoid cascading renders)
  useEffect(() => { queueMicrotask(() => refresh()); }, [refresh]);

  const saveApiKey = (key: string) => {
    setApiKey(key);
    localStorage.setItem("nami_api_key", key);
  };

  useEffect(() => {
    const saved = localStorage.getItem("nami_api_key");
    if (saved) setApiKey(saved);
  }, []);
  const toggleTheme = () => {
    setDark(d => {
      const next = !d;
      document.documentElement.classList.toggle("light", !next);
      return next;
    });
  };

  return (
    <div className="min-h-screen flex flex-col page-bg">
      <header className="flex items-center justify-between px-6 py-3 header">
        <div><h1 className="header-title">Nami Ecosystem</h1><p className="text-xs text-dim">Live orchestrator control surface</p></div>
        <div className="flex items-center gap-3">
          <input
            placeholder="API Key"
            value={apiKey}
            onChange={e => saveApiKey(e.target.value)}
            type="password"
            className="input-dark w-36 text-xs"
            aria-label="API Key"
          />
          <span className={`text-xs px-2 py-0.5 rounded font-semibold ${wsState === "on" ? "bg-green-900/30 text-green-400" : wsState === "wait" ? "bg-orange-900/30 text-orange-400" : "bg-red-900/30 text-red-400"}`}>
            WS {wsState === "on" ? "on" : wsState === "wait" ? "wait" : "off"}
          </span>
          <span className="text-xs text-dim">{lastUpdate}</span>
          <span className={`w-2.5 h-2.5 rounded-full inline-block ${healthOk ? "bg-green-500 shadow-[0_0_6px_#00C853]" : "bg-red-500 shadow-[0_0_6px_#FF1744]"}`} />
          <button onClick={toggleTheme} className="btn-icon" aria-label="Toggle theme">
            {dark ? <Moon size={16} /> : <Sun size={16} />}
          </button>
          <a href="/docs" className="btn-icon" aria-label="API Docs" title="API Docs">
            <BookOpen size={16} />
          </a>
          <button onClick={refresh} className="btn-icon" aria-label="Refresh data">
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-6">
        <MetricCard label="Workers" value={workers.length} icon={Cpu} />
        <MetricCard label="Dispatches" value={metrics.nami_core_dispatch_total ?? 0} icon={Zap} />
        <MetricCard label="Errors" value={metrics.nami_core_dispatch_errors_total ?? 0} icon={Activity} />
        <MetricCard label="Uptime" value={`${Math.floor((metrics.nami_core_uptime_seconds ?? 0) / 3600)}h`} icon={Clock} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 px-6 pb-6">
        <WorkerTopologyCanvas workers={workers} healthOk={healthOk} wsState={wsState} />
        <RuntimePanel health={runtimeHealth} tools={runtimeTools} jobs={runtimeJobs} mcpServers={runtimeMcpServers} apiKey={apiKey} onRefresh={refresh} />
        <WorkerHealthCards workers={workers} onAlert={setAlert} />
        <WorkerBarChart workers={workers} />
        <LatencyChart entries={audit} />
        <AuditTable entries={audit} />
        <DispatchPanel workers={workers} apiKey={apiKey} />
        <BatchDispatchPanel apiKey={apiKey} />
        <SSEEventLog />
        <RateLimitsPanel workers={workers} apiKey={apiKey} />
        <QuickActionsPanel apiKey={apiKey} />
      </div>
      <AlertToast message={alert} onClose={() => setAlert("")} />
    </div>
  );
}
