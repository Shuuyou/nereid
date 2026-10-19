"use client";
import { Children, isValidElement, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SendHorizontal, Square, Plus, ChevronRight, ExternalLink, MessageSquareText } from "lucide-react";
import { streamChat, api } from "@/lib/api";
import { remarkChips } from "@/lib/remark-chips";

interface Msg { role: "user" | "assistant"; content: string; citations?: any[]; trace?: any; confidence?: number; }
interface Sess { id: string; title: string; ts: number; }

const SUGGESTIONS = [
  "最近一周有哪些 AI 基础设施高危漏洞？",
  "CVE-2024-37032 的影响面与修复建议？",
  "我们内网部署了 Ollama 和 Milvus 2.4，请分析面临的风险。",
  "哪些 AI 基础设施漏洞已被 CISA KEV 收录？攻击链共性？",
];

const STEP_ZH: Record<string, string> = {
  extract: "实体提取", route: "意图路由", tool_call: "工具调用", agent_evidence: "Agent 取证",
  fallback_retrieve: "兜底检索", retrieve: "混合检索", kg_expand: "图谱扩展", context: "组装",
  generate: "生成", cve_direct: "CVE 直连", kev: "KEV 直查", agent_stop: "Agent 收敛",
};

const LS_KEY = "nereid-qa-sessions";
function loadSessions(): Sess[] {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch { return []; }
}

function confBand(c?: number): { label: string; cls: string } {
  if (c == null) return { label: "—", cls: "text-faint" };
  if (c >= 0.6) return { label: "置信 · 高", cls: "text-ok" };
  if (c >= 0.35) return { label: "置信 · 中", cls: "text-warn" };
  return { label: "置信 · 低", cls: "text-err" };
}

/** [n] 引用 chip + hover 预览卡（Consensus/Glean 式：hover 即见证据摘录） */
function CitationChip({ n, cite, onCite }: { n: number; cite?: any; onCite: (n: number) => void }) {
  if (!cite) return <span className="cite opacity-50">{n}</span>;
  return (
    <span className="group/cite relative inline-block">
      <button type="button" className="cite" onClick={() => onCite(n)}>{n}</button>
      <span className="pointer-events-none invisible absolute bottom-full left-0 z-50 pb-2 opacity-0 transition duration-150 delay-200 group-hover/cite:visible group-hover/cite:opacity-100">
        <span className="block w-64 rounded-md border border-line2 bg-overlay p-2.5 text-left shadow-2xl">
          <span className="block truncate text-[11.5px] font-medium text-fg">{cite.title}</span>
          {cite.snippet && (
            <span className="mt-1 line-clamp-3 block text-[11px] leading-snug text-dim">{cite.snippet}</span>
          )}
          <span className="mt-1.5 block font-mono text-[9.5px] text-faint">
            {cite.url ? "external" : `item:${String(cite.item_id).slice(0, 8)}`} · 点击定位证据
          </span>
        </span>
      </span>
    </span>
  );
}

const ENT_HREF: Record<string, (id: string) => string> = {
  CVE: (id) => `/items?cve=${id}`,
  GHSA: (id) => `https://github.com/advisories/${id}`,
  CWE: (id) => `https://cwe.mitre.org/data/definitions/${id.slice(4)}.html`,
  CAPEC: (id) => `https://capec.mitre.org/data/definitions/${id.slice(6)}.html`,
  "AML.T": (id) => `https://atlas.mitre.org/techniques/${id}`,
  T: (id) => `https://attack.mitre.org/techniques/${id.replace(".", "/")}`,
};
function entHref(id: string): { href: string; external: boolean } {
  const kind = id.startsWith("CVE-") ? "CVE" : id.startsWith("GHSA-") ? "GHSA"
    : id.startsWith("CWE-") ? "CWE" : id.startsWith("CAPEC-") ? "CAPEC"
    : id.startsWith("AML.") ? "AML.T" : "T";
  const href = ENT_HREF[kind](id);
  return { href, external: href.startsWith("http") };
}

/** 实体 chip：mono 小标签，点击进对应详情/外库 */
function EntityChip({ id }: { id: string }) {
  const { href, external } = entHref(id);
  return (
    <a href={href} target={external ? "_blank" : "_self"} rel={external ? "noreferrer" : undefined}
      className="mx-px inline-flex items-center rounded-[4px] border border-line bg-surface px-1 font-mono text-[10.5px] leading-[16px] text-dim transition-colors hover:border-accent/50 hover:text-accent">
      {id}
    </a>
  );
}

/** 长实体清单折叠：默认露 4 个 + "+N" 展开（GraphRAG count-then-drill 的 UI 侧） */
function EntityGroup({ children }: { children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const kids = Children.toArray(children);
  const chips = kids.filter((k) => isValidElement(k));
  if (chips.length <= 4) return <>{children}</>;
  return (
    <span className="inline">
      {chips.slice(0, 4)}
      <span className="text-[11px] text-faint"> 等 </span>
      {!open && (
        <button type="button" onClick={() => setOpen(true)}
          className="mx-px inline-flex items-center rounded-[4px] border border-line bg-surface px-1 font-mono text-[10.5px] leading-[16px] text-accent transition-colors hover:border-accent/50">
          +{chips.length - 4} 展开
        </button>
      )}
      {open && chips.slice(4)}
    </span>
  );
}

/** 回答正文：[n]→可点 chip、实体 ID→chip、长枚举→折叠组；流式时尾部缓冲半成品 */
function AnswerBody({ content, streaming, cites, onCite }: {
  content: string; streaming: boolean; cites?: any[]; onCite: (n: number) => void;
}) {
  const md = useMemo(
    // 流式中抠掉末尾未完成的 "[1" 式半成品引用，防抖动
    () => (streaming ? content.replace(/\[\d{0,3}$/, "") : content),
    [content, streaming],
  );
  const citeMap = useMemo(() => {
    const m = new Map<number, any>();
    (cites || []).forEach((c) => m.set(c.n, c));
    return m;
  }, [cites]);
  return (
    <div className={`prose-a ${streaming && content ? "caret" : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkChips]}
        components={{
          "citation-chip": ({ n }: any) => (
            <CitationChip n={parseInt(n, 10)} cite={citeMap.get(parseInt(n, 10))} onCite={onCite} />
          ),
          "entity-chip": ({ id }: any) => <EntityChip id={id} />,
          "entity-group": ({ children }: any) => <EntityGroup>{children}</EntityGroup>,
          a: ({ href, children }: any) => (
            <a href={href} target="_blank" rel="noreferrer">{children}</a>
          ),
        } as any}
      >
        {md}
      </ReactMarkdown>
    </div>
  );
}

export default function QaPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [deep, setDeep] = useState(true);
  const [tab, setTab] = useState<"evi" | "trace">("evi");
  const [citeFocus, setCiteFocus] = useState<number | null>(null);
  const [openTrace, setOpenTrace] = useState<Record<number, boolean>>({});
  const bottom = useRef<HTMLDivElement>(null);
  const esRef = useRef<boolean>(false);

  useEffect(() => { setSessions(loadSessions()); }, []);

  function saveSession(id: string, title: string) {
    setSessions((prev) => {
      const rest = prev.filter((s) => s.id !== id);
      const next = [{ id, title: title.slice(0, 30), ts: Date.now() }, ...rest].slice(0, 20);
      try { localStorage.setItem(LS_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  }

  async function openSession(s: Sess) {
    if (busy) return;
    setSessionId(s.id); setMsgs([]); setStatus("");
    try {
      const h = await api.qaHistory(s.id);
      setMsgs((h.messages || []).map((m: any) => ({
        role: m.role, content: m.content, citations: m.citations, trace: m.trace, confidence: m.confidence,
      })));
    } catch { /* 历史不可恢复则从空会话继续 */ }
  }

  function newSession() {
    if (busy) return;
    setSessionId(null); setMsgs([]); setStatus(""); setOpenTrace({});
  }

  async function send(q?: string) {
    const question = (q ?? input).trim();
    if (!question || busy) return;
    setInput(""); setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: question }, { role: "assistant", content: "" }]);
    let firstQ = question;
    try {
      let acc = "", cites: any[] = [], trace: any = null, conf: number | undefined;
      for await (const ev of streamChat(question, sessionId, deep)) {
        if (ev.type === "status") {
          if (ev.data.session_id && !sessionId) {
            setSessionId(ev.data.session_id);
            saveSession(ev.data.session_id, firstQ);
          }
          const t = ev.data.tool
            ? `${STEP_ZH[ev.data.tool] || ev.data.tool} · ${ev.data.hits ?? "?"} 命中`
            : (ev.data.msg || "");
          setStatus(t);
        } else if (ev.type === "token") {
          acc += ev.data.t;
          setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], content: acc }; return a; });
          setStatus("");
        } else if (ev.type === "citations") {
          cites = ev.data.citations || [];
          // 提前写入当前消息——流式期间行内 chip 即可 hover 预览
          setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], citations: cites }; return a; });
          setTab("evi");
        } else if (ev.type === "trace") {
          trace = ev.data.trace;
        } else if (ev.type === "done") {
          conf = ev.data.confidence;
          setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], citations: cites, trace, confidence: conf }; return a; });
        } else if (ev.type === "error") {
          acc += "\n\n[服务错误] " + ev.data.error;
          setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], content: acc }; return a; });
        }
      }
    } catch (e: any) {
      setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], content: "连接失败：" + String(e) }; return a; });
    }
    setBusy(false); setStatus("");
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length]);

  const lastA = [...msgs].reverse().find((m) => m.role === "assistant" && (m.citations?.length || m.trace));
  const totalMs = lastA?.trace?.steps?.reduce((s: number, x: any) => s + (x.ms || 0), 0);
  const maxMs = lastA?.trace?.steps?.reduce((m: number, x: any) => Math.max(m, x.ms || 0), 1) ?? 1;
  const band = confBand(lastA?.confidence);

  return (
    /* 三栏工作台：会话 │ 对话列 │ Evidence/Trace */
    <div className="-mx-6 -my-5 flex h-screen">

      {/* ── 左：会话列表 ── */}
      <div className="flex w-[200px] shrink-0 flex-col border-r border-line bg-panel">
        <div className="flex h-11 items-center justify-between border-b border-line px-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-faint">调查会话</span>
          <button onClick={newSession} className="rounded-[5px] p-1 text-faint transition-colors hover:bg-surface2 hover:text-fg" title="新调查">
            <Plus size={14} strokeWidth={2} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-1.5">
          {sessions.length === 0 && (
            <div className="px-2 py-6 text-center text-[11px] leading-relaxed text-faint">
              暂无历史调查<br />提问自动建档
            </div>
          )}
          {sessions.map((s) => (
            <button key={s.id} onClick={() => openSession(s)}
              className={`mb-px block w-full truncate rounded-[5px] px-2 py-1.5 text-left text-[12px] transition-colors ${
                sessionId === s.id ? "bg-surface2 text-fg" : "text-dim hover:bg-surface hover:text-fg"}`}>
              {s.title}
            </button>
          ))}
        </div>
        <div className="border-t border-line p-1.5">
          <div className="flex items-center gap-1 rounded-[5px] p-0.5 text-[11px]">
            {([[true, "深度"], [false, "快速"]] as const).map(([v, label]) => (
              <button key={label} onClick={() => setDeep(v)}
                className={`flex-1 rounded-[4px] py-1 transition-colors ${
                  deep === v ? "bg-surface2 font-medium text-fg" : "text-faint hover:text-dim"}`}
                title={v ? "Agent 工具编排 + 多跳推理" : "直接检索生成 ≤10s"}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── 中：无边框对话列 ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[700px] px-6 py-6">
            {msgs.length === 0 && (
              <div className="flex h-full min-h-[60vh] flex-col justify-center">
                <div className="spec-row"><span>FIG_QA</span><span className="dot" /><span>跨文档检索 · KG 多跳 · 可解释推理</span></div>
                <p className="mt-3 text-[15px] leading-relaxed text-dim">
                  向捞针提问——横跨 <span className="mono text-fg">45k</span> 条情报与
                  <span className="mono text-fg"> 29k</span> 图谱节点推理作答
                </p>
                <div className="mt-6 space-y-px">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)}
                      className="group flex w-full items-center gap-2 rounded-[6px] px-2 py-2 text-left text-[13px] text-dim transition-colors hover:bg-surface hover:text-fg">
                      <ChevronRight size={12} className="text-faint transition-colors group-hover:text-accent" />
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {msgs.map((m, i) => (
              <div key={i} className="rise mb-6">
                {m.role === "user" ? (
                  /* 用户问题：左侧 hairline 引用条，非气泡 */
                  <div className="border-l-2 border-accent/50 pl-4">
                    <div className="text-[13.5px] font-medium leading-relaxed text-fg">{m.content}</div>
                  </div>
                ) : (
                  /* 助手回答：无边框纯文本流 */
                  <div>
                    {m.content
                      ? <AnswerBody content={m.content} streaming={busy && i === msgs.length - 1}
                          cites={m.citations}
                          onCite={(n) => { setTab("evi"); setCiteFocus(n); }} />
                      : (busy && i === msgs.length - 1
                        ? <span className="text-faint"> </span>
                        : <span className="text-faint">…</span>)}

                    {/* 判定条：置信 band + 推理链折叠行 */}
                    {(m.confidence != null || m.trace?.steps) && !busy && (
                      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-line pt-2.5 text-[11.5px]">
                        {m.confidence != null && (() => { const b = confBand(m.confidence); return (
                          <span className={`font-mono text-[10.5px] uppercase tracking-[0.06em] ${b.cls}`}>{b.label}</span>
                        ); })()}
                        {m.citations && m.citations.length > 0 && (
                          <button onClick={() => setTab("evi")} className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-faint transition-colors hover:text-accent">
                            {m.citations.length} SOURCES
                          </button>
                        )}
                        {m.trace?.steps && (
                          <button onClick={() => setOpenTrace((o) => ({ ...o, [i]: !o[i] }))}
                            className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-faint transition-colors hover:text-accent">
                            {openTrace[i] ? "▾" : "▸"} TRACE {m.trace.steps.length} STEPS
                          </button>
                        )}
                      </div>
                    )}
                    {openTrace[i] && m.trace?.steps && (
                      <div className="mt-2 space-y-px rounded-md border border-line py-1">
                        {m.trace.steps.map((s: any, j: number) => (
                          <div key={j} className="flex items-center gap-2.5 px-3 py-1 text-[11.5px]">
                            <span className="w-4 text-right font-mono text-[10px] text-faint">{j + 1}</span>
                            <span className="text-dim">{STEP_ZH[s.step] || s.step}</span>
                            {s.hits != null && <span className="font-mono text-[10px] text-faint">{s.hits} hits</span>}
                            {s.ms != null && <span className="ml-auto font-mono text-[10px] tnum text-faint">{s.ms}ms</span>}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* 引用行：mono 编号 chip */}
                    {m.citations && m.citations.length > 0 && (
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        {m.citations.map((c) => (
                          <a key={c.n} href={c.url || `/items/${c.item_id}`} target={c.url ? "_blank" : "_self"}
                            title={c.title}
                            className="group inline-flex max-w-[280px] items-center gap-1.5 truncate rounded-[5px] border border-line bg-panel px-2 py-1 text-[11px] text-dim transition-colors hover:border-line2 hover:text-fg">
                            <span className="font-mono text-[10px] text-accent">[{c.n}]</span>
                            <span className="truncate">{c.title}</span>
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* 动态单行状态：就地演变 */}
            {status && (
              <div className="mb-6 flex items-center gap-2 text-[12px] text-dim">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" style={{ animation: "pulse-dot 1.4s ease-in-out infinite" }} />
                <span className="font-mono text-[11px]">{status}</span>
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>

        {/* composer */}
        <div className="shrink-0 border-t border-line px-6 py-3">
          <div className="mx-auto flex max-w-[700px] items-center gap-2">
            <input
              className="input h-9 flex-1 !text-[13px]"
              placeholder="提问 AI 安全情报… @实体 / Enter 发送"
              value={input} disabled={busy}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()} />
            <button className="btn btn-acc h-9" onClick={() => send()} disabled={busy || !input.trim()}>
              {busy ? <Square size={12} /> : <SendHorizontal size={13} strokeWidth={2} />}
            </button>
          </div>
        </div>
      </div>

      {/* ── 右：Evidence / Trace 面板 ── */}
      <div className="flex w-[290px] shrink-0 flex-col border-l border-line bg-panel">
        <div className="flex h-11 items-center gap-4 border-b border-line px-3">
          {([["evi", `证据 ${lastA?.citations?.length || ""}`], ["trace", "推理链"]] as const).map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`h-full border-b-2 font-mono text-[10.5px] uppercase tracking-[0.08em] transition-colors ${
                tab === k ? "border-accent text-fg" : "border-transparent text-faint hover:text-dim"}`}>
              {l}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto">
          {tab === "evi" && (
            <div className="p-2">
              {!lastA?.citations?.length && (
                <div className="px-2 py-8 text-center text-[11.5px] leading-relaxed text-faint">
                  <MessageSquareText size={16} strokeWidth={1.5} className="mx-auto mb-2 opacity-60" />
                  提问后此处列出<br />答案引用的情报条目
                </div>
              )}
              {lastA?.citations?.map((c: any) => (
                <a key={c.n} href={c.url || `/items/${c.item_id}`} target={c.url ? "_blank" : "_self"}
                  className={`group mb-1 block rounded-[6px] border px-2.5 py-2 transition-colors ${
                    citeFocus === c.n ? "border-accent/50 bg-[rgba(90,180,196,0.14)]" : "border-transparent hover:border-line hover:bg-surface"}`}>
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono text-[10px] text-accent">[{c.n}]</span>
                    <span className="min-w-0 flex-1 truncate text-[12px] leading-snug text-fg">{c.title}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2 pl-6 font-mono text-[10px] text-faint">
                    <span>{c.url ? "external" : `item:${String(c.item_id).slice(0, 8)}`}</span>
                    <ExternalLink size={9} className="opacity-0 transition-opacity group-hover:opacity-60" />
                  </div>
                </a>
              ))}
            </div>
          )}
          {tab === "trace" && (
            <div className="p-3">
              {!lastA?.trace?.steps ? (
                <div className="px-1 py-8 text-center text-[11.5px] text-faint">本轮尚无推理轨迹</div>
              ) : (
                <>
                  <div className="mb-3 flex items-baseline justify-between">
                    <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint">SPAN WATERFALL</span>
                    <span className="font-mono text-[10px] tnum text-dim">{totalMs}ms</span>
                  </div>
                  {lastA.trace.steps.map((s: any, j: number) => (
                    <div key={j} className="mb-2.5">
                      <div className="flex items-baseline justify-between text-[11px]">
                        <span className="text-dim">{STEP_ZH[s.step] || s.step}</span>
                        <span className="font-mono text-[10px] tnum text-faint">{s.ms ?? "—"}ms</span>
                      </div>
                      <div className="mt-1 h-[3px] rounded bg-surface2">
                        <div className="h-full rounded bg-accent/70"
                          style={{ width: `${Math.max(2, ((s.ms || 0) / maxMs) * 100)}%` }} />
                      </div>
                      {s.hits != null && <div className="mt-0.5 font-mono text-[9.5px] text-faint">{s.hits} hits</div>}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
