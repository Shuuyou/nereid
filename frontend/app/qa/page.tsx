"use client";
import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamChat } from "@/lib/api";

interface Msg { role: "user" | "assistant"; content: string; citations?: any[]; trace?: any; confidence?: number; }

const SUGGESTIONS = [
  "最近一周有哪些 AI 基础设施高危漏洞？",
  "CVE-2024-37032 的影响面与修复建议？",
  "与 Ollama 相关的漏洞还有哪些同弱点关联情报？",
  "KEV 目录中 AI 相关的在野利用漏洞有哪些？",
];

export default function QaPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [deep, setDeep] = useState(true);
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
          const t = ev.data.tool ? `调用 ${ev.data.tool}(${ev.data.hits ?? "?"} 命中)` : (ev.data.msg || "");
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

  return (
    <div className="mx-auto flex h-[calc(100vh-140px)] max-w-4xl flex-col">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">深度问答</h1>
        <p className="text-sm text-dim">跨文档检索 · 知识图谱多跳 · 可解释推理链</p>
      </div>
      <div className="card flex-1 space-y-4 overflow-y-auto">
        {msgs.length === 0 && (
          <div className="space-y-2 pt-8 text-center">
            <p className="text-dim">向 SecAgent 提问试试</p>
            <div className="mx-auto flex max-w-lg flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn-ghost text-xs" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            <div className={`inline-block max-w-[85%] rounded-xl px-4 py-2.5 text-left text-sm leading-relaxed ${
              m.role === "user" ? "bg-accent/15 text-fg" : "bg-border/60"}`}>
              {m.role === "assistant" ? (
                <div className="prose prose-invert prose-sm max-w-none [&_p]:my-1.5 [&_ul]:my-1 [&_ol]:my-1">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content || "…"}</ReactMarkdown>
                </div>
              ) : m.content}
              {m.confidence != null && (
                <div className="mt-2 border-t border-border pt-1.5 text-xs text-dim">
                  置信度 {(m.confidence * 100).toFixed(0)}%
                  {m.trace?.steps && ` · 链路: ${m.trace.steps.map((s: any) => s.step).join("→")}`}
                </div>
              )}
            </div>
            {m.citations && m.citations.length > 0 && (
              <div className="mt-1.5 max-w-[85%] space-y-1 text-left">
                {m.citations.map((c) => (
                  <a key={c.n} href={c.url || `/items/${c.item_id}`} target={c.url ? "_blank" : "_self"}
                    className="block rounded border border-border px-2 py-1 text-xs text-dim hover:text-accent">
                    [{c.n}] {c.title}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        {status && <div className="text-sm text-accent">{status}</div>}
        <div ref={bottom} />
      </div>
      <div className="mt-3 flex gap-2">
        <button
          className={`btn-ghost text-xs shrink-0 ${deep ? "text-accent" : "text-low"}`}
          onClick={() => setDeep((d) => !d)}
          title={deep ? "深度模式：Agent 工具编排+多跳推理（较慢）" : "快速模式：直接检索生成（≤10s）"}>
          {deep ? "深度" : "快速"}
        </button>
        <input className="input flex-1" placeholder="提问 AI 安全情报… (Enter 发送)"
          value={input} disabled={busy}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()} />
        <button className="btn" onClick={() => send()} disabled={busy}>{busy ? "思考中…" : "发送"}</button>
      </div>
    </div>
  );
}
