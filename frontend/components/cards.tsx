import Link from "next/link";

export function SevBadge({ s }: { s?: string }) {
  if (!s) return null;
  const v = s.toLowerCase();
  const cls = ["critical", "high", "medium", "low"].includes(v) ? `sev-${v}` : "tag";
  return <span className={`badge ${cls}`}>{s.toUpperCase()}</span>;
}

export function LayerTag({ l }: { l?: string }) {
  const names: Record<string, string> = {
    L1: "L1 基础设施", L2: "L2 模型数据", L3: "L3 应用智能体",
    L4: "L4 供应链", L5: "L5 政策治理", L6: "L6 滥用威胁",
  };
  return l ? <span className="tag-accent">{names[l] || l}</span> : null;
}

export function ItemCard({ item: it }: { item: any }) {
  return (
    <Link href={`/items/${it.id}`} className="card block hover:border-accent/50 transition-colors">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <SevBadge s={it.severity} />
        {it.is_kev && <span className="tag-kev">KEV</span>}
        {it.has_poc && <span className="tag-accent">PoC</span>}
        <LayerTag l={it.ai_layer} />
        <span className="tag">{it.item_type}</span>
        {(it.cve_ids || []).slice(0, 2).map((c: string) => <span key={c} className="tag mono">{c}</span>)}
      </div>
      <h3 className="line-clamp-2 text-sm font-medium leading-snug">{it.title_zh || it.title}</h3>
      <div className="mt-2 flex items-center justify-between text-xs text-dim">
        <span className="truncate">{(it.source_names || []).slice(0, 2).join(" · ")}</span>
        <span className="flex gap-3 shrink-0">
          {it.cvss_v31_score != null && <span className="text-high">CVSS {it.cvss_v31_score}</span>}
          {it.epss_score != null && <span>EPSS {(it.epss_score * 100).toFixed(1)}%</span>}
          {it.published_at && <span>{it.published_at.slice(0, 10)}</span>}
        </span>
      </div>
    </Link>
  );
}
