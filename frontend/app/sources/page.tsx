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
      <div className="card flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">数据源监控</h1>
          <p className="text-sm text-dim">{rows.length} 个源 · {ok} 健康</p>
        </div>
        <div className="flex items-center gap-3">
          {msg && <span className="text-sm text-low">{msg}</span>}
          <button className="btn" onClick={() => api.runAll().then(load)}>立即采集全部</button>
        </div>
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-dim">
              <th className="p-3">源</th><th className="p-3">类型</th><th className="p-3">级别</th>
              <th className="p-3">最近运行</th><th className="p-3">状态</th><th className="p-3">累计</th><th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="border-b border-border/50 hover:bg-border/30">
                <td className="p-3">
                  <div className="font-medium">{s.name}</div>
                  {s.last_error && <div className="mt-0.5 max-w-md truncate text-xs text-critical" title={s.last_error}>{s.last_error}</div>}
                </td>
                <td className="p-3 text-dim">{s.source_type}</td>
                <td className="p-3"><span className="tag">T{s.tier}</span></td>
                <td className="p-3 text-xs text-dim">{s.last_run_at ? s.last_run_at.slice(5, 19).replace("T", " ") : "—"}</td>
                <td className="p-3">
                  {s.consecutive_failures > 0
                    ? <span className="badge sev-critical">失败×{s.consecutive_failures}</span>
                    : s.last_success_at ? <span className="badge sev-low">正常</span>
                    : <span className="badge tag">未运行</span>}
                </td>
                <td className="p-3 text-dim">{s.total_items}</td>
                <td className="p-3"><button className="btn-ghost !px-2 !py-1 text-xs" disabled={running[s.id]} onClick={() => run(s.id)}>{running[s.id] ? "…" : "采集"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
