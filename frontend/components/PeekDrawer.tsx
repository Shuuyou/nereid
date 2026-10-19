"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Empty, SevPill, Skeleton } from "@/components/ui";
import { ArrowUpRight, Check, ChevronDown, ChevronUp, RefreshCw, Undo2, X } from "lucide-react";

/** 置信度 → 语义色（高可信 ok / 中 warn / 低 err，不吃品牌色）；复核表与 peek 抽屉共用 */
export function confTone(c?: number) {
  if (c == null) return "bg-surface2";
  if (c >= 0.7) return "bg-ok";
  if (c >= 0.4) return "bg-warn";
  return "bg-err";
}
export function confText(c?: number) {
  if (c == null) return "text-faint";
  if (c >= 0.7) return "text-ok";
  if (c >= 0.4) return "text-warn";
  return "text-err";
}

/** 传给复核动作的轻量条目（行内按钮传列表行，抽屉传详情） */
export interface PeekTarget {
  id: string;
  title?: string;
}

export interface PeekDrawerProps {
  /** 速览条目 id；null = 抽屉关闭 */
  id: string | null;
  /** 队列内索引（-1 = 不在当前队列：?peek= 直开 / 跨 tab） */
  index: number;
  /** 队列长度（n/total 计数与翻页边界禁用） */
  total: number;
  /** 列表行标题 —— 详情拉取完成前的首帧 fallback */
  title?: string;
  /** 任一复核动作进行中 → 禁用全部动作按钮 */
  busy?: boolean;
  /** 只读模式：隐藏复核动作（确认/回炉/重富化），仅留翻页与完整页外链 —— items 页速览用 */
  readonly?: boolean;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  onAct?: (it: PeekTarget, action: "confirm" | "reject") => void;
  onReEnrich?: (it: PeekTarget) => void;
}

/** 抽屉内分区标签（详情页 Rail 同式 mono 小灰） */
function Sect({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="mt-5 first:mt-0">
      <div className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.1em] text-faint">{label}</div>
      {children}
    </section>
  );
}

/**
 * Chronicle/Elastic 式右侧 peek 抽屉：400px 贴边、四角直角 r0、
 * transform-only 350ms（--ease-drawer）、遮罩 bg-ink/30 fade 200ms。
 * Esc / 点遮罩关闭；打开期间锁 body 滚动；▲▼ 队列内翻页。
 */
export function PeekDrawer({
  id, index, total, title, busy, readonly = false,
  onClose, onPrev, onNext, onAct, onReEnrich,
}: PeekDrawerProps) {
  const open = id != null;
  const [mounted, setMounted] = useState(false);
  const [shown, setShown] = useState(false);
  const [item, setItem] = useState<any>(null);
  const [err, setErr] = useState("");
  const reqRef = useRef(0);
  const lastIdRef = useRef<string | null>(null);

  /* 进出场：挂载 → 双 rAF 置 shown 播 slide-in；关闭 → 反向 transform 播完后卸载 */
  useEffect(() => {
    if (open) {
      setMounted(true);
      const raf = requestAnimationFrame(() => requestAnimationFrame(() => setShown(true)));
      return () => cancelAnimationFrame(raf);
    }
    setShown(false);
    const t = setTimeout(() => setMounted(false), 380);
    return () => clearTimeout(t);
  }, [open]);

  /* 打开期间 body overflow hidden */
  useEffect(() => {
    if (!mounted) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [mounted]);

  /* 键盘流（KYRA/StellaOps 键位）：Esc 关、j/k 或 ↑↓ 翻页、c/r/e 动作；输入框聚焦时抑制 */
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
      else if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); onNext(); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); onPrev(); }
      else if (!readonly && !busy && lastIdRef.current && onAct && onReEnrich) {
        const target: PeekTarget = { id: lastIdRef.current, title: "" };
        if (e.key === "c") { e.preventDefault(); onAct(target, "confirm"); }
        else if (e.key === "r") { e.preventDefault(); onAct(target, "reject"); }
        else if (e.key === "e") { e.preventDefault(); onReEnrich(target); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, readonly, onClose, onPrev, onNext, onAct, onReEnrich]);

  /* id 变化 → 拉详情（▲▼ 翻页同抽屉内重拉；reqRef 防乱序响应覆写） */
  useEffect(() => {
    if (!id) { setItem(null); setErr(""); return; }
    lastIdRef.current = id;
    const req = ++reqRef.current;
    setItem(null);
    setErr("");
    api.item(id)
      .then((d) => { if (reqRef.current === req) setItem(d); })
      .catch((e) => { if (reqRef.current === req) setErr(String(e)); });
  }, [id]);

  if (!mounted) return null;

  /* 关闭动画 380ms 内 id 已置 null —— 用最后非空 id 兜底 href/动作目标 */
  const effId = id ?? lastIdRef.current;
  const headTitle = item ? (item.title_zh || item.title) : (title || effId || "");
  const target: PeekTarget = { id: effId || "", title: headTitle };
  const hasPrev = index > 0;
  const hasNext = index >= 0 && index < total - 1;

  const ex = (item?.extra || {}) as Record<string, any>;
  /* 薄弱维度：与 /api/review 同口径 —— enrichment 里 status 为 error/partial 的维度名 */
  const weak = Object.entries((item?.enrichment || {}) as Record<string, any>)
    .filter(([, v]) => v && typeof v === "object" && (v.status === "error" || v.status === "partial"))
    .map(([k]) => k);
  /* 评分构成：scorers 跑过才展示，与详情页同序取前 3 */
  const scoreRows = (item && item.enrichment?.scorers
    ? ([
        item.cvss_v31_score != null && { k: "cvss31", label: "CVSS v3.1", value: item.cvss_v31_score.toFixed(1), basis: ex.cvss_source ? `src ${ex.cvss_source}` : "采集器内联" },
        item.cvss_v40_score != null && { k: "cvss40", label: "CVSS v4.0", value: item.cvss_v40_score.toFixed(1), basis: "v4.0 metric" },
        item.epss_score != null && { k: "epss", label: "EPSS", value: `${(item.epss_score * 100).toFixed(2)}%`, basis: item.epss_percentile != null ? `pctl ${(item.epss_percentile * 100).toFixed(0)}%` : "—" },
        item.is_kev && { k: "kev", label: "CISA KEV", value: <span className="text-err">在列</span>, basis: item.kev_date_added ? `added ${String(item.kev_date_added).slice(0, 10)}` : "—" },
        ex.ssvc && { k: "ssvc", label: "SSVC", value: ex.ssvc.exploitation || "—", basis: "vulnrichment" },
        item.exploit_maturity && { k: "maturity", label: "利用成熟度", value: item.exploit_maturity, basis: "kev/ssvc/poc" },
        item.ai_relevance_score != null && { k: "airel", label: "AI 相关度", value: item.ai_relevance_score.toFixed(2), basis: "≥0.30 计入" },
        item.priority_score != null && { k: "prio", label: "优先级", value: item.priority_score.toFixed(2), basis: "ingest._priority" },
      ].filter(Boolean) as { k: string; label: string; value: React.ReactNode; basis: string }[]).slice(0, 3)
    : []) as { k: string; label: string; value: React.ReactNode; basis: string }[];

  return (
    <>
      {/* 遮罩：bg-ink/30 · fade 200ms · 点击关闭 */}
      <div className="fixed inset-0 z-40 bg-ink/30" onClick={onClose}
        style={{ transition: "opacity 200ms ease-out", opacity: shown ? 1 : 0 }} />

      {/* 抽屉：w-400 贴右边、四角直角，transform-only 350ms --ease-drawer */}
      <aside role="dialog" aria-modal="true" aria-label="条目速览"
        className="fixed inset-y-0 right-0 z-50 flex w-[400px] max-w-[94vw] flex-col rounded-none border-l border-line bg-panel shadow-lift"
        style={{ transition: "transform 350ms var(--ease-drawer)", transform: shown ? "translateX(0)" : "translateX(100%)" }}>

        {/* 头：item id mono + 标题截断 + ▲▼ 队列内翻页 + 关闭 */}
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-3">
          <span className="mono max-w-[120px] shrink-0 truncate text-[11px] uppercase tracking-[0.04em] text-faint" title={effId ?? undefined}>
            {effId}
          </span>
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-fg" title={headTitle}>
            {headTitle}
          </span>
          {index >= 0 && total > 0 && (
            <span className="tnum shrink-0 font-mono text-[11px] text-faint">{index + 1}/{total}</span>
          )}
          <div className="flex shrink-0 items-center gap-0.5">
            <button className="btn btn-sm btn-ghost !px-1" onClick={onPrev} disabled={!hasPrev}
              title="上一条 (K/↑)" aria-label="上一条">
              <ChevronUp size={12} strokeWidth={2} />
            </button>
            <button className="btn btn-sm btn-ghost !px-1" onClick={onNext} disabled={!hasNext}
              title="下一条 (J/↓)" aria-label="下一条">
              <ChevronDown size={12} strokeWidth={2} />
            </button>
            <button className="btn btn-sm btn-ghost !px-1" onClick={onClose}
              title="关闭 (Esc)" aria-label="关闭">
              <X size={12} strokeWidth={2} />
            </button>
          </div>
        </header>

        {/* 决策面：SevPill · 置信度 · 薄弱维度 · 摘要 · 评分构成前3 */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {err ? (
            <Empty text="条目加载失败" hint={err} />
          ) : !item ? (
            <div className="space-y-2.5">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-24" />
              <Skeleton className="h-16" />
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                <SevPill level={item.severity} />
                {item.item_type && <span className="badge">{item.item_type}</span>}
                {(item.cve_ids || []).slice(0, 3).map((c: string) => (
                  <span key={c} className="badge mono">{c}</span>
                ))}
                {item.is_kev && (
                  <span className="badge"><span className="dot" style={{ background: "var(--err)" }} />KEV</span>
                )}
                {item.has_poc && (
                  <span className="badge"><span className="dot" style={{ background: "var(--warn)" }} />PoC</span>
                )}
              </div>

              <Sect label="置信度">
                <div className="flex items-center gap-2">
                  <div className="h-[3px] flex-1 rounded-full bg-surface2">
                    <div className={`h-full rounded-full ${confTone(item.confidence)}`}
                      style={{ width: `${Math.round((item.confidence ?? 0) * 100)}%` }} />
                  </div>
                  <span className={`tnum font-mono text-[12px] ${confText(item.confidence)}`}>
                    {item.confidence != null ? `${Math.round(item.confidence * 100)}%` : "—"}
                  </span>
                </div>
              </Sect>

              <Sect label="薄弱维度">
                {weak.length ? (
                  <div className="flex flex-wrap gap-1">
                    {weak.map((d) => (
                      <span key={d} className="badge mono">
                        <span className="dot" style={{ background: "var(--err)" }} />{d}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-[12px] text-faint">—（各富化维度状态正常）</span>
                )}
              </Sect>

              <Sect label="摘要">
                <p className="text-[13px] leading-relaxed text-dim">
                  {item.summary_zh || item.summary || "—"}
                </p>
              </Sect>

              {scoreRows.length > 0 && (
                <Sect label="评分构成">
                  {scoreRows.map((r) => (
                    <div key={r.k}
                      className="flex items-baseline justify-between gap-3 border-b border-line py-[7px] last:border-0">
                      <span className="shrink-0 font-mono text-[11px] uppercase tracking-[0.08em] text-faint">{r.label}</span>
                      <span className="min-w-0 text-right">
                        <span className="tnum font-mono text-[12px] text-fg">{r.value}</span>
                        <span className="ml-2 font-mono text-[11px] text-faint">{r.basis}</span>
                      </span>
                    </div>
                  ))}
                </Sect>
              )}
            </>
          )}
        </div>

        {/* footer：确认 / 回炉 / 重富化 + 完整页外链 */}
        <footer className="shrink-0 border-t border-line px-3 py-2.5">
          <div className="flex items-center gap-1.5">
            {!readonly && onAct && (
              <button className="btn btn-sm !border-ok/40 !text-ok hover:!bg-ok/10" title="确认 (C)"
                disabled={busy} onClick={() => onAct(target, "confirm")}>
                <Check size={11} strokeWidth={2} />确认<kbd className="ml-1 rounded-[3px] border border-current/30 px-0.5 font-mono text-[9px] opacity-60">c</kbd>
              </button>
            )}
            {!readonly && onAct && (
              <button className="btn btn-sm !border-err/40 !text-err hover:!bg-err/10" title="回炉 (R)"
                disabled={busy} onClick={() => onAct(target, "reject")}>
                <Undo2 size={11} strokeWidth={2} />回炉<kbd className="ml-1 rounded-[3px] border border-current/30 px-0.5 font-mono text-[9px] opacity-60">r</kbd>
              </button>
            )}
            {!readonly && onReEnrich && (
              <button className="btn btn-sm btn-ghost" title="重新触发富化 worker (E)"
                disabled={busy} onClick={() => onReEnrich(target)}>
                <RefreshCw size={11} strokeWidth={2} />重富化<kbd className="ml-1 rounded-[3px] border border-line px-0.5 font-mono text-[9px] opacity-60">e</kbd>
              </button>
            )}
            <Link href={`/items/${effId}`} className="btn btn-sm btn-ghost ml-auto" title="整页详情">
              打开完整页<ArrowUpRight size={11} strokeWidth={2} />
            </Link>
          </div>
        </footer>
      </aside>
    </>
  );
}
