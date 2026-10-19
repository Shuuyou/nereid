"use client";
import { Children, isValidElement, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowUp, Square, Plus, ChevronRight, ExternalLink, MessageSquareText, Check, X, ArrowUpRight, Copy, Paperclip, FileText } from "lucide-react";
import { streamChat, api } from "@/lib/api";
import { remarkChips } from "@/lib/remark-chips";
import { SevPill } from "@/components/ui";
import { LayerTag } from "@/components/cards";

interface Msg {
  role: "user" | "assistant"; content: string; citations?: any[]; trace?: any;
  confidence?: number; followups?: string[]; aborted?: boolean; abstain?: boolean;
}
interface Sess { id: string; title: string; ts: number; }

const SUGGESTIONS = [
  "最近一周有哪些 AI 基础设施高危漏洞？",
  "CVE-2024-37032 的影响面与修复建议？",
  "我们内网部署了 Ollama 和 Milvus 2.4，请分析面临的风险。",
  "哪些 AI 基础设施漏洞已被 CISA KEV 收录？攻击链共性？",
];

const STEP_ZH: Record<string, string> = {
  extract: "实体识别", route: "意图路由", tool_call: "工具调用", agent_evidence: "Agent 取证",
  fallback_retrieve: "兜底补检", retrieve: "混合检索", kg_expand: "图谱扩展", context: "证据组装",
  generate: "生成", cve_direct: "CVE 直连", kev: "KEV 直查", agent_stop: "Agent 收敛",
  fast_path: "快速检索", kev_facts: "KEV 事实", recent_facts: "窗口枚举",
  time_filter: "时效过滤", time_filter_retry: "时效放宽", time_filter_dropped: "时效放宽",
  severity_filter: "级别过滤", agent_error: "Agent 降级", prepare_error: "降级",
  // 工具名（ev.data.tool 会带着原名进来，必须翻译——不给用户看函数名）
  retrieve_intel: "检索情报库", get_item_detail: "读取情报卡", list_kev: "查 KEV 清单",
};

const LS_KEY = "nereid-qa-sessions";
function loadSessions(): Sess[] {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch { return []; }
}

/** 正文里实际引用的 [n] 集合 */
function citedNsOf(content?: string): Set<number> {
  return new Set(Array.from((content || "").matchAll(/\[(\d{1,3})\]/g)).map((x) => +x[1]));
}

function confBand(c?: number): { label: string; cls: string; bar: string } {
  /* 与 PeekDrawer.confTone 同口径：0-0.25 弃答 / 0.25-0.4 低 / 0.4-0.7 中 / ≥0.7 高 */
  if (c == null) return { label: "—", cls: "text-faint", bar: "bg-surface2" };
  if (c >= 0.7) return { label: "高", cls: "text-ok", bar: "bg-ok" };
  if (c >= 0.4) return { label: "中", cls: "text-warn", bar: "bg-warn" };
  return { label: "低", cls: "text-err", bar: "bg-err" };
}

interface SpineStep { step: string; ms: number; hits?: number; running?: boolean; error?: boolean }
function fmtMs(ms?: number) {
  if (ms == null) return "";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}
/** 推理脊椎：纵向步骤条骑线节点（Grok/Devin 式），流式累积、完成可收 receipt */
function TraceSpine({ steps, streaming, elapsedNow, onJump }: {
  steps: SpineStep[]; streaming: boolean; elapsedNow?: number; onJump?: () => void;
}) {
  if (!steps.length && !streaming) return null;
  return (
    <div className="relative mb-3 ml-[7px] border-l border-line2 pl-4">
      {steps.map((s, i) => {
        /* running 步显示实时跳动时长（elapsedNow - 步骤开始时累计ms），完成后显示差分值 */
        const liveMs = s.running && elapsedNow != null ? Math.max(0, elapsedNow - s.ms) : null;
        return (
          <button key={i} type="button" onClick={onJump}
            className="group relative flex w-full items-center gap-2 py-[5px] text-left">
            <span className={`absolute -left-[21px] flex h-3.5 w-3.5 items-center justify-center rounded-full border bg-panel ${
              s.error ? "border-err" : s.running ? "border-accent" : "border-line2"}`}>
              {s.running && <span className="h-1.5 w-1.5 rounded-full bg-accent" style={{ animation: "pulse-dot 1.4s ease-in-out infinite" }} />}
              {s.error && <X size={8} className="text-err" />}
              {!s.running && !s.error && <Check size={8} className="text-ok" />}
            </span>
            <span className={`flex-1 truncate text-[12px] transition-colors group-hover:text-fg ${s.running ? "shimmer-text" : "text-dim"}`}>
              {STEP_ZH[s.step] || s.step}
              {s.hits != null && <span className={s.running ? "" : "text-faint"}> {s.hits} 命中</span>}
            </span>
            <span className={`font-mono text-[11px] tnum ${s.running ? "text-accent" : "text-faint"}`}>
              {liveMs != null ? fmtMs(liveMs) : fmtMs(s.ms)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** [n] 引用 chip + hover 预览卡（Consensus/Glean 式：hover 即见证据摘录） */
function CitationChip({ n, cite, onCite }: { n: number; cite?: any; onCite: (n: number) => void }) {
  if (!cite) return <span className="cite opacity-50">{n}</span>;
  return (
    <span className="group/cite relative inline-block">
      <button type="button" className="cite" onClick={() => onCite(n)}>{n}</button>
      <span className="pointer-events-none invisible absolute bottom-full left-0 z-50 pb-2 opacity-0 transition duration-150 delay-200 group-hover/cite:visible group-hover/cite:opacity-100">
        <span className="block w-64 rounded-md border border-line2 bg-overlay p-2.5 text-left shadow-2xl">
          <span className="block truncate text-[12px] font-medium text-fg">{cite.title}</span>
          {cite.snippet && (
            <span className="mt-1 line-clamp-3 block text-[12px] leading-snug text-dim">{cite.snippet}</span>
          )}
          <span className="mt-1.5 block font-mono text-[11px] text-faint">
            {cite.url ? "external" : `item:${String(cite.item_id).slice(0, 8)}`} · 点击定位证据
          </span>
        </span>
      </span>
    </span>
  );
}

/** 复制回答（Perplexity 答案动作行首钮） */
function CopyBtn({ text }: { text: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" title="复制回答"
      onClick={() => { navigator.clipboard?.writeText(text).catch(() => {}); setOk(true); setTimeout(() => setOk(false), 1500); }}
      className="flex h-8 w-8 items-center justify-center rounded-full text-dim transition-colors hover:bg-surface2 hover:text-fg">
      {ok ? <Check size={15} className="text-ok" /> : <Copy size={15} />}
    </button>
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
      className="mx-px inline-flex items-center rounded-[4px] border border-line bg-surface px-1 font-mono text-[11px] leading-[16px] text-dim transition-colors hover:border-accent/50 hover:text-accent">
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
      <span className="text-[12px] text-faint"> 等 </span>
      {!open && (
        <button type="button" onClick={() => setOpen(true)}
          className="mx-px inline-flex items-center rounded-[4px] border border-line bg-surface px-1 font-mono text-[11px] leading-[16px] text-accent transition-colors hover:border-accent/50">
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
  const [spine, setSpine] = useState<SpineStep[]>([]);
  const [deep, setDeep] = useState(true);
  const [tab, setTab] = useState<"evi" | "trace">("evi");
  const [citeFocus, setCiteFocus] = useState<number | null>(null);
  const [showUncited, setShowUncited] = useState(false);
  const [openTrace, setOpenTrace] = useState<Record<number, boolean>>({});
  const [peekId, setPeekId] = useState<string | null>(null);
  const [peekShown, setPeekShown] = useState(false);
  const [peekItem, setPeekItem] = useState<any>(null);
  const [peekErr, setPeekErr] = useState(false);
  const peekCloseT = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [atts, setAtts] = useState<{ id: string; name: string; size: number; thumb?: string; text?: string; ioc?: { cve: number; ip: number; hash: number } }[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const dragN = useRef(0);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setSessions(loadSessions()); }, []);

  function saveSession(id: string, title: string) {
    setSessions((prev) => {
      const rest = prev.filter((s) => s.id !== id);
      const next = [{ id, title: title.slice(0, 30), ts: Date.now() }, ...rest].slice(0, 20);
      try { localStorage.setItem(LS_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  }

  /** 顶栏标题同步（layout HeaderTitle 监听） */
  function reportTitle(t: string | null) {
    window.dispatchEvent(new CustomEvent("nereid:title", { detail: t }));
  }

  async function openSession(s: Sess) {
    if (busy) return;
    setSessionId(s.id); setMsgs([]); setStatus(""); closePeek();
    reportTitle(s.title);
    try {
      const h = await api.qaHistory(s.id);
      setMsgs((h.messages || []).map((m: any) => ({
        role: m.role, content: m.content, citations: m.citations, trace: m.trace, confidence: m.confidence,
      })));
    } catch { /* 历史不可恢复则从空会话继续 */ }
  }

  function newSession() {
    if (busy) return;
    setSessionId(null); setMsgs([]); setStatus(""); setOpenTrace({}); closePeek();
    reportTitle(null);
  }

  function stop() {
    abortRef.current?.abort();
  }

  /** [n] chip → 右栏证据卡：切 tab + 滚动定位 + 高亮（若抽屉开着先收起，否则高亮被盖住） */
  function focusCite(n: number) {
    if (peekId) closePeek();
    setTab("evi");
    setCiteFocus(n);
    requestAnimationFrame(() => {
      document.getElementById(`evi-${n}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }

  /** 证据 peek：内部 item 就地右侧抽屉预览（不离开对话上下文），自动切到 evi */
  function openPeek(itemId: string) {
    if (peekCloseT.current) { clearTimeout(peekCloseT.current); peekCloseT.current = null; }
    setTab("evi");
    setPeekItem(null); setPeekErr(false);
    setPeekId(itemId);
    api.item(itemId).then(setPeekItem).catch(() => setPeekErr(true));
  }
  function closePeek() {
    setPeekShown(false);
    if (peekCloseT.current) clearTimeout(peekCloseT.current);
    peekCloseT.current = setTimeout(() => { setPeekId(null); peekCloseT.current = null; }, 320);
  }

  // 抽屉滑入：挂载后双 rAF 让 translateX(100%) 先落一帧再过渡到 0
  useEffect(() => {
    if (!peekId) return;
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => setPeekShown(true)));
    return () => cancelAnimationFrame(raf);
  }, [peekId]);

  // Esc 关闭抽屉
  useEffect(() => {
    if (!peekId) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closePeek(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [peekId]);

  /** 附件入口统一收口：粘贴/拖拽/选文件都走这里；文本类读内容+IOC计数，图像存缩略图并标"不解析" */
  async function addFiles(files: Iterable<File> | ArrayLike<File>) {
    const stamp = new Date().toLocaleString("sv-SE").replace(/:/g, ".").slice(0, 19);
    for (const f of Array.from(files)) {
      const id = `a${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
      const generic = !f.name || /^(image|clipboard|blob)/i.test(f.name);
      const name = generic
        ? `${f.type.startsWith("image/") ? "截图" : "粘贴文件"} ${stamp}.${(f.type.split("/")[1] || "png")}`
        : f.name;
      const att: any = { id, name, size: f.size };
      if (f.type.startsWith("image/")) {
        att.thumb = await new Promise<string>((res) => {
          const r = new FileReader(); r.onload = () => res(String(r.result)); r.readAsDataURL(f);
        });
      } else if (f.size < 10 * 1024 * 1024) {
        const t = await f.text().catch(() => undefined);
        if (t != null) {
          att.text = t;
          att.ioc = {
            cve: new Set(t.match(/\bCVE-\d{4}-\d{4,7}\b/gi) || []).size,
            ip: new Set(t.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || []).size,
            hash: new Set(t.match(/\b[a-f0-9]{64}\b/gi) || []).size,
          };
        }
      }
      setAtts((a) => [...a, att]);
    }
  }

  async function send(q?: string) {
    let question = (q ?? input).trim();
    if (!question && !atts.length) return;
    if (!question || busy) return;
    // 附件并入问题：文本类 head80%+tail20% 截断内联（日志最新在尾），图像留诚实标记位
    if (atts.length) {
      const MAX = 30_000;
      const parts = atts.map((a) => {
        if (!a.text) return `\n\n[附件 ${a.name}（图像/二进制，未送模型解析）]`;
        const t = a.text.length > MAX
          ? `${a.text.slice(0, Math.floor(MAX * 0.8))}\n…[省略 ${a.text.length - MAX} 字符]…\n${a.text.slice(-Math.floor(MAX * 0.2))}`
          : a.text;
        return `\n\n[附件 ${a.name}]\n\`\`\`\n${t}\n\`\`\``;
      });
      question += parts.join("");
    }
    setInput(""); setAtts([]); setBusy(true); setSpine([]); setStatus(""); setElapsed(0); closePeek();
    const t0 = Date.now();
    timerRef.current = setInterval(() => setElapsed(Date.now() - t0), 400);
    // 气泡只显示用户原文+附件标记，附件内容进 API 问题不进气泡
    const shown = (q ?? input).trim() + (atts.length ? `（附 ${atts.length} 个附件）` : "");
    setMsgs((m) => [...m, { role: "user", content: shown }, { role: "assistant", content: "" }]);
    const abort = new AbortController();
    abortRef.current = abort;
    const firstQ = shown;
    try {
      let acc = "", cites: any[] = [], trace: any = null, conf: number | undefined, fups: string[] = [];
      for await (const ev of streamChat(question, sessionId, deep, abort.signal)) {
        if (ev.type === "status") {
          if (ev.data.session_id && !sessionId) {
            setSessionId(ev.data.session_id);
            saveSession(ev.data.session_id, firstQ);
            reportTitle(firstQ.slice(0, 30));
          }
          const t = ev.data.tool
            ? `${STEP_ZH[ev.data.tool] || ev.data.tool} · ${ev.data.hits ?? "?"} 命中`
            : (ev.data.msg || "");
          setStatus(t);
          // 脊椎累积：同步骤更新，异步骤追加（ms 为累计值，显示时差分）
          if (ev.data.step) {
            setSpine((s) => {
              const a = [...s];
              const prev = a[a.length - 1];
              if (prev && prev.step === ev.data.step) {
                a[a.length - 1] = { ...prev, ms: ev.data.ms ?? prev.ms, hits: ev.data.hits ?? prev.hits };
              } else {
                if (prev) prev.running = false;
                a.push({ step: ev.data.step, ms: ev.data.ms ?? 0, hits: ev.data.hits, running: true });
              }
              return a;
            });
          }
        } else if (ev.type === "token") {
          // token 到达 = 生成阶段已在交付——脊椎步骤全部标完成，防"卡在生成"假象
          if (acc === "") setSpine((s) => s.map((x) => ({ ...x, running: false })));
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
          fups = ev.data.followups || [];
          const abst = !!ev.data.abstain;
          setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], citations: cites, trace, confidence: conf, followups: fups, abstain: abst }; return a; });
        } else if (ev.type === "error") {
          acc += "\n\n[服务错误] " + ev.data.error;
          setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], content: acc }; return a; });
        }
      }
    } catch (e: any) {
      if (abort.signal.aborted) {
        // 用户主动中止：保留已流出的部分答案
        setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], aborted: true }; return a; });
      } else {
        setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], content: "连接失败：" + String(e) }; return a; });
      }
    }
    setSpine((s) => s.map((x) => ({ ...x, running: false })));
    setBusy(false); setStatus("");
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    abortRef.current = null;
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length]);

  const lastA = [...msgs].reverse().find((m) => m.role === "assistant" && (m.citations?.length || m.trace));
  // trace.steps[].ms 是累计耗时 → 差分得单步耗时
  const traceSteps: any[] = lastA?.trace?.steps || [];
  const stepDurs: number[] = traceSteps.map((s: any, j: number, arr: any[]) =>
    j + 1 < arr.length ? Math.max(0, (arr[j + 1].ms ?? s.ms) - (s.ms ?? 0)) : Math.max(0, s.ms ?? 0));
  const totalMs = traceSteps.length ? traceSteps[traceSteps.length - 1].ms : 0;
  const maxMs = stepDurs.reduce((m, x) => Math.max(m, x), 1);

  return (
    /* 三栏工作台：会话 │ 对话列 │ Evidence/Trace
       高度=视口-顶栏49px（外层 padding wrapper 是 auto 高，h-full 解析不到——必须显式 calc） */
    <div className="-mx-6 -my-5 flex h-[calc(100dvh-49px)]">

      {/* ── 左：会话列表 ── */}
      <div className="flex w-[240px] shrink-0 flex-col border-r border-line bg-panel">
        <div className="flex h-12 items-center justify-between px-3.5">
          <span className="text-[12px] font-medium text-faint">最近调查</span>
          <button onClick={newSession} className="rounded-[6px] p-1.5 text-faint transition-colors hover:bg-surface2 hover:text-fg" title="新调查">
            <Plus size={14} strokeWidth={2} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {sessions.length === 0 && (
            <div className="px-2 py-6 text-center text-[12px] leading-relaxed text-faint">
              暂无历史调查<br />提问自动建档
            </div>
          )}
          {(() => {
            /* ChatGPT 式按日分组：今天/昨天/前7天/更早 */
            const day = 86400000, now = Date.now();
            const g: [string, Sess[]][] = [["今天", []], ["昨天", []], ["前 7 天", []], ["更早", []]];
            for (const s of sessions) {
              const d = now - s.ts;
              g[d < day ? 0 : d < 2 * day ? 1 : d < 7 * day ? 2 : 3][1].push(s);
            }
            return g.filter(([, l]) => l.length).map(([label, list]) => (
              <div key={label} className="mb-1">
                <div className="px-2.5 pb-1 pt-3 text-[11px] font-medium text-faint">{label}</div>
                {list.map((s) => (
                  <button key={s.id} onClick={() => openSession(s)}
                    className={`mb-px flex h-9 w-full items-center truncate rounded-[10px] px-2.5 text-left text-[13.5px] transition-colors ${
                      sessionId === s.id ? "bg-surface2 font-medium text-fg" : "text-dim hover:bg-surface hover:text-fg"}`}>
                    <span className="truncate">{s.title}</span>
                  </button>
                ))}
              </div>
            ));
          })()}
        </div>
      </div>

      {/* ── 中：无边框对话列（整栏是 drop 热区，遮罩提示） ── */}
      <div className="relative flex min-w-0 flex-1 flex-col"
        onDragEnter={(e) => { if (Array.from(e.dataTransfer?.types || []).includes("Files")) { e.preventDefault(); dragN.current++; setDragOver(true); } }}
        onDragOver={(e) => { if (Array.from(e.dataTransfer?.types || []).includes("Files")) e.preventDefault(); }}
        onDragLeave={() => { if (--dragN.current <= 0) { dragN.current = 0; setDragOver(false); } }}
        onDrop={(e) => { e.preventDefault(); dragN.current = 0; setDragOver(false); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files); }}>
        {dragOver && (
          <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-panel/80 backdrop-blur-[2px]">
            <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-accent/50 bg-canvas/70 px-10 py-8">
              <Paperclip size={20} className="text-accent" />
              <div className="text-[14px] font-medium text-fg">拖放文件到此处</div>
              <div className="font-mono text-[11px] text-faint">.log .txt .csv · IOC 清单 · 截图（图像仅存证不解析）</div>
            </div>
          </div>
        )}
        <div className="flex-1 overflow-y-auto overflow-x-hidden">
          <div className="mx-auto max-w-[660px] px-6 py-6">
            {msgs.length === 0 && (
              <div className="flex h-full min-h-[60vh] flex-col justify-center">
                <div className="spec-row"><span>FIG_QA</span><span className="spec-sep" /><span>跨文档检索</span><span className="spec-sep" /><span>KG 多跳 · 可解释</span></div>
                <p className="mt-3 text-[15px] leading-relaxed text-dim">
                  向捞针提问——横跨 <span className="mono text-fg">45k</span> 条情报与
                  <span className="mono text-fg"> 29k</span> 图谱节点推理作答
                  <span className="display-en italic mt-2 block text-[14px] text-faint">
                    ask in plain language, get a cited answer
                  </span>
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
              <div key={i} className="rise mb-7">
                {m.role === "user" ? (
                  /* 用户消息：右对齐 offset 灰气泡（Perplexity 实测 rounded-20/px4/py2.5/15px） */
                  <div className="flex justify-end">
                    <div className="max-w-[80%] whitespace-pre-wrap rounded-[20px] bg-surface2 px-4 py-2.5 text-[15px] leading-6 text-fg">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  /* 助手回答：无边框纯文本流 */
                  <div>
                    {/* 弃答标记：系统知道自己不知道——安全产品的 trust 机制（非通用对话话术） */}
                    {m.abstain && (
                      <div className="mb-2 flex items-center gap-2 text-[12px]">
                        <span className="h-1.5 w-1.5 rounded-full bg-warn" />
                        <span className="font-medium text-warn">置信度不足 · 证据缺口</span>
                        <button onClick={() => { setTab("evi"); setShowUncited(true); }}
                          className="text-faint underline-offset-2 transition-colors hover:text-dim hover:underline">
                          查看未引用候选
                        </button>
                      </div>
                    )}
                    {/* 推理脊椎：进行中就地累积 → 完成就地收拢成 receipt（计数统一用权威 trace.steps） */}
                    {i === msgs.length - 1 && busy && spine.length > 0 && (
                      <TraceSpine steps={spine} streaming elapsedNow={elapsed} onJump={() => setTab("trace")} />
                    )}
                    {!busy && (m.trace?.steps?.length || (i === msgs.length - 1 && spine.length)) ? (
                      <button type="button" onClick={() => setOpenTrace((o) => ({ ...o, [i]: !o[i] }))}
                        className="group mb-3 ml-[7px] flex items-center gap-2 text-[12px] text-faint transition-colors hover:text-dim">
                        <Check size={11} className="text-ok" />
                        <span>推理链 {(m.trace?.steps || spine).length} 步{m.trace?.total_ms ? ` · 用时 ${fmtMs(m.trace.total_ms)}` : ""}</span>
                        <ChevronRight size={11} className={`transition-transform ${openTrace[i] ? "rotate-90" : ""}`} />
                      </button>
                    ) : null}
                    {openTrace[i] && m.trace?.steps && (
                      <TraceSpine steps={m.trace.steps.map((s: any, j: number, arr: any[]) => ({
                        step: s.step,
                        ms: j + 1 < arr.length ? Math.max(0, (arr[j + 1].ms ?? s.ms) - s.ms) : (s.dur_ms ?? s.ms),
                        hits: s.hits, error: s.status === "error",
                      }))} streaming={false} onJump={() => setTab("trace")} />
                    )}
                    {busy && i === msgs.length - 1 && elapsed > 30000 && (
                      <div className="mb-3 ml-[7px] text-[12px] text-faint">
                        深度推理耗时较长属正常，可随时 ■ 中止
                      </div>
                    )}
                    {m.content
                      ? <AnswerBody content={m.content} streaming={busy && i === msgs.length - 1}
                          cites={m.citations} onCite={focusCite} />
                      : (busy && i === msgs.length - 1
                        ? <span className="text-faint"> </span>
                        : <span className="text-faint">…</span>)}
                    {m.aborted && (
                      <div className="mt-2 font-mono text-[11px] uppercase tracking-[0.06em] text-warn">
                        ▪ 已中止——可修改问题重发
                      </div>
                    )}

                    {/* 动作行：Perplexity 式图标行（复制/来源/推理链/置信度），低噪音 */}
                    {(m.confidence != null || m.trace?.steps || m.citations?.length) && !busy && (
                      <div className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-1.5">
                        <CopyBtn text={m.content} />
                        {m.confidence != null && (() => { const b = confBand(m.confidence); return (
                          <span className="ml-1 flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1" title={`答案置信度 ${m.confidence.toFixed(2)}`}>
                            <span className="relative h-[3px] w-10 rounded-full bg-surface2">
                              <span className={`absolute inset-y-0 left-0 rounded-full ${b.bar}`}
                                style={{ width: `${Math.round(m.confidence * 100)}%` }} />
                            </span>
                            <span className={`tnum font-mono text-[11px] ${b.cls}`}>{m.confidence.toFixed(2)}</span>
                          </span>
                        ); })()}
                        {m.citations && m.citations.length > 0 && (() => {
                          const cited = citedNsOf(m.content).size;
                          return (
                            <button onClick={() => setTab("evi")}
                              className="rounded-full px-2 py-1 text-[12px] text-faint transition-colors hover:bg-surface hover:text-fg">
                              {cited} 来源
                            </button>
                          );
                        })()}
                        {m.trace?.steps && (
                          <button onClick={() => setTab("trace")}
                            className="rounded-full px-2 py-1 text-[12px] text-faint transition-colors hover:bg-surface hover:text-fg">
                            推理链
                          </button>
                        )}
                      </div>
                    )}

                    {/* 引用行：只展示正文真正引用的 [n]（Perplexity 纪律：检索候选≠来源） */}
                    {m.citations && m.citations.length > 0 && (() => {
                      const citedNs = citedNsOf(m.content);
                      const shown = m.citations.filter((c) => citedNs.has(c.n));
                      if (!shown.length) return null;
                      return (
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {shown.map((c) => {
                            const cls = "group inline-flex max-w-[280px] items-center gap-1.5 truncate rounded-[5px] border border-line bg-panel px-2 py-1 text-[12px] text-dim transition-colors hover:border-line2 hover:text-fg";
                            const inner = (<>
                              <span className="font-mono text-[11px] text-accent">[{c.n}]</span>
                              <span className="truncate">{c.title}</span>
                            </>);
                            // 外部链接照旧 _blank；内部 item 开右侧 peek 抽屉而非跳页
                            return c.url ? (
                              <a key={c.n} href={c.url} target="_blank" rel="noreferrer" title={c.title} className={cls}>{inner}</a>
                            ) : (
                              <button key={c.n} type="button" title={c.title} className={cls}
                                onClick={() => c.item_id && openPeek(String(c.item_id))}>{inner}</button>
                            );
                          })}
                        </div>
                      );
                    })()}

                    {/* 追问（Perplexity Related 真品形态：分组标签+整宽分隔行+右置箭头） */}
                    {m.followups && m.followups.length > 0 && !busy && (
                      <div className="mt-8">
                        <div className="px-1 pb-1 text-[13px] font-medium text-dim">追问</div>
                        {m.followups.slice(0, 3).map((fq) => (
                          <button key={fq} onClick={() => send(fq)}
                            className="group flex w-full items-center gap-3 border-b border-line px-1 py-3.5 text-left text-[14px] text-dim transition-colors last:border-0 hover:bg-surface/60 hover:text-fg">
                            <span className="min-w-0 flex-1 truncate">{fq}</span>
                            <ChevronRight size={14} className="shrink-0 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* 进行中状态行（气泡下方对话区内）：shimmer 扫光步骤文案 + 已用计时 */}
            {busy && (
              <div className="mb-6 flex items-baseline gap-3">
                <span className="shimmer-text text-[14px]">{status || "正在生成回答…"}</span>
                <span className="font-mono text-[11px] tnum text-faint">已用 {fmtMs(elapsed)}</span>
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>

        {/* composer：Perplexity 式胶囊容器——内嵌附件chip行+模式切换+圆形发送/停止钮；支持粘贴/拖拽 */}
        <div className="shrink-0 px-6 pb-5 pt-2">
          <div className={`mx-auto max-w-[660px] rounded-[24px] border bg-panel shadow-[0_2px_4px_-2px_rgba(32,24,18,0.06),0_8px_24px_-12px_rgba(32,24,18,0.12)] transition-colors focus-within:border-[rgba(33,31,38,0.4)] ${
            dragOver ? "border-accent" : "border-line2"}`}>
            {/* 附件 chip 行 */}
            {atts.length > 0 && (
              <div className="flex gap-2 overflow-x-auto px-3.5 pt-3">
                {atts.map((a) => a.thumb ? (
                  /* 图片 tile：48px 缩略图 + "不解析"诚实徽标（纯文本模型，图仅存证） */
                  <span key={a.id} className="group relative h-12 w-12 shrink-0">
                    <img src={a.thumb} alt={a.name} title={`${a.name} · 图片仅存证不参与分析`} className="h-12 w-12 rounded-[10px] border border-line2 object-cover" />
                    <span className="absolute bottom-0.5 left-0.5 rounded-[3px] bg-panel/95 px-1 font-mono text-[9px] text-warn">不解析</span>
                    <button type="button" onClick={() => setAtts((x) => x.filter((y) => y.id !== a.id))}
                      className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-fg text-panel opacity-0 transition-opacity group-hover:opacity-100"
                      title="移除"><X size={9} /></button>
                  </span>
                ) : (
                  /* 文档 chip：图标+文件名+IOC计数/大小 */
                  <span key={a.id} className="group relative flex h-[34px] shrink-0 items-center gap-1.5 rounded-[9px] border border-line bg-surface px-2"
                    title={`${a.name} · ${(a.size / 1024).toFixed(1)}KB`}>
                    <FileText size={13} className="text-faint" />
                    <span className="max-w-[150px] truncate text-[12px] text-fg">{a.name}</span>
                    <span className="font-mono text-[10.5px] text-faint">
                      {a.ioc?.cve ? `CVE×${a.ioc.cve}` : a.ioc?.ip ? `IP×${a.ioc.ip}` : a.ioc?.hash ? `HASH×${a.ioc.hash}` : `${(a.size / 1024).toFixed(0)}K`}
                    </span>
                    <button type="button" onClick={() => setAtts((x) => x.filter((y) => y.id !== a.id))}
                      className="text-faint transition-colors hover:text-err" title="移除"><X size={11} /></button>
                  </span>
                ))}
              </div>
            )}
            <textarea
              onPaste={(e) => {
                // ★ items 必须在 handler 返回前同步收完（之后即失效）
                const files: File[] = [];
                for (const it of Array.from(e.clipboardData?.items || [])) {
                  if (it.kind === "file") { const f = it.getAsFile(); if (f) files.push(f); }
                }
                if (files.length) { e.preventDefault(); addFiles(files); return; }
                // 大段文本粘贴（>4k字符）自动转附件 chip，不灌进输入框
                const t = e.clipboardData?.getData("text/plain");
                if (t && t.length > 4000) {
                  e.preventDefault();
                  addFiles([new File([t], `粘贴的文本 ${new Date().toLocaleString("sv-SE").replace(/:/g, ".")}.txt`, { type: "text/plain" })]);
                }
              }}
              ref={(el) => { if (el) { el.style.height = "0px"; el.style.height = `${Math.min(el.scrollHeight, 200)}px`; } }}
              className="w-full resize-none bg-transparent px-5 pt-4 text-[15px] leading-7 text-fg outline-none placeholder:text-faint"
              rows={2}
              placeholder={busy ? "运行中——可继续输入，发送将排队为下一个问题" : "提问 AI 安全情报…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            <div className="flex items-center gap-1 px-3 pb-3">
              {/* 附件上传（ChatGPT 左位 + 钮） */}
              <input ref={fileRef} type="file" multiple className="hidden"
                accept="image/png,image/jpeg,image/webp,image/gif,.txt,.log,.csv,.json,.md,.xml,.yaml,.ioc,.tsv,text/*"
                onChange={(e) => { addFiles(e.target.files || []); e.target.value = ""; }} />
              <button type="button" onClick={() => fileRef.current?.click()} title="上传附件（截图/日志/IOC 清单）"
                className="flex h-8 w-8 items-center justify-center rounded-full text-dim transition-colors hover:bg-surface2 hover:text-fg">
                <Paperclip size={15} strokeWidth={1.75} />
              </button>
              {/* 模式切换：深度=Agent 工具编排 / 快速=直接检索（Perplexity 模式 chip 位） */}
              <div className="flex items-center rounded-full bg-surface2/70 p-0.5 text-[12px]">
                {([[true, "深度"], [false, "快速"]] as const).map(([v, label]) => (
                  <button key={label} onClick={() => setDeep(v)}
                    className={`rounded-full px-2.5 py-1 transition-colors ${
                      deep === v ? "bg-panel font-medium text-fg shadow-sm" : "text-faint hover:text-dim"}`}
                    title={v ? "Agent 工具编排 + 多跳推理" : "直接检索生成 ≤10s"}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="flex-1" />
              {busy ? (
                <button onClick={stop} title="中止当前生成"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-[#211f26] text-white transition-all hover:opacity-85">
                  <Square size={11} fill="currentColor" />
                </button>
              ) : (
                <button onClick={() => send()} disabled={!input.trim()}
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-[#211f26] text-white transition-all hover:opacity-85 disabled:bg-surface2 disabled:text-faint">
                  <ArrowUp size={15} strokeWidth={2.2} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── 右：Evidence / Trace 面板（Perplexity 式紧凑来源列表，一屏内呈现） ── */}
      <div className="relative flex w-[320px] shrink-0 flex-col overflow-hidden border-l border-line bg-panel">
        <div className="flex h-12 items-center gap-1 px-3">
          {([["evi", `证据 ${lastA?.citations?.length || ""}`], ["trace", "推理链"]] as const).map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`rounded-full px-3 py-1 text-[12px] transition-colors ${
                tab === k ? "bg-surface2 font-medium text-fg" : "text-faint hover:text-dim"}`}>
              {l}
            </button>
          ))}
        </div>
        {/* 研判条：置信/引用率/耗时——去掉内部路由名与 · 分隔（内部标签不外露） */}
        {lastA && (() => {
          const citedN = citedNsOf(lastA.content).size;
          const totalN = lastA.citations?.length || 0;
          return (
            <div className="flex items-center gap-3 border-t border-line px-3 py-1.5 font-mono text-[10.5px] text-faint">
              {lastA.confidence != null && <span className="tnum">置信 {lastA.confidence.toFixed(2)}</span>}
              {totalN > 0 && <span className="tnum">引用 {citedN}/{totalN}</span>}
              {lastA.trace?.total_ms != null && <span className="tnum ml-auto">{fmtMs(lastA.trace.total_ms)}</span>}
            </div>
          );
        })()}
        <div className="flex-1 overflow-y-auto border-t border-line">
          {tab === "evi" && (
            <div className="p-2">
              {!lastA?.citations?.length && (
                <div className="px-2 py-8 text-center text-[12px] leading-relaxed text-faint">
                  <MessageSquareText size={16} strokeWidth={1.5} className="mx-auto mb-2 opacity-60" />
                  提问后此处列出<br />答案引用的情报条目
                </div>
              )}
              {(() => {
                const citedNs = citedNsOf(lastA?.content);
                const cited = (lastA?.citations || []).filter((c: any) => citedNs.has(c.n));
                const rest = (lastA?.citations || []).filter((c: any) => !citedNs.has(c.n));
                const host = (u?: string) => { try { return u ? new URL(u).hostname.replace(/^www\./, "") : ""; } catch { return ""; } };
                /* 单行紧凑来源行：n chip + severity色点 + 标题 + 研判meta（KEV>CVE>EPSS>域名） */
                const SEV_DOT: Record<string, string> = {
                  critical: "#d92638", high: "#e8622c", medium: "#b07c00", low: "#5c8a3f",
                };
                const Card = ({ c, dimmed }: { c: any; dimmed?: boolean }) => {
                  const cls = `group mb-px flex w-full items-center gap-2 rounded-[6px] px-2 py-[7px] text-left transition-colors ${
                    citeFocus === c.n ? "bg-[rgba(21,122,119,0.12)]"
                      : "hover:bg-surface"} ${dimmed ? "opacity-50" : ""}`;
                  const sevDot = c.severity && SEV_DOT[c.severity];
                  const meta = dimmed ? "候选"
                    : c.is_kev ? "KEV"
                    : c.cve ? String(c.cve).split(",")[0]
                    : c.epss != null ? `${Math.round(c.epss * 100)}%`
                    : c.url ? host(c.url) : "库内";
                  const inner = (<>
                    <span className="cite shrink-0">{c.n}</span>
                    {sevDot && <span className="h-[6px] w-[6px] shrink-0 rounded-full" style={{ background: sevDot }} title={c.severity} />}
                    <span className="min-w-0 flex-1 truncate text-[12px] leading-snug text-fg">{c.title}</span>
                    <span className={`shrink-0 font-mono text-[10px] ${c.is_kev && !dimmed ? "font-medium text-err" : "text-faint"}`}>
                      {meta}
                    </span>
                    {c.url
                      ? <ExternalLink size={9} className="shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-70" />
                      : <ChevronRight size={10} className="shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-70" />}
                  </>);
                  // 外部链接照旧 _blank；内部 item 开右侧 peek 抽屉而非跳页
                  return c.url ? (
                    <a id={`evi-${c.n}`} href={c.url} target="_blank" rel="noreferrer" title={c.title} className={cls}>{inner}</a>
                  ) : (
                    <button id={`evi-${c.n}`} type="button" title={c.title} className={cls}
                      onClick={() => c.item_id && openPeek(String(c.item_id))}>{inner}</button>
                  );
                };
                return (<>
                  {cited.map((c: any) => <Card key={c.n} c={c} />)}
                  {rest.length > 0 && (
                    showUncited
                      ? <>
                          <button onClick={() => setShowUncited(false)}
                            className="mb-1 mt-2 w-full px-2 text-left text-[11px] text-faint transition-colors hover:text-dim">
                            ▾ 其他检索候选 {rest.length}
                          </button>
                          {rest.map((c: any) => <Card key={c.n} c={c} dimmed />)}
                        </>
                      : <button onClick={() => setShowUncited(true)}
                          className="mt-2 w-full rounded-[6px] px-2 py-1.5 text-left text-[11px] text-faint transition-colors hover:bg-surface hover:text-dim">
                          ▸ 其他检索候选 {rest.length}（未被引用）
                        </button>
                  )}
                </>);
              })()}
            </div>
          )}
          {tab === "trace" && (
            <div className="p-3">
              {!lastA?.trace?.steps ? (
                <div className="px-1 py-8 text-center text-[12px] text-faint">本轮尚无推理轨迹</div>
              ) : (
                <>
                  <div className="mb-3 flex items-baseline justify-between">
                    <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-faint">SPAN WATERFALL</span>
                    <span className="font-mono text-[11px] tnum text-dim">{totalMs}ms</span>
                  </div>
                  {lastA.trace.steps.map((s: any, j: number) => (
                    <div key={j} className="mb-2.5">
                      <div className="flex items-baseline justify-between text-[12px]">
                        <span className="text-dim">{STEP_ZH[s.step] || s.step}</span>
                        <span className="font-mono text-[11px] tnum text-faint">{fmtMs(stepDurs[j]) || "—"}</span>
                      </div>
                      <div className="mt-1 h-[3px] rounded bg-surface2">
                        <div className="h-full rounded bg-accent/70"
                          style={{ width: `${Math.max(2, (stepDurs[j] / maxMs) * 100)}%` }} />
                      </div>
                      {s.hits != null && <div className="mt-0.5 font-mono text-[11px] text-faint">{s.hits} hits</div>}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* 证据 peek 抽屉：面板内覆盖滑入（全宽贴边直角、无遮罩、不遮对话列） */}
        {peekId && (
          <div role="dialog" aria-label="证据预览"
            className="absolute inset-0 z-20 flex flex-col bg-panel"
            style={{
              transform: peekShown ? "translateX(0)" : "translateX(101%)",
              transition: "transform 300ms var(--ease-drawer)",
              boxShadow: "-16px 0 40px -20px rgba(60, 50, 90, 0.35)",
            }}>
            <div className="flex h-11 shrink-0 items-center justify-between border-b border-line px-3">
              <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-faint">证据预览</span>
              <button onClick={closePeek} title="关闭 (Esc)"
                className="rounded-[5px] p-1 text-faint transition-colors hover:bg-surface2 hover:text-fg">
                <X size={12} strokeWidth={2} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              {peekErr ? (
                <div className="px-1 py-8 text-center text-[12px] leading-relaxed text-faint">条目加载失败</div>
              ) : !peekItem ? (
                <div className="space-y-2.5 pt-1">
                  <div className="skel h-4 w-4/5" />
                  <div className="skel h-3 w-full" />
                  <div className="skel h-3 w-full" />
                  <div className="skel h-3 w-3/5" />
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <SevPill level={peekItem.severity} />
                    {peekItem.is_kev && (
                      <span className="badge"><span className="dot" style={{ background: "#d92638" }} />KEV</span>
                    )}
                  </div>
                  <div className="mt-2 text-[13px] font-medium leading-snug text-fg">
                    {peekItem.title_zh || peekItem.title}
                  </div>
                  {(peekItem.cve_ids || []).length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {peekItem.cve_ids.map((c: string) => <span key={c} className="badge mono">{c}</span>)}
                    </div>
                  )}
                  {(peekItem.summary_zh || peekItem.summary) && (
                    <p className="mt-2.5 line-clamp-3 text-[12px] leading-relaxed text-dim">
                      {peekItem.summary_zh || peekItem.summary}
                    </p>
                  )}
                  {peekItem.ai_layer && <div className="mt-2.5"><LayerTag l={peekItem.ai_layer} /></div>}
                </>
              )}
            </div>
            <div className="shrink-0 border-t border-line p-2.5">
              <Link href={`/items/${peekId}`} className="btn btn-sm w-full justify-center">
                打开完整页<ArrowUpRight size={11} strokeWidth={2} />
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
