import { Inbox } from "lucide-react";

export function PageHeader({ title, desc, right }: { title: string; desc?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-[17px] font-semibold tracking-[-0.01em] text-fg">{title}</h1>
        {desc && <p className="mt-0.5 text-[12px] text-faint">{desc}</p>}
      </div>
      {right}
    </div>
  );
}

export function Empty({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-2 py-10 text-center">
      <Inbox size={20} strokeWidth={1.5} className="text-faint" />
      <div className="text-[13px] text-dim">{text}</div>
      {hint && <div className="text-[11px] text-faint">{hint}</div>}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function StatCard({ label, value, sub, tone }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "accent" | "critical" | "high" | "low" | "fg";
}) {
  const c = { accent: "text-accent", critical: "text-critical", high: "text-high", low: "text-low", fg: "text-fg" }[tone || "fg"];
  return (
    <div className="card card-hover">
      <div className="h3">{label}</div>
      <div className={`kpi mt-1.5 text-[24px] leading-none ${c}`}>{value}</div>
      {sub && <div className="mt-1.5 text-[11px] text-faint">{sub}</div>}
    </div>
  );
}

export function Dot({ tone = "low", glow = true }: { tone?: "low" | "critical" | "accent" | "dim"; glow?: boolean }) {
  const bg = { low: "bg-low", critical: "bg-critical", accent: "bg-accent", dim: "bg-faint" }[tone];
  const gl = { low: "dot-glow", critical: "shadow-[0_0_8px_rgba(240,85,79,0.6)]", accent: "dot-glow-accent", dim: "" }[tone];
  return <span className={`dot ${bg} ${glow ? gl : ""}`} />;
}
