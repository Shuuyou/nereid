"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SpecRow, SpecDot, PageHeader, StatStrip, St, Empty } from "@/components/ui";
import { Radio, RefreshCw } from "lucide-react";

/** 采集间隔格式化：秒 → "15m" / "1.5h" */
function fmtInterval(sec?: number) {
  if (!sec) return "—";
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1).replace(/\.0$/, "")}h`;
}

export default function SourcesPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [running, setRunning] = useState<Record<number, boolean>>({});
  const [loaded, setLoaded] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => api.sources().then((d) => { setRows(d.sources || []); setLoaded(true); }).catch(() => setLoaded(true));
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);

  async function run(id: number) {
    setRunning((r) => ({ ...r, [id]: true }));
    await api.runSource(id).catch(() => {});
    setMsg("已触发采集"); setTimeout(() => setMsg(""), 2000);
    setRunning((r) => ({ ...r, [id]: false }));
    setTimeout(load, 1500);
  }

  const ok = rows.filter((r) => r.enabled && !r.consecutive_failures).length;
  const totalItems = rows.reduce((s, r) => s + (r.total_items || 0), 0);
  const intervals = rows.map((r) => r.poll_interval_sec).filter((x) => x > 0);
  const avgInterval = intervals.length ? Math.round(intervals.reduce((a, b) => a + b, 0) / intervals.length) : null;

  return (
    <div>
      <SpecRow>
        <span>FIG_05</span><SpecDot />
        <span>SOURCES</span><SpecDot />
        <span>{ok}/{rows.length} ONLINE</span>
        <span className="ml-auto flex items-center gap-1.5 normal-case tracking-normal">
          <St tone={ok === rows.length && rows.length > 0 ? "ok" : ok > 0 ? "warn" : "dim"}>
            {rows.length ? (ok === rows.length ? "ALL HEALTHY" : `${rows.length - ok} DEGRADED`) : "NO DATA"}
          </St>
        </span>
      </SpecRow>

      <PageHeader title="数据源监控" desc="采集器健康度 · tier 调度 · 失败重试"
        right={<button className="btn btn-acc" onClick={() => api.runAll().then(load)}>
          <Radio size={12} strokeWidth={1.75} />采集全部
        </button>} />

      <StatStrip stats={[
        { label: "在线源", value: `${ok}/${rows.length}`, tone: ok === rows.length ? "ok" : "high" },
        { label: "累计条目", value: totalItems.toLocaleString() },
        { label: "平均采集间隔", value: avgInterval ? fmtInterval(avgInterval) : "—", tone: "accent" },
        { label: "失败源", value: rows.filter((r) => r.consecutive_failures > 0).length, tone: rows.some((r) => r.consecutive_failures > 0) ? "critical" : "fg" },
      ]} />

      <div className="sect !mt-6">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="sect-title">采集器清单</h2>
          <span className="font-mono text-[10.5px] text-faint">POLL 15s AUTO-REFRESH</span>
        </div>
        {!loaded ? (
          <div className="space-y-px">{[0, 1, 2].map((i) => <div key={i} className="skel h-9" />)}</div>
        ) : rows.length === 0 ? (
          <Empty text="无数据源" hint="后端未连接或未配置采集器" />
        ) : (
          <div className="overflow-x-auto">
            <table className="dt">
              <thead>
                <tr>
                  <th>源</th>
                  <th>类型</th>
                  <th>Tier</th>
                  <th>状态</th>
                  <th className="r">累计条目</th>
                  <th>上次采集</th>
                  <th className="r">频率</th>
                  <th className="r">连败</th>
                  <th className="r"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <div className="text-[12.5px] font-medium text-fg">{s.name}</div>
                      {s.last_error && (
                        <div className="mono mt-0.5 max-w-[340px] truncate text-[10px] text-err" title={s.last_error}>
                          {s.last_error}
                        </div>
                      )}
                    </td>
                    <td><span className="badge mono">{s.source_type}</span></td>
                    <td><span className="badge mono">T{s.tier}</span></td>
                    <td>
                      {!s.enabled ? <St tone="dim">停用</St>
                        : s.consecutive_failures > 0 ? <St tone="err">失败</St>
                        : s.last_success_at ? <St tone="ok">正常</St>
                        : <St tone="dim">未运行</St>}
                    </td>
                    <td className="r num text-dim">{(s.total_items || 0).toLocaleString()}</td>
                    <td className="num text-faint">
                      {s.last_run_at ? s.last_run_at.slice(5, 19).replace("T", " ") : "—"}
                    </td>
                    <td className="r num text-dim">{fmtInterval(s.poll_interval_sec)}</td>
                    <td className="r num">
                      {s.consecutive_failures > 0
                        ? <span className="text-err">×{s.consecutive_failures}</span>
                        : <span className="text-faint">0</span>}
                    </td>
                    <td className="r">
                      <button className="btn btn-sm" disabled={running[s.id] || !s.enabled} onClick={() => run(s.id)}>
                        {running[s.id] ? <RefreshCw size={11} strokeWidth={1.75} className="animate-spin" /> : null}
                        {running[s.id] ? "采集中" : "采集"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {msg && (
        <div className="rise fixed bottom-5 right-5 z-50 rounded-[8px] border border-line border-l-2 border-l-accent bg-panel px-4 py-2.5 text-[12.5px] text-fg">
          {msg}
        </div>
      )}
    </div>
  );
}
