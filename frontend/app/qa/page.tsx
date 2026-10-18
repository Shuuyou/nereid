"use client";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SendHorizontal, Zap, Brain, ExternalLink, ChevronDown } from "lucide-react";
import { streamChat } from "@/lib/api";

interface Msg { role: "user" | "assistant"; content: string; citations?: any[]; trace?: any; confidence?: number; }

const SUGGESTIONS = [
  "最近一周有哪些 AI 基础设施高危漏洞？",
  "CVE-2024-37032 的影响面与修复建议？",
  "我们内网部署了 Ollama 和 Milvus 2.4，请分析面临的风险。",
  "哪些 AI 基础设施漏洞已被 CISA KEV 收录？攻击链共性？",
];

const STEP_ZH: Record<string, string> = {
  extract: "实体提取", route: "意图路由", tool_call: "工具调用", agent_evidence: "Agent取证",
  fallback_retrieve: "兜底检索", retrieve: "混合检索", kg_expand: "图谱扩展", context: "组装",
  generate: "生成", cve_direct: "CVE直连", kev: "KEV直查", agent_stop: "Agent收敛",
};

export default function QaPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [deep, setDeep] = useState(true);
  const [openTrace, setOpenTrace] = useState<Record<number, boolean>>({});
  const bottom = useRef<HTMLDivElement>(null);

  async function send(q?: string) {
    const question = (q ?? input).trim();
    if (!question || busy) return;
    setInput(""); setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: question }, { role: "assistant", content: "" }]);
    try {
      let acc = "", cites: any[] = [], trace: any = null, conf = 0;
      for await (const ev of streamChat(question, sessionId, deep)) {
        if (ev.type === "status") {
          if (ev.data.session_id) setSessionId(ev.data.session_id);
          const t = ev.data.tool
            ? `工具 ${ev.data.tool} · ${ev.data.hits ?? "?"} 命中`
            : (ev.data.msg || "");
          setStatus(t);
        } else if (ev.type === "token") {
          acc += ev.data.t;
          setMsgs((m) => { const a = [...m]; a[a.length - 1] = { ...a[a.length - 1], content: acc }; return a; });
          setStatus("");
        } else if (ev.type === "citations") {
          cites = ev.data.citations || [];
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

  return (
    <div className="mx-auto flex h-[calc(100vh-140px)] max-w-4xl flex-col">
      <div className="mb-4 flex items-end justify-between">
        <div>
          <h1 className="text-[17px] font-semibold tracking-[-0.01em]">深度问答</h1>
          <p className="mt-0.5 text-[12px] text-faint">跨文档检索 · 知识图谱多跳 · 可解释推理链</p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-line p-0.5 text-[11px]">
          {([[true, "深度", Brain], [false, "快速", Zap]] as const).map(([v, label, Icon]) => (
            <button key={label} onClick={() => setDeep(v)}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 transition-colors ${
                deep === v ? "bg-white/[0.08] text-fg" : "text-faint hover:text-dim"}`}
              title={v ? "Agent 工具编排 + 多跳推理" : "直接检索生成 ≤10s"}>
              <Icon size={11} strokeWidth={1.75} />{label}
            </button>
          ))}
        </div>
      </div>

      <div className="card flex-1 space-y-5 overflow-y-auto !bg-transparent !border-0 !p-0 pr-1">
        {msgs.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
            <div>
              <div className="font-mono text-[12px] lowercase tracking-[0.2em] text-faint">nereid·qa</div>
              <p className="mt-2 text-[15px] text-dim">向捞针提问试试——跨 4.5 万条情报与 2.9 万图谱节点推理</p>
            </div>
            <div className="flex max-w-lg flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn-ghost !py-1.5 !text-[12px]" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {msgs.map((m, i) => (
          <div key={i} className={`feed-in ${m.role === "user" ? "flex justify-end" : ""}`}>
            {m.role === "user" ? (
              <div className="max-w-[80%] rounded-2xl rounded-br-md border border-accent/20 bg-accent/[0.10] px-4 py-2.5 text-[13.5px] leading-relaxed text-fg">
                {m.content}
              </div>
            ) : (
              <div className="w-full max-w-[92%]">
                <div className="rounded-2xl rounded-bl-md border border-line bg-panel px-4 py-3">
                  <div className="md">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content || "…"}</ReactMarkdown>
                  </div>
                  {(m.confidence != null || m.trace?.steps) && (
                    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line/60 pt-2 text-[11px] text-faint">
                      {m.confidence != null && (
                        <span className="flex items-center gap-1.5">
                          <span className="h-1.5 w-10 overflow-hidden rounded-full bg-white/[0.07]">
                            <span className={`block h-full rounded-full ${m.confidence >= 0.6 ? "bg-low" : m.confidence >= 0.35 ? "bg-medium" : "bg-critical"}`}
                              style={{ width: `${Math.round(m.confidence * 100)}%` }} />
                          </span>
                          置信度 <span className="tabular-nums text-dim">{Math.round(m.confidence * 100)}%</span>
                        </span>
                      )}
                      {m.trace?.steps && (
                        <button className="flex items-center gap-1 hover:text-dim"
                          onClick={() => setOpenTrace((o) => ({ ...o, [i]: !o[i] }))}>
                          推理链 {m.trace.steps.length} 步
                          <ChevronDown size={11} className={`transition-transform ${openTrace[i] ? "rotate-180" : ""}`} />
                        </button>
                      )}
                    </div>
                  )}
                  {openTrace[i] && m.trace?.steps && (
                    <div className="mt-2 space-y-1 border-l border-line pl-3">
                      {m.trace.steps.map((s: any, j: number) => (
                        <div key={j} className="flex items-center gap-2 text-[11px]">
                          <span className="dot bg-accent/60" />
                          <span className="text-dim">{STEP_ZH[s.step] || s.step}</span>
                          {s.ms != null && <span className="mono text-faint">{s.ms}ms</span>}
                          {s.hits != null && <span className="text-faint">·{s.hits} 命中</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-1.5 space-y-1 pl-1">
                    {m.citations.map((c) => (
                      <a key={c.n} href={c.url || `/items/${c.item_id}`} target={c.url ? "_blank" : "_self"}
                        className="group flex items-center gap-2 truncate rounded-md border border-line/60 bg-panel/60 px-2 py-1.5 text-[11px] text-dim transition-colors hover:border-linestrong hover:text-fg">
                        <span className="mono shrink-0 text-accent/80">[{c.n}]</span>
                        <span className="truncate">{c.title}</span>
                        <ExternalLink size={10} className="ml-auto shrink-0 opacity-0 transition-opacity group-hover:opacity-60" />
                      </a>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {status && (
          <div className="flex items-center gap-2 pl-1 text-[12px]">
            <span className="dot bg-accent dot-glow-accent breathe" />
            <span className="shimmer font-medium">{status}</span>
          </div>
        )}
        <div ref={bottom} />
      </div>

      <div className="composer mt-3 flex items-center gap-2 rounded-2xl border border-line bg-panel p-2 transition-shadow duration-200">
        <input className="flex-1 bg-transparent px-3 py-1.5 text-[13.5px] text-fg placeholder:text-faint focus:outline-none"
          placeholder="提问 AI 安全情报… (Enter 发送)"
          value={input} disabled={busy}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()} />
        <button className="btn !rounded-xl" onClick={() => send()} disabled={busy || !input.trim()}>
          {busy ? <span className="breathe">思考中</span> : <SendHorizontal size={14} strokeWidth={2} />}
        </button>
      </div>
    </div>
  );
}
