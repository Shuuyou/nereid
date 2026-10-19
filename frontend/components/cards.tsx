import Link from "next/link";
import { Sev } from "@/components/ui";

/** severity 显示统一走 <Sev>（6px 色点 + 文字，不吃品牌色/不满底色块）。
 *  保留原签名供 review / for-you 等页复用。 */
export function SevBadge({ s }: { s?: string }) {
  return <Sev level={s} />;
}

/** AI 层标签：pastel 分类色（color-as-taxonomy，L1-L6 一一映射） */
export function LayerTag({ l }: { l?: string }) {
  const tones: Record<string, [string, string]> = {
    L1: ["L1 基础设施", "bg-mint text-mint-ink"],
    L2: ["L2 模型数据", "bg-lav text-lav-ink"],
    L3: ["L3 应用智能体", "bg-sky text-sky-ink"],
    L4: ["L4 供应链", "bg-peach text-peach-ink"],
    L5: ["L5 政策治理", "bg-butter text-butter-ink"],
    L6: ["L6 滥用威胁", "bg-rose text-rose-ink"],
  };
  const t = l ? tones[l] : null;
  return t ? (
    <span className={`inline-flex items-center rounded-badge px-2 py-0.5 font-mono text-[10.5px] font-medium ${t[1]}`}>
      {t[0]}
    </span>
  ) : null;
}

/** 紧凑行情报条目：Sev 点 + 标题(truncate) + mono CVE/EPSS/时间。
 *  无卡片包裹、零阴影、hover 仅背景移。 */
export function ItemCard({ item: it }: { item: any }) {
  return (
    <Link
      href={`/items/${it.id}`}
      className="group flex items-center gap-3 border-b border-line px-1 py-2 transition-colors last:border-0 hover:bg-surface"
    >
      <Sev level={it.severity} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] text-fg transition-colors group-hover:text-accent">
          {it.title_zh || it.title}
        </div>
        <div className="mt-0.5 flex items-center gap-2 font-mono text-[10.5px] text-faint">
          {(it.cve_ids || []).slice(0, 2).map((c: string) => <span key={c}>{c}</span>)}
          {it.is_kev && <span className="text-err">KEV</span>}
          {it.has_poc && <span className="text-warn">PoC</span>}
          <span className="truncate">{(it.source_names || []).slice(0, 2).join(" · ")}</span>
        </div>
      </div>
      {it.epss_score != null && (
        <span className="tnum shrink-0 font-mono text-[11px] text-dim">
          {(it.epss_score * 100).toFixed(1)}%
        </span>
      )}
      <span className="tnum shrink-0 font-mono text-[11px] text-faint">
        {it.published_at ? it.published_at.slice(0, 10) : ""}
      </span>
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
