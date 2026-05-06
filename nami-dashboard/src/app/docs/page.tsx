"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Play, Key } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8092";

interface Endpoint {
  method: string;
  path: string;
  description: string;
  auth: boolean;
  body?: string;
}

const endpoints: Endpoint[] = [
  { method: "GET", path: "/health", description: "System health check", auth: false },
  { method: "GET", path: "/workers", description: "List all workers and actions", auth: false },
  { method: "GET", path: "/workers/{name}/health", description: "Worker health check", auth: false },
  { method: "GET", path: "/metrics", description: "System metrics", auth: false },
  { method: "GET", path: "/audit", description: "Audit trail (public read)", auth: false },
  { method: "GET", path: "/scheduler", description: "Scheduler status", auth: false },
  { method: "GET", path: "/events", description: "SSE event stream", auth: false },
  { method: "GET", path: "/webhook/verify", description: "Webhook signing info", auth: false },
  { method: "POST", path: "/dispatch", description: "Dispatch to a worker", auth: true, body: '{"worker":"status","action":"health","payload":{}}' },
  { method: "POST", path: "/dispatch/batch", description: "Batch dispatch (max 10)", auth: true, body: '{"items":[{"worker":"status","action":"health","payload":{}}]}' },
  { method: "POST", path: "/webhook", description: "Send webhook event", auth: false, body: '{"source":"test","event":"ping","data":{}}' },
  { method: "GET", path: "/workers/{name}/rate-limit", description: "Worker rate limit status", auth: true },
  { method: "GET", path: "/cache", description: "Cache statistics", auth: true },
  { method: "GET", path: "/db", description: "Database pool stats", auth: true },
  { method: "POST", path: "/cache/flush", description: "Flush cache", auth: true },
  { method: "POST", path: "/rotate-key", description: "Rotate API key", auth: true, body: '{"new_key":"new-key-here-min-8-chars"}' },
  { method: "POST", path: "/restart", description: "Graceful restart", auth: true },
  { method: "POST", path: "/reload-workers", description: "Hot-reload workers", auth: true },
];

const methodColor: Record<string, string> = {
  GET: "bg-green-900/30 text-green-400",
  POST: "bg-blue-900/30 text-blue-400",
};

export default function DocsPage() {
  const [apiKey, setApiKey] = useState("");
  const [selected, setSelected] = useState<Endpoint | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [workerName, setWorkerName] = useState("status");

  const saveKey = (k: string) => {
    setApiKey(k);
    localStorage.setItem("nami_api_key", k);
  };

  // Load saved API key on mount (lazy init to avoid effect cascading)
  const [initialized, setInitialized] = useState(false);
  if (!initialized && typeof window !== "undefined") {
    const saved = localStorage.getItem("nami_api_key");
    if (saved) { setApiKey(saved); }
    setInitialized(true);
  }

  const tryEndpoint = async (ep: Endpoint) => {
    setLoading(true);
    setResult(null);
    try {
      const path = ep.path.replace("{name}", workerName);
      const opts: RequestInit = { method: ep.method };
      const headers: Record<string, string> = {};
      if (ep.auth && apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
      if (ep.body) {
        headers["Content-Type"] = "application/json";
        opts.body = ep.body;
      }
      opts.headers = headers;
      const r = await fetch(`${API_BASE}${path}`, opts);
      const data = await r.json();
      setResult(JSON.stringify(data, null, 2));
    } catch (e) {
      setResult(`Error: ${e}`);
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen page-bg text-white p-6">
      <div className="flex items-center gap-4 mb-6">
        <Link href="/" className="btn-icon" title="Back to Dashboard"><ArrowLeft size={20} /></Link>
        <h1 className="text-xl font-bold text-gold">API Documentation</h1>
        <span className="text-xs text-dim">{API_BASE}</span>
      </div>

      <div className="flex gap-2 mb-4 items-center">
        <Key size={14} className="text-gold-dim" />
        <input
          placeholder="API Key (saved in localStorage)"
          value={apiKey}
          onChange={e => saveKey(e.target.value)}
          type="password"
          className="input-dark flex-1 max-w-md"
          aria-label="API Key"
        />
        <input
          placeholder="Worker name for {name} paths"
          value={workerName}
          onChange={e => setWorkerName(e.target.value)}
          className="input-dark w-40"
          aria-label="Worker name"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          {endpoints.map((ep, i) => (
            <button
              key={i}
              onClick={() => setSelected(ep)}
              className={`text-left p-3 rounded-lg border ${selected?.path === ep.path && selected?.method === ep.method ? "border-gold bg-gold/5" : "border-gray-800 hover:border-gray-600"}`}
            >
              <div className="flex items-center gap-2">
                <span className={`text-xs font-mono px-2 py-0.5 rounded ${methodColor[ep.method]}`}>{ep.method}</span>
                <span className="font-mono text-sm">{ep.path}</span>
                {ep.auth && <span className="text-[10px] text-orange-400">AUTH</span>}
              </div>
              <div className="text-xs text-dim mt-1">{ep.description}</div>
            </button>
          ))}
        </div>

        <div className="card">
          {selected ? (
            <>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-mono px-2 py-0.5 rounded ${methodColor[selected.method]}`}>{selected.method}</span>
                  <span className="font-mono text-sm">{selected.path.replace("{name}", workerName)}</span>
                </div>
                <button onClick={() => tryEndpoint(selected)} disabled={loading} className="btn-gold text-xs flex items-center gap-1">
                  <Play size={12} /> {loading ? "Running..." : "Try It"}
                </button>
              </div>
              {selected.body && (
                <div className="mb-3">
                  <div className="text-xs text-dim mb-1">Request Body:</div>
                  <pre className="pre-dark text-xs">{selected.body}</pre>
                </div>
              )}
              {result !== null && (
                <div>
                  <div className="text-xs text-dim mb-1">Response:</div>
                  <pre className="pre-dark text-xs max-h-96 overflow-auto">{result}</pre>
                </div>
              )}
            </>
          ) : (
            <div className="text-dim text-sm">Select an endpoint to try it</div>
          )}
        </div>
      </div>
    </div>
  );
}
