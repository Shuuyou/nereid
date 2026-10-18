"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SourcesPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [running, setRunning] = useState<Record<number, boolean>>({});
  const [msg, setMsg] = useState("");

  const load = () => api.sources().then((d) => setRows(d.sources || [])).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);

  async function run(id: number) {
    setRunning((r) => ({ ...r, [id]: true }));
    await api.runSource(id).catch(() => {});
    setMsg("已触发采集"); setTimeout(() => setMsg(""), 2000);
    setRunning((r) => ({ ...r, [id]: false }));
    setTimeout(load, 1500);
  }

  const ok = rows.filter((r) => r.enabled && !r.consecutive_failures).length;

  return (
    <div className="space-y-4">
      <div className="mb-1 flex items-end justify-between">
        <div>
          <h1 className="h2">数据源监控</h1>
          <p className="mt-0.5 text-[12px] text-faint">{rows.length} 个源 · <span className="text-low">{ok} 健康</span></p>
        </div>
        <div className="flex items-center gap-3">
          {msg && <span className="text-[12px] text-low">{msg}</span>}
          <button className="btn" onClick={() => api.runAll().then(load)}>立即采集全部</button>
        </div>
      </div>
      <div className="card overflow-x-auto !p-0">
        <table className="tbl">
          <thead>
            <tr><th>源</th><th>类型</th><th>级别</th><th>最近运行</th><th>状态</th><th>累计</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <td>
                  <div className="font-medium">{s.name}</div>
                  {s.last_error && <div className="mt-0.5 max-w-md truncate text-xs text-critical" title={s.last_error}>{s.last_error}</div>}
                </td>
                <td className="mono text-[11px] text-dim">{s.source_type}</td>
                <td><span className="tag">T{s.tier}</span></td>
                <td className="mono text-[11px] text-faint">{s.last_run_at ? s.last_run_at.slice(5, 19).replace("T", " ") : "—"}</td>
                <td>
                  {s.consecutive_failures > 0
                    ? <span className="badge sev-critical">失败×{s.consecutive_failures}</span>
                    : s.last_success_at ? <span className="badge sev-low">正常</span>
                    : <span className="badge tag">未运行</span>}
                </td>
                <td className="tabular-nums text-dim">{(s.total_items || 0).toLocaleString()}</td>
                <td><button className="btn-ghost !px-2 !py-1 text-xs" disabled={running[s.id]} onClick={() => run(s.id)}>{running[s.id] ? "…" : "采集"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
