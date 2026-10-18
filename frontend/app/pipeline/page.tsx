"use client";
import { useEffect, useRef, useState } from "react";
import { API, api } from "@/lib/api";

interface DagNode { id: string; label: string; desc: string }
interface Dag { engine?: string; nodes: DagNode[]; edges: [string, string][]; schedule?: string }
interface RunRec {
  run_id: string; source_id: string; status: string; current?: string;
  started_at?: string; finished_at?: string; error?: string; nodes?: Record<string, string>;
}

export default function PipelinePage() {
  const [dag, setDag] = useState<Dag | null>(null);
  const [sources, setSources] = useState<any[]>([]);
  const [sid, setSid] = useState<number | "">("");
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunRec | null>(null);
  const [runs, setRuns] = useState<RunRec[]>([]);
  const [msg, setMsg] = useState("");
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetch(`${API}/api/pipeline/graph`, { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setDag).catch(() => setDag(null));
    api.sources().then((d) => {
      const rows = d.sources || [];
      setSources(rows);
      if (rows.length) setSid(rows[0].id);
    }).catch(() => {});
    refreshRuns();
    return () => { if (poll.current) clearInterval(poll.current); };
  }, []);

  async function refreshRuns() {
    try {
      const r = await fetch(`${API}/api/pipeline/runs`, { cache: "no-store" });
      if (r.ok) setRuns((await r.json()).runs || []);
    } catch { /* ignore */ }
  }

  const ordered: DagNode[] = (() => {
    if (!dag) return [];
    const byId = new Map(dag.nodes.map((n) => [n.id, n]));
    const next = new Map(dag.edges.map(([a, b]) => [a, b]));
    const hasIn = new Set(dag.edges.map(([, b]) => b));
    const seq: DagNode[] = [];
    const seen = new Set<string>();
    let cur = dag.nodes.find((n) => !hasIn.has(n.id))?.id;
    while (cur && !seen.has(cur)) {
      seen.add(cur);
      const n = byId.get(cur);
      if (n) seq.push(n);
      cur = next.get(cur);
    }
    return seq.length === dag.nodes.length ? seq : dag.nodes;
  })();

  function toast(text: string) { setMsg(text); setTimeout(() => setMsg(""), 3500); }

  async function triggerRun() {
    if (!sid || run?.status === "running") return;
    try {
      const r = await fetch(`${API}/api/pipeline/run/${sid}`, { method: "POST" });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const d = await r.json();
      setRunId(d.run_id);
      setRun({ run_id: d.run_id, source_id: String(sid), status: "running", nodes: {} });
      toast(`DAG 已启动 run_id=${d.run_id}`);
      // 真实状态轮询：后端 Redis 回写每节点完成情况
      if (poll.current) clearInterval(poll.current);
      poll.current = setInterval(async () => {
        try {
          const sr = await fetch(`${API}/api/pipeline/run/${d.run_id}`, { cache: "no-store" });
          if (!sr.ok) return;
          const rec: RunRec = await sr.json();
          setRun(rec);
          if (rec.status !== "running") {
            if (poll.current) clearInterval(poll.current);
            refreshRuns();
            toast(rec.status === "done" ? "DAG 执行完成" : `执行失败：${rec.error || "未知错误"}`);
          }
        } catch { /* ignore */ }
      }, 1000);
    } catch (e) {
      toast(`触发失败：${e}`);
    }
  }

  const nodeState = (id: string): "pending" | "running" | "done" | "error" => {
    if (!run) return "pending";
    if (run.status === "done") return "done";
    if (run.status === "error") return run.nodes?.[id] === "done" ? "done" : run.current === id ? "error" : "pending";
    if (run.nodes?.[id] === "done") return "done";
    if (run.current === id) return "running";
    return "pending";
  };

  const nodeCls = (id: string) => {
    const st = nodeState(id);
    if (st === "done") return "border-low/30 bg-low/[0.06]";
    if (st === "running") return "border-accent/60 bg-accent/[0.10] shadow-[0_0_18px_rgba(62,200,232,0.18)]";
    if (st === "error") return "border-critical/50 bg-critical/[0.08]";
    return "border-line";
  };
  const badgeCls = (id: string) => {
    const st = nodeState(id);
    if (st === "done") return "border-low/30 bg-low/[0.12] text-low";
    if (st === "running") return "border-accent/40 bg-accent/[0.15] text-accent";
    if (st === "error") return "border-critical/40 bg-critical/[0.15] text-critical";
    return "border-line bg-white/[0.04] text-faint";
  };

  const sel = "input";
  const running = run?.status === "running";

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="h2">LangGraph 流水线</h1>
          <p className="text-[12px] text-faint">
            {dag?.engine || "LangGraph StateGraph"} 编排 · collect → enrich → index → kg → notify
          </p>
        </div>
        {dag?.schedule && <span className="tag-accent">调度：{dag.schedule}</span>}
      </div>

      <div className="card overflow-x-auto p-6">
        {ordered.length === 0 ? (
          <div className="py-10 text-center text-dim">无 DAG 数据（后端未连接）</div>
        ) : (
          <div className="flex min-w-max items-stretch">
            {ordered.map((n, i) => (
              <div key={n.id} className="flex items-center">
                <div className={`w-44 rounded-lg border p-3 transition-all duration-200 ${nodeCls(n.id)}`}>
                  <div className="mb-1 flex items-center gap-2">
                    <span className={`badge mono ${badgeCls(n.id)}`}>
                      {nodeState(n.id) === "done" ? "✓" : i + 1}
                    </span>
                    <span className="font-medium">{n.label}</span>
                    <span className="mono text-[10px] text-dim">{n.id}</span>
                  </div>
                  <p className="text-xs leading-snug text-dim">{n.desc}</p>
                  {nodeState(n.id) === "running" && <div className="mt-2 text-[11px] text-accent">执行中…</div>}
                  {nodeState(n.id) === "error" && <div className="mt-2 text-[11px] text-critical">失败</div>}
                </div>
                {i < ordered.length - 1 && (
                  <div className="mx-3 flex flex-col items-center text-dim">
                    <span className="text-lg leading-none text-faint">→</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {run && (
          <div className="mt-4 border-t border-line pt-3 text-xs text-dim">
            当前运行：<span className="mono text-fg">{run.run_id}</span>
            {run.current && <span> · 当前节点 <span className="text-accent">{run.current}</span></span>}
            <span> · 状态 <span className={run.status === "done" ? "text-low" : run.status === "error" ? "text-critical" : "text-accent"}>{run.status}</span></span>
            {run.error && <span className="text-critical"> · {run.error}</span>}
          </div>
        )}
      </div>

      <div className="card space-y-3">
        <h2 className="h3 mb-1">手动触发</h2>
        <div className="flex flex-wrap items-center gap-3">
          <select className={sel} value={sid} onChange={(e) => setSid(Number(e.target.value))}>
            {sources.length === 0 && <option value="">（无数据源）</option>}
            {sources.map((s) => (
              <option key={s.id} value={s.id}>{s.name}（{s.source_type} · T{s.tier}）</option>
            ))}
          </select>
          <button className="btn" disabled={running || sid === ""} onClick={triggerRun}>
            {running ? "DAG 运行中…" : "运行完整 DAG"}
          </button>
          {running && <span className="text-xs text-accent">节点状态来自后端 Redis 实时回写</span>}
        </div>
        <p className="text-xs text-dim">
          触发后后端执行整条 LangGraph 链：采集入库 → 并发富化 worker → Qdrant 混合向量索引 → Neo4j 图谱同步 → 高危条目 SSE 广播。
          节点状态通过 astream 事件实时写入 Redis，前端每秒轮询真实进度（非示意动画）。
        </p>
      </div>

      {runs.length > 0 && (
        <div className="card !p-0">
          <h2 className="h3 px-4 pt-3">最近运行</h2>
          <table className="tbl">
            <thead><tr><th>run_id</th><th>source</th><th>状态</th><th>开始</th><th>结束</th></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="mono text-xs">{r.run_id}</td>
                  <td className="text-xs">{r.source_id}</td>
                  <td>
                    <span className={`badge ${r.status === "done" ? "bg-low/15 text-low" : r.status === "error" ? "bg-critical/15 text-critical" : "bg-accent/15 text-accent"}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="text-xs text-dim">{(r.started_at || "").slice(5, 19).replace("T", " ")}</td>
                  <td className="text-xs text-dim">{(r.finished_at || "").slice(5, 19).replace("T", " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {msg && (
        <div className="card fixed bottom-6 right-6 z-50 border-accent/30 bg-overlay px-4 py-3 text-[13px] shadow-[0_8px_32px_rgba(0,0,0,0.5)]">{msg}</div>
      )}
    </div>
  );
}
