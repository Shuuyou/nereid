import { Inbox } from "lucide-react";

/** 页头：标题 + 右侧操作；配 spec-row 图纸元数据行使用 */
export function PageHeader({ title, desc, right }: { title: string; desc?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-[16px] font-semibold tracking-[-0.01em] text-fg">{title}</h1>
        {desc && <p className="mt-0.5 text-[12px] text-faint">{desc}</p>}
      </div>
      {right}
    </div>
  );
}

/** 图纸元数据行：FIG_02 · REVIEW QUEUE · 2026-10-19 · 47 ITEMS */
export function SpecRow({ children }: { children: React.ReactNode }) {
  return <div className="spec-row mb-3">{children}</div>;
}
export function SpecDot() {
  return <span className="dot" />;
}

export function Empty({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 rounded-md border border-dashed border-line2 py-12 text-center">
      <Inbox size={18} strokeWidth={1.5} className="text-faint" />
      <div className="text-[12.5px] text-dim">{text}</div>
      {hint && <div className="text-[11px] text-faint">{hint}</div>}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skel ${className}`} />;
}

/** hairline stat strip — KPI 不包卡片，1px 衬底分隔 */
export function StatStrip({ stats }: {
  stats: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "fg" | "accent" | "critical" | "high" | "ok" }[];
}) {
  const c = { fg: "text-fg", accent: "text-accent", critical: "text-crit", high: "text-high", ok: "text-ok" } as const;
  return (
    <div
      className="grid overflow-hidden rounded-md border border-line"
      style={{ gridTemplateColumns: `repeat(${stats.length},1fr)`, gap: 1, background: "rgba(33,31,38,0.07)" }}
    >
      {stats.map((s, i) => (
        <div key={i} className="bg-bg px-4 py-3.5">
          <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint">{s.label}</div>
          <div className={`mt-1.5 tnum font-mono text-[26px] font-medium leading-none tracking-[-0.02em] ${c[s.tone || "fg"]}`}>
            {s.value}
          </div>
          {s.sub && <div className="mt-1.5 text-[11px] leading-snug text-faint">{s.sub}</div>}
        </div>
      ))}
    </div>
  );
}

/** 状态点：纯色 5px + 文字 */
export function St({ tone = "dim", children }: { tone?: "ok" | "err" | "warn" | "live" | "dim"; children?: React.ReactNode }) {
  return (
    <span className={`st st-${tone === "dim" ? "" : tone}`}>
      <span className="dot" style={tone === "dim" ? { background: "#a49f8f" } : undefined} />
      {children}
    </span>
  );
}

/** severity 点+文字 */
export function Sev({ level }: { level?: string }) {
  const l = (level || "").toLowerCase();
  const cls = l.includes("crit") ? "sev-crit" : l.includes("high") ? "sev-high"
    : l.includes("med") ? "sev-med" : l.includes("low") ? "sev-low" : "";
  const label = l.includes("crit") ? "严重" : l.includes("high") ? "高危" : l.includes("med") ? "中危" : l.includes("low") ? "低危" : (level || "—");
  return <span className={`sev ${cls}`}><span className="dot" style={cls ? undefined : { background: "#71717a" }} />{label}</span>;
}
