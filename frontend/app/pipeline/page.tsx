"use client";
import { useEffect, useRef, useState } from "react";
import { API, api } from "@/lib/api";
import { SpecRow, SpecDot, PageHeader, St, Empty } from "@/components/ui";
import { Check, X, Play } from "lucide-react";

interface DagNode { id: string; label: string; desc: string }
interface Dag { engine?: string; nodes: DagNode[]; edges: [string, string][]; schedule?: string }
interface RunRec {
  run_id: string; source_id: string; status: string; current?: string;
  started_at?: string; finished_at?: string; error?: string; nodes?: Record<string, string>;
}

type NodeState = "pending" | "running" | "done" | "error";

const STATE_TXT: Record<NodeState, string> = { pending: "等待", running: "执行中", done: "完成", error: "失败" };

function dur(a?: string, b?: string) {
  if (!a || !b) return "—";
  const ms = new Date(b).getTime() - new Date(a).getTime();
  if (ms < 0) return "—";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}
function fmtMs(ms: number) {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

export default function PipelinePage() {
  const [dag, setDag] = useState<Dag | null>(null);
  const [sources, setSources] = useState<any[]>([]);
  const [sid, setSid] = useState<number | "">("");
  const [run, setRun] = useState<RunRec | null>(null);
  const [runs, setRuns] = useState<RunRec[]>([]);
  const [msg, setMsg] = useState("");
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);
  // 节点完成时间戳（前端观测真实状态迁移记录，非模拟动画）
  const doneAt = useRef<Record<string, number>>({});

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

  function observe(rec: RunRec) {
    for (const [n, st] of Object.entries(rec.nodes || {})) {
      if (st === "done" && doneAt.current[n] === undefined) doneAt.current[n] = Date.now();
    }
  }

  async function triggerRun() {
    if (!sid || run?.status === "running") return;
    try {
      const r = await fetch(`${API}/api/pipeline/run/${sid}`, { method: "POST" });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const d = await r.json();
      doneAt.current = {};
      setRun({ run_id: d.run_id, source_id: String(sid), status: "running", nodes: {} });
      toast(`DAG 已启动 run_id=${d.run_id}`);
      // 真实状态轮询：后端 Redis 回写每节点完成情况
      if (poll.current) clearInterval(poll.current);
      poll.current = setInterval(async () => {
        try {
          const sr = await fetch(`${API}/api/pipeline/run/${d.run_id}`, { cache: "no-store" });
          if (!sr.ok) return;
          const rec: RunRec = await sr.json();
          observe(rec);
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

  async function inspect(r: RunRec) {
    // 点历史行 → 拉该 run 快照回放到 DAG 视图
    try {
      const sr = await fetch(`${API}/api/pipeline/run/${r.run_id}`, { cache: "no-store" });
      if (sr.ok) { const rec = await sr.json(); setRun(rec); }
    } catch { /* ignore */ }
  }

  const nodeState = (id: string): NodeState => {
    if (!run) return "pending";
    if (run.status === "done") return "done";
    if (run.status === "error") return run.nodes?.[id] === "done" ? "done" : run.current === id ? "error" : "pending";
    if (run.nodes?.[id] === "done") return "done";
    if (run.current === id) return "running";
    return "pending";
  };

  /** 相邻节点完成时间差 → 边标签（仅本轮前端观测到的真实迁移） */
  const edgeMs = (prevId: string, curId: string): string | null => {
    const a = doneAt.current[prevId]; const b = doneAt.current[curId];
    if (a === undefined || b === undefined || b < a) return null;
    return fmtMs(b - a);
  };

  const nodeCls = (id: string) => {
    const st = nodeState(id);
    if (st === "done") return "border-ok/40";
    if (st === "running") return "border-accent/60";
    if (st === "error") return "border-err/50";
    return "border-line";
  };

  const running = run?.status === "running";

  return (
    <div>
      <SpecRow>
        <span>FIG_06</span><SpecDot />
        <span>PIPELINE</span><SpecDot />
        <span>{dag?.engine || "LANGGRAPH"} DAG</span>
        <span className="ml-auto flex items-center gap-1.5 normal-case tracking-normal">
          <St tone={running ? "live" : "dim"}>{running ? "RUNNING" : "IDLE"}</St>
        </span>
      </SpecRow>

      <PageHeader title="LangGraph 流水线" desc={dag?.schedule || "collect → enrich → index → kg → notify"}
        right={
          <div className="flex items-center gap-2">
            <select className="input w-64" value={sid} onChange={(e) => setSid(Number(e.target.value))}>
              {sources.length === 0 && <option value="">（无数据源）</option>}
              {sources.map((s) => (
                <option key={s.id} value={s.id}>{s.name}（{s.source_type} · T{s.tier}）</option>
              ))}
            </select>
            <button className="btn btn-acc" disabled={running || sid === ""} onClick={triggerRun}>
              <Play size={12} strokeWidth={1.75} />{running ? "DAG 运行中…" : "运行完整 DAG"}
            </button>
          </div>
        } />

      {/* ── DAG 画布：n8n 式紧凑矩形节点 ── */}
      <div className="overflow-x-auto rounded-md border border-line bg-panel px-6 py-5">
        {ordered.length === 0 ? (
          <Empty text="无 DAG 数据" hint="后端未连接" />
        ) : (
          <div className="flex min-w-max items-stretch">
            {ordered.map((n, i) => {
              const st = nodeState(n.id);
              const ms = i > 0 ? edgeMs(ordered[i - 1].id, n.id) : null;
              return (
                <div key={n.id} className="flex items-center">
                  {i > 0 && (
                    /* 边：hairline + 耗时标签 */
                    <div className="mx-1 flex w-14 flex-col items-center justify-center gap-0.5">
                      <span className={`num text-[10px] ${ms ? "text-dim" : "text-transparent"}`}>{ms || "0"}</span>
                      <div className={`h-px w-full ${st === "pending" ? "bg-line2" : "bg-ok/50"}`} />
                      <span className={`font-mono text-[9px] leading-none ${st === "pending" ? "text-faint" : "text-ok/70"}`}>▸</span>
                    </div>
                  )}
                  {/* 节点卡 */}
                  <div
                    title={`${n.id} · ${n.desc}\n状态：${STATE_TXT[st]}`}
                    className={`relative w-[168px] rounded-[8px] border bg-panel px-3 py-2.5 transition-colors ${nodeCls(n.id)} ${
                      st === "pending" ? "opacity-70" : ""}`}
                  >
                    {st === "running" && (
                      <span className="pointer-events-none absolute -inset-px rounded-[8px] border border-accent"
                        style={{ animation: "pulse-dot 2.4s ease-in-out infinite" }} />
                    )}
                    <div className="flex items-center gap-2">
                      <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border font-mono text-[9.5px] ${
                        st === "done" ? "border-ok/40 bg-ok/10 text-ok"
                        : st === "error" ? "border-err/40 bg-err/10 text-err"
                        : st === "running" ? "border-accent/40 bg-accent/10 text-accent"
                        : "border-line bg-surface text-faint"}`}>
                        {st === "done" ? <Check size={10} strokeWidth={2.5} />
                          : st === "error" ? <X size={10} strokeWidth={2.5} />
                          : i + 1}
                      </span>
                      <span className="truncate text-[12.5px] font-medium text-fg">{n.label}</span>
                      <span className="mono ml-auto text-[9.5px] text-faint">{n.id}</span>
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-dim">{n.desc}</p>
                    {st === "running" && (
                      <div className="mt-1.5 flex items-center gap-1.5 text-[10.5px] text-accent">
                        <span className="h-1 w-1 rounded-full bg-accent" style={{ animation: "pulse-dot 1.4s ease-in-out infinite" }} />
                        执行中…
                      </div>
                    )}
                    {st === "error" && <div className="mt-1.5 text-[10.5px] text-err">节点失败</div>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {/* 运行状态行 */}
        {run && (
          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line pt-3 text-[11.5px] text-dim">
            <span>RUN <span className="mono text-fg">{run.run_id}</span></span>
            <SpecDot />
            <span>SRC <span className="mono text-fg">{run.source_id}</span></span>
            {run.current && <><SpecDot /><span>NODE <span className="mono text-accent">{run.current}</span></span></>}
            <SpecDot />
            {run.status === "done" ? <St tone="ok">DONE</St>
              : run.status === "error" ? <St tone="err">ERROR</St>
              : <St tone="live">RUNNING</St>}
            {run.started_at && run.finished_at && (
              <><SpecDot /><span className="num">{dur(run.started_at, run.finished_at)}</span></>
            )}
            {run.error && <span className="mono text-[10.5px] text-err">{run.error}</span>}
          </div>
        )}
      </div>

      {/* ── 运行历史 ── */}
      <div className="sect">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="sect-title">运行历史</h2>
          <span className="font-mono text-[10.5px] text-faint">REDIS pipeline:runs · LAST 20</span>
        </div>
        {runs.length === 0 ? (
          <Empty text="暂无运行记录" hint="选择数据源并点击「运行完整 DAG」" />
        ) : (
          <table className="dt">
            <thead>
              <tr><th>run_id</th><th>source</th><th>状态</th><th>节点进度</th><th>开始</th><th>结束</th><th className="r">耗时</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const done = Object.values(r.nodes || {}).filter((v) => v === "done").length;
                const total = ordered.length || Object.keys(r.nodes || {}).length;
                return (
                  <tr key={r.run_id} className="cursor-pointer" onClick={() => inspect(r)}
                    title="点击回放该次运行的节点状态">
                    <td className="mono text-[11.5px] text-accent">{r.run_id}</td>
                    <td className="text-[12px]">{r.source_id}</td>
                    <td>
                      {r.status === "done" ? <St tone="ok">done</St>
                        : r.status === "error" ? <St tone="err">error</St>
                        : <St tone="live">{r.status}</St>}
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <div className="h-[3px] w-14 rounded-full bg-surface2">
                          <div className={`h-full rounded-full ${r.status === "error" ? "bg-err" : "bg-ok"}`}
                            style={{ width: `${total ? Math.round((done / total) * 100) : 0}%` }} />
                        </div>
                        <span className="num text-faint">{done}/{total}</span>
                      </div>
                    </td>
                    <td className="num text-faint">{(r.started_at || "").slice(5, 19).replace("T", " ") || "—"}</td>
                    <td className="num text-faint">{(r.finished_at || "").slice(5, 19).replace("T", " ") || "—"}</td>
                    <td className="r num text-dim">{dur(r.started_at, r.finished_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
