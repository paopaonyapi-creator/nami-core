"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import {
  Activity, Cpu, Clock, Moon, Sun, RefreshCw, Zap, Send,
  BarChart3, Shield, Database, Heart, Layers, Radio, AlertCircle, BookOpen, Gauge,
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

function DispatchPanel({ workers }: { workers: WorkerInfo[] }) {
  const [worker, setWorker] = useState("");
  const [action, setAction] = useState("");
  const [payload, setPayload] = useState("{}");
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const runDispatch = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
          {loading ? "Running..." : "▶ Run"}
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
                <td className="py-1 px-2">{e.ok ? "✓" : "✗"}</td>
                <td className="py-1 px-2">{e.latency_ms?.toFixed(1) ?? "—"}ms</td>
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

function BatchDispatchPanel() {
  const [items, setItems] = useState('[{"worker":"status","action":"health","payload":{}}]');
  const [results, setResults] = useState<BatchResult[] | null>(null);
  const [loading, setLoading] = useState(false);

  const runBatch = async () => {
    setLoading(true);
    try {
      const parsed = JSON.parse(items);
      const r = await fetch(`${API_BASE}/dispatch/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
          {loading ? "Running..." : "▶ Run Batch"}
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
                    <td className="py-1 px-2">{r.ok ? "✓" : "✗"}</td>
                    <td className="py-1 px-2">{r.latency_ms?.toFixed(1) ?? "—"}ms</td>
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

function RateLimitsPanel({ workers }: { workers: WorkerInfo[] }) {
  const [limits, setLimits] = useState<RateLimitInfo[]>([]);
  const [apiKey, setApiKey] = useState("");

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
        <div className="flex gap-2">
          <input placeholder="API Key" value={apiKey} onChange={e => setApiKey(e.target.value)} type="password" className="input-dark flex-1" aria-label="API Key" />
          <button onClick={fetchLimits} disabled={!apiKey} className="btn-gold text-xs">Check</button>
        </div>
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

function AlertToast({ message, onClose }: { message: string; onClose: () => void }) {
  if (!message) return null;
  return (
    <div className="fixed bottom-4 right-4 bg-red-900/90 text-red-200 px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 z-50 text-sm">
      <AlertCircle size={16} />
      <span>{message}</span>
      <button onClick={onClose} className="ml-2 text-red-400 hover:text-white">✕</button>
    </div>
  );
}

export default function Dashboard() {
  const [dark, setDark] = useState(true);
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [wsState, setWsState] = useState<"on" | "off" | "wait">("wait");
  const [lastUpdate, setLastUpdate] = useState("—");
  const [healthOk, setHealthOk] = useState(false);
  const [alert, setAlert] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async () => {
    try {
      const h = await apiFetch<{ status: string; workers: string[] }>("/health");
      const w = await apiFetch<{ workers: WorkerInfo[] }>("/workers");
      const m = await apiFetch<Record<string, number>>("/metrics");
      const a = await apiFetch<{ entries: AuditEntry[] }>("/audit");
      setHealthOk(h.status === "ok");
      setWorkers(w.workers);
      setMetrics(m);
      setAudit(a.entries || []);
      setLastUpdate(new Date().toLocaleTimeString());
    } catch { setLastUpdate("error"); }
  }, []);

  useEffect(() => {
    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => setWsState("on");
      ws.onclose = () => setWsState("off");
      ws.onmessage = () => { setLastUpdate(new Date().toLocaleTimeString() + " ⚡"); setTimeout(refresh, 1000); };
    } catch { /* WS unavailable — wsState stays "wait" until onclose fires */ }
    return () => { wsRef.current?.close(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { const id = setInterval(refresh, 60000); return () => clearInterval(id); }, [refresh]);

  // Initial data fetch (deferred to avoid cascading renders)
  useEffect(() => { queueMicrotask(() => refresh()); }, [refresh]);

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
        <h1 className="header-title">🌸 Nami Ecosystem</h1>
        <div className="flex items-center gap-3">
          <span className={`text-xs px-2 py-0.5 rounded font-semibold ${wsState === "on" ? "bg-green-900/30 text-green-400" : wsState === "wait" ? "bg-orange-900/30 text-orange-400" : "bg-red-900/30 text-red-400"}`}>
            WS {wsState === "on" ? "●" : wsState === "wait" ? "◌" : "○"}
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
        <WorkerHealthCards workers={workers} onAlert={setAlert} />
        <WorkerBarChart workers={workers} />
        <LatencyChart entries={audit} />
        <AuditTable entries={audit} />
        <DispatchPanel workers={workers} />
        <BatchDispatchPanel />
        <SSEEventLog />
        <RateLimitsPanel workers={workers} />
        <div className="card">
          <h2 className="card-title">
            <Database size={16} /> Quick Actions
          </h2>
          <div className="flex flex-col gap-2">
            <button className="btn-gold-dim" onClick={() => fetch(`${API_BASE}/cache`).then(r => r.json()).then(console.log)}>
              Cache Stats
            </button>
            <button className="btn-gold-dim" onClick={() => fetch(`${API_BASE}/cache/flush`, { method: "POST" }).then(console.log)}>
              Flush Cache
            </button>
          </div>
        </div>
      </div>
      <AlertToast message={alert} onClose={() => setAlert("")} />
    </div>
  );
}
