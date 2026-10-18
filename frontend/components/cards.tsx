import Link from "next/link";
import { Flame, Zap, Sparkles, FileText } from "lucide-react";
import { SEV_COLOR } from "@/lib/theme";

export function SevBadge({ s }: { s?: string }) {
  if (!s) return null;
  const v = s.toLowerCase();
  const cls = ["critical", "high", "medium", "low"].includes(v) ? `sev-${v}` : "tag";
  return <span className={cls}>{s.toUpperCase()}</span>;
}

export function LayerTag({ l }: { l?: string }) {
  const names: Record<string, string> = {
    L1: "L1 基础设施", L2: "L2 模型数据", L3: "L3 应用智能体",
    L4: "L4 供应链", L5: "L5 政策治理", L6: "L6 滥用威胁",
  };
  return l ? <span className="tag-ai">{names[l] || l}</span> : null;
}

export function ItemCard({ item: it }: { item: any }) {
  return (
    <Link href={`/items/${it.id}`} className="card card-hover group block">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <SevBadge s={it.severity} />
        {it.is_kev && (
          <span className="tag-kev"><Flame size={10} strokeWidth={2.5} />KEV</span>
        )}
        {it.has_poc && (
          <span className="tag-accent"><Zap size={10} strokeWidth={2.5} />PoC</span>
        )}
        {it.ai_layer && <span className="tag-ai"><Sparkles size={10} strokeWidth={2.5} />{it.ai_layer}</span>}
        <span className="tag">{it.item_type}</span>
        {(it.cve_ids || []).slice(0, 2).map((c: string) => (
          <span key={c} className="tag mono">{c}</span>
        ))}
      </div>
      <h3 className="line-clamp-2 text-[13px] font-medium leading-snug text-fg/95 group-hover:text-fg">
        {it.title_zh || it.title}
      </h3>
      <div className="mt-2.5 flex items-center justify-between text-[11px] text-faint">
        <span className="flex items-center gap-1 truncate">
          <FileText size={11} strokeWidth={1.5} className="shrink-0" />
          {(it.source_names || []).slice(0, 2).join(" · ")}
        </span>
        <span className="flex shrink-0 gap-3 tabular-nums">
          {it.cvss_v31_score != null && (
            <span style={{ color: SEV_COLOR[cvssToSev(it.cvss_v31_score)] }}>
              CVSS {it.cvss_v31_score}
            </span>
          )}
          {it.epss_score != null && <span>EPSS {(it.epss_score * 100).toFixed(1)}%</span>}
          {it.published_at && <span>{it.published_at.slice(0, 10)}</span>}
        </span>
      </div>
    </Link>
  );
}

export function cvssToSev(score: number): string {
  if (score >= 9) return "critical";
  if (score >= 7) return "high";
  if (score >= 4) return "medium";
  if (score > 0) return "low";
  return "none";
}
