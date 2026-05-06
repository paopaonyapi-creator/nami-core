"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Activity, Cpu, Clock, Moon, Sun, RefreshCw, Zap, Send,
  BarChart3, Shield, Database,
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

async function apiFetch<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  return r.json();
}

function MetricCard({ label, value, icon: Icon }: { label: string; value: string | number; icon: React.ElementType }) {
  return (
    <div className="rounded-xl p-5" style={{ background: "linear-gradient(135deg, var(--dark2), var(--dark3))", border: "1px solid rgba(212,175,55,0.15)" }}>
      <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-dim)" }}>
        <Icon size={14} style={{ color: "var(--gold-dim)" }} /> {label}
      </div>
      <div className="text-2xl font-bold mt-1" style={{ color: "var(--gold)" }}>{value}</div>
    </div>
  );
}

function WorkerChips({ workers }: { workers: WorkerInfo[] }) {
  return (
    <div className="rounded-xl p-5" style={{ background: "linear-gradient(135deg, var(--dark2), var(--dark3))", border: "1px solid rgba(212,175,55,0.15)" }}>
      <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--gold)" }}>
        <Cpu size={16} /> Workers ({workers.length})
      </h2>
      <div className="flex flex-wrap gap-1">
        {workers.map(w => (
          <span key={w.name} className="inline-block rounded-md px-2 py-1 text-xs" style={{ background: "rgba(212,175,55,0.1)", border: "1px solid rgba(212,175,55,0.2)" }}>{w.name}</span>
        ))}
      </div>
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
    <div className="rounded-xl p-5" style={{ background: "linear-gradient(135deg, var(--dark2), var(--dark3))", border: "1px solid rgba(212,175,55,0.15)" }}>
      <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--gold)" }}>
        <Send size={16} /> Dispatch Test
      </h2>
      <div className="flex flex-col gap-2">
        <select value={worker} onChange={e => setWorker(e.target.value)} className="rounded-md px-2 py-1.5 text-sm" style={{ background: "var(--dark)", color: "var(--text)", border: "1px solid var(--gold-dim)" }}>
          <option value="">Select worker...</option>
          {workers.map(w => <option key={w.name} value={w.name}>{w.name}</option>)}
        </select>
        <input placeholder="Action" value={action} onChange={e => setAction(e.target.value)} className="rounded-md px-2 py-1.5 text-sm" style={{ background: "var(--dark)", color: "var(--text)", border: "1px solid var(--gold-dim)" }} />
        <textarea placeholder="{}" value={payload} onChange={e => setPayload(e.target.value)} rows={2} className="rounded-md px-2 py-1.5 text-sm" style={{ background: "var(--dark)", color: "var(--text)", border: "1px solid var(--gold-dim)" }} />
        <button onClick={runDispatch} disabled={loading || !worker || !action} className="rounded-md px-4 py-2 font-semibold text-sm cursor-pointer" style={{ background: "var(--gold)", color: "var(--dark)" }}>
          {loading ? "Running..." : "▶ Run"}
        </button>
        {result && <pre className="mt-2 p-2 rounded text-xs overflow-auto max-h-40" style={{ background: "var(--dark)", color: "var(--text)" }}>{result}</pre>}
      </div>
    </div>
  );
}

function AuditTable({ entries }: { entries: AuditEntry[] }) {
  return (
    <div className="rounded-xl p-5" style={{ background: "linear-gradient(135deg, var(--dark2), var(--dark3))", border: "1px solid rgba(212,175,55,0.15)" }}>
      <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--gold)" }}>
        <Shield size={16} /> Audit Trail
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr style={{ color: "var(--gold-dim)" }}>
            <th className="text-left py-1 px-2">Worker</th><th className="text-left py-1 px-2">Action</th>
            <th className="text-left py-1 px-2">OK</th><th className="text-left py-1 px-2">Latency</th>
            <th className="text-left py-1 px-2">Time</th>
          </tr></thead>
          <tbody>
            {entries.slice(0, 15).map((e, i) => (
              <tr key={i} className="border-b" style={{ borderColor: "rgba(212,175,55,0.1)" }}>
                <td className="py-1 px-2">{e.worker}</td><td className="py-1 px-2">{e.action}</td>
                <td className="py-1 px-2">{e.ok ? "✓" : "✗"}</td>
                <td className="py-1 px-2">{e.latency_ms?.toFixed(1) ?? "—"}ms</td>
                <td className="py-1 px-2" style={{ color: "var(--text-dim)" }}>{new Date(e.timestamp).toLocaleTimeString()}</td>
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
    <div className="rounded-xl p-5" style={{ background: "linear-gradient(135deg, var(--dark2), var(--dark3))", border: "1px solid rgba(212,175,55,0.15)" }}>
      <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--gold)" }}>
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
    <div className="rounded-xl p-5" style={{ background: "linear-gradient(135deg, var(--dark2), var(--dark3))", border: "1px solid rgba(212,175,55,0.15)" }}>
      <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--gold)" }}>
        <Activity size={16} /> Worker Actions
      </h2>
      <Bar data={data} options={{ responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: "#888", font: { size: 9 } } }, y: { ticks: { color: "#888" } } } }} />
    </div>
  );
}

export default function Dashboard() {
  const [dark, setDark] = useState(true);
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [metrics, setMetrics] = useState<Record<string, number>>({});
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [wsState, setWsState] = useState<"on" | "off" | "wait">("off");
  const [lastUpdate, setLastUpdate] = useState("—");
  const [healthOk, setHealthOk] = useState(false);
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
      setWsState("wait");
      ws.onopen = () => setWsState("on");
      ws.onclose = () => setWsState("off");
      ws.onmessage = () => { setLastUpdate(new Date().toLocaleTimeString() + " ⚡"); setTimeout(refresh, 1000); };
    } catch { setWsState("off"); }
    return () => { wsRef.current?.close(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { refresh(); const id = setInterval(refresh, 60000); return () => clearInterval(id); }, [refresh]);

  const toggleTheme = () => {
    setDark(d => {
      const next = !d;
      document.documentElement.classList.toggle("light", !next);
      return next;
    });
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--dark)", color: "var(--text)" }}>
      <header className="flex items-center justify-between px-6 py-3" style={{ background: "linear-gradient(135deg, var(--dark2), var(--dark3))", borderBottom: "2px solid var(--gold-dim)" }}>
        <h1 className="text-xl font-bold" style={{ color: "var(--gold)" }}>🌸 Nami Ecosystem</h1>
        <div className="flex items-center gap-3">
          <span className={`text-xs px-2 py-0.5 rounded font-semibold ${wsState === "on" ? "bg-green-900/30 text-green-400" : wsState === "wait" ? "bg-orange-900/30 text-orange-400" : "bg-red-900/30 text-red-400"}`}>
            WS {wsState === "on" ? "●" : wsState === "wait" ? "◌" : "○"}
          </span>
          <span className="text-xs" style={{ color: "var(--text-dim)" }}>{lastUpdate}</span>
          <span className={`w-2.5 h-2.5 rounded-full inline-block ${healthOk ? "bg-green-500 shadow-[0_0_6px_#00C853]" : "bg-red-500 shadow-[0_0_6px_#FF1744]"}`} />
          <button onClick={toggleTheme} className="p-1.5 rounded-lg border-0 cursor-pointer" style={{ borderColor: "var(--gold-dim)", color: "var(--gold)", background: "none" }}>
            {dark ? <Moon size={16} /> : <Sun size={16} />}
          </button>
          <button onClick={refresh} className="p-1.5 rounded-lg border-0 cursor-pointer" style={{ borderColor: "var(--gold-dim)", color: "var(--gold)", background: "none" }}>
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
        <WorkerChips workers={workers} />
        <WorkerBarChart workers={workers} />
        <LatencyChart entries={audit} />
        <AuditTable entries={audit} />
        <DispatchPanel workers={workers} />
        <div className="rounded-xl p-5" style={{ background: "linear-gradient(135deg, var(--dark2), var(--dark3))", border: "1px solid rgba(212,175,55,0.15)" }}>
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--gold)" }}>
            <Database size={16} /> Quick Actions
          </h2>
          <div className="flex flex-col gap-2">
            <button className="rounded-md px-3 py-1.5 text-xs font-semibold cursor-pointer" style={{ background: "var(--gold-dim)", color: "var(--dark)" }} onClick={() => fetch(`${API_BASE}/cache`).then(r => r.json()).then(console.log)}>
              Cache Stats
            </button>
            <button className="rounded-md px-3 py-1.5 text-xs font-semibold cursor-pointer" style={{ background: "var(--gold-dim)", color: "var(--dark)" }} onClick={() => fetch(`${API_BASE}/cache/flush`, { method: "POST" }).then(console.log)}>
              Flush Cache
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
