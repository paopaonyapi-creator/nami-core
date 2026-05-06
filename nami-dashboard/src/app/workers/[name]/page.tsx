"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Heart, Zap, Clock, Activity } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8092";

interface WorkerInfo { name: string; actions: string[] }
interface WorkerHealth { worker: string; healthy: boolean | null; latency_ms: number; actions: string[]; message?: string; response?: Record<string, unknown>; error?: string }
interface AuditEntry { worker: string; action: string; caller_ip: string; ok: boolean; latency_ms: number; timestamp: string }

export default function WorkerDetailPage() {
  const params = useParams();
  const name = params.name as string;
  const [info, setInfo] = useState<WorkerInfo | null>(null);
  const [health, setHealth] = useState<WorkerHealth | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [dispatchResult, setDispatchResult] = useState<string | null>(null);
  const [dispatchAction, setDispatchAction] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(false);

  // Lazy init API key from localStorage
  const [keyInit, setKeyInit] = useState(false);
  if (!keyInit && typeof window !== "undefined") {
    const saved = localStorage.getItem("nami_api_key");
    if (saved) setApiKey(saved);
    setKeyInit(true);
  }

  useEffect(() => {
    const fetchData = async () => {
      try {
        const wRes = await fetch(`${API_BASE}/workers`);
        const wData = await wRes.json();
        const found = wData.workers?.find((w: WorkerInfo) => w.name === name);
        setInfo(found || null);

        const hRes = await fetch(`${API_BASE}/workers/${name}/health`);
        if (hRes.ok) setHealth(await hRes.json());

        const aRes = await fetch(`${API_BASE}/audit?limit=50`);
        const aData = await aRes.json();
        setAudit((aData.entries || []).filter((e: AuditEntry) => e.worker === name));
      } catch { /* skip */ }
    };
    if (name) fetchData();
    const id = setInterval(() => { if (name) fetchData(); }, 30000);
    return () => clearInterval(id);
  }, [name]);

  const doDispatch = async () => {
    if (!dispatchAction || !apiKey) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({ worker: name, action: dispatchAction, payload: {} }),
      });
      setDispatchResult(JSON.stringify(await r.json(), null, 2));
    } catch (e) { setDispatchResult(`Error: ${e}`); }
    setLoading(false);
  };

  const healthBadge = health?.healthy === true
    ? "bg-green-900/30 text-green-400 border-green-700"
    : health?.healthy === false
      ? "bg-red-900/30 text-red-400 border-red-700"
      : "bg-gray-800 text-gray-400 border-gray-600";

  return (
    <div className="min-h-screen page-bg text-white p-6">
      <div className="flex items-center gap-4 mb-6">
        <Link href="/" className="btn-icon" title="Back to Dashboard"><ArrowLeft size={20} /></Link>
        <h1 className="text-xl font-bold text-gold">Worker: {name}</h1>
        <span className={`text-xs px-2 py-0.5 rounded border ${healthBadge}`}>
          {health?.healthy === true ? "HEALTHY" : health?.healthy === false ? "UNHEALTHY" : "UNKNOWN"}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Health Card */}
        <div className="card">
          <h2 className="card-title"><Heart size={16} /> Health</h2>
          {health ? (
            <div className="flex flex-col gap-1 text-sm">
              <div className="flex justify-between"><span className="text-dim">Latency:</span><span>{health.latency_ms?.toFixed(1) ?? "—"}ms</span></div>
              <div className="flex justify-between"><span className="text-dim">Message:</span><span className="truncate max-w-[200px]">{health.message || health.error || "OK"}</span></div>
              {health.response && <pre className="pre-dark text-xs mt-2 max-h-32 overflow-auto">{JSON.stringify(health.response, null, 2)}</pre>}
            </div>
          ) : <div className="text-dim text-sm">Loading...</div>}
        </div>

        {/* Actions Card */}
        <div className="card">
          <h2 className="card-title"><Zap size={16} /> Actions</h2>
          {info ? (
            <div className="flex flex-wrap gap-1">
              {info.actions.map(a => (
                <button key={a} onClick={() => setDispatchAction(a)} className={`chip cursor-pointer ${dispatchAction === a ? "bg-gold/20 text-gold border-gold/50" : "hover:bg-gray-700"}`}>
                  {a}
                </button>
              ))}
            </div>
          ) : <div className="text-dim text-sm">Loading...</div>}
        </div>

        {/* Dispatch Card */}
        <div className="card">
          <h2 className="card-title"><Activity size={16} /> Dispatch</h2>
          <div className="flex flex-col gap-2">
            <input placeholder="API Key" value={apiKey} onChange={e => { setApiKey(e.target.value); localStorage.setItem("nami_api_key", e.target.value); }} type="password" className="input-dark" aria-label="API Key" />
            <div className="flex gap-2">
              <input placeholder="Action" value={dispatchAction} onChange={e => setDispatchAction(e.target.value)} className="input-dark flex-1" aria-label="Action" />
              <button onClick={doDispatch} disabled={loading || !dispatchAction || !apiKey} className="btn-gold text-xs">
                {loading ? "..." : "▶ Run"}
              </button>
            </div>
            {dispatchResult && <pre className="pre-dark text-xs max-h-40 overflow-auto">{dispatchResult}</pre>}
          </div>
        </div>

        {/* Audit Card */}
        <div className="card md:col-span-2 lg:col-span-3">
          <h2 className="card-title"><Clock size={16} /> Recent Audit ({audit.length})</h2>
          {audit.length === 0 ? <div className="text-dim text-sm">No recent audit entries</div> : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="table-header">
                  <th className="text-left py-1 px-2">Time</th>
                  <th className="text-left py-1 px-2">Action</th>
                  <th className="text-left py-1 px-2">IP</th>
                  <th className="text-left py-1 px-2">OK</th>
                  <th className="text-left py-1 px-2">Latency</th>
                </tr></thead>
                <tbody>
                  {audit.slice(0, 20).map((e, i) => (
                    <tr key={i} className="border-b table-row-border">
                      <td className="py-1 px-2 text-dim">{new Date(e.timestamp).toLocaleTimeString()}</td>
                      <td className="py-1 px-2">{e.action}</td>
                      <td className="py-1 px-2 text-dim">{e.caller_ip}</td>
                      <td className="py-1 px-2">{e.ok ? "✓" : "✗"}</td>
                      <td className="py-1 px-2">{e.latency_ms?.toFixed(1) ?? "—"}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
