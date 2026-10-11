"use client";
import { useEffect, useRef, useState } from "react";
import { API, api } from "@/lib/api";

interface DagNode { id: string; label: string; desc: string }
interface Dag { engine?: string; nodes: DagNode[]; edges: [string, string][]; schedule?: string }

export default function PipelinePage() {
  const [dag, setDag] = useState<Dag | null>(null);
  const [sources, setSources] = useState<any[]>([]);
  const [sid, setSid] = useState<number | "">("");
  const [running, setRunning] = useState(false);
  // progress: -1 空闲；n = 第 n 个节点正在执行；>= 节点数 = 全部完成
  const [progress, setProgress] = useState(-1);
  const [msg, setMsg] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetch(`${API}/api/pipeline/graph`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then(setDag)
      .catch(() => setDag(null));
    api.sources()
      .then((d) => {
        const rows = d.sources || [];
        setSources(rows);
        if (rows.length) setSid(rows[0].id);
      })
      .catch(() => {});
    return () => { if (timer.current) clearInterval(timer.current); };
  }, []);

  // 按 edges 链式排序（入度为 0 的起点一路走到尾），异常时回落原始顺序
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

  function toast(text: string) {
    setMsg(text);
    setTimeout(() => setMsg(""), 3000);
  }

  async function run() {
    if (!sid || running) return;
    setRunning(true);
    setProgress(0);
    try {
      const r = await fetch(`${API}/api/pipeline/run/${sid}`, { method: "POST" });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const d = await r.json();
      toast(`已启动对「${d.source}」的全链 DAG（后台异步执行）`);
      // 后端 asyncio 后台执行，前端按 DAG 顺序逐节点高亮示意推进
      const chain: string[] = d.dag || ordered.map((n) => n.id);
      let i = 0;
      timer.current = setInterval(() => {
        i += 1;
        setProgress(i);
        if (i >= chain.length) {
          if (timer.current) clearInterval(timer.current);
          setRunning(false);
        }
      }, 1200);
    } catch (e) {
      toast(`触发失败：${e}`);
      setRunning(false);
      setProgress(-1);
    }
  }

  function nodeCls(i: number) {
    if (progress >= 0 && i < progress) return "border-low/50 bg-low/5";
    if (i === progress && running) return "border-accent bg-accent/10 animate-pulse";
    if (progress >= ordered.length && ordered.length > 0) return "border-low/50 bg-low/5";
    return "border-border";
  }

  const sel = "rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-fg";

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">LangGraph 流水线</h1>
          <p className="text-sm text-dim">
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
                <div className={`w-44 rounded-xl border p-3 transition-colors ${nodeCls(i)}`}>
                  <div className="mb-1 flex items-center gap-2">
                    <span className={`badge ${progress > i || progress >= ordered.length ? "bg-low/15 text-low" : i === progress && running ? "bg-accent/15 text-accent" : "bg-border text-dim"}`}>
                      {progress > i || progress >= ordered.length ? "✓" : i + 1}
                    </span>
                    <span className="font-medium">{n.label}</span>
                    <span className="mono text-[10px] text-dim">{n.id}</span>
                  </div>
                  <p className="text-xs leading-snug text-dim">{n.desc}</p>
                  {i === progress && running && <div className="mt-2 text-[11px] text-accent">执行中…</div>}
                </div>
                {i < ordered.length - 1 && (
                  <div className="mx-3 flex flex-col items-center text-dim">
                    <span className="text-xl leading-none">→</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card space-y-3">
        <h2 className="text-sm font-semibold">手动触发</h2>
        <div className="flex flex-wrap items-center gap-3">
          <select className={sel} value={sid} onChange={(e) => setSid(Number(e.target.value))}>
            {sources.length === 0 && <option value="">（无数据源）</option>}
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}（{s.source_type} · T{s.tier}）
              </option>
            ))}
          </select>
          <button className="btn" disabled={running || sid === ""} onClick={run}>
            {running ? "DAG 运行中…" : "运行完整 DAG"}
          </button>
          {running && <span className="text-xs text-accent">流水线推进中，节点逐个点亮</span>}
          {!running && progress >= ordered.length && ordered.length > 0 && (
            <span className="text-xs text-low">本轮 DAG 已跑完</span>
          )}
        </div>
        <p className="text-xs text-dim">
          触发后后端以 asyncio 后台执行整条 LangGraph 链：采集入库 → 并发富化 worker → Qdrant 混合向量索引 → Neo4j 图谱同步 → 高危条目 SSE 广播。
          {dag?.schedule ? `（${dag.schedule}）` : ""} 实际运行状态可在「数据源监控」页查看。
        </p>
      </div>

      {msg && (
        <div className="card fixed bottom-6 right-6 z-50 border-accent/40 px-4 py-3 text-sm shadow-lg">
          {msg}
        </div>
      )}
    </div>
  );
}
