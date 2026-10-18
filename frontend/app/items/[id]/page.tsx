"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Flame, Zap, ExternalLink, ShieldCheck, RefreshCw, FileDown, Skull } from "lucide-react";
import { API, api } from "@/lib/api";
import { SevBadge, LayerTag, cvssToSev } from "@/components/cards";
import { Skeleton } from "@/components/ui";
import { SEV_COLOR } from "@/lib/theme";

const CRED_COLOR: Record<string, string> = {
  trusted: "text-low border-low/30 bg-low/[0.12]",
  community: "text-medium border-medium/30 bg-medium/[0.12]",
  suspicious: "text-high border-high/30 bg-high/[0.12]",
  malicious: "text-critical border-critical/30 bg-critical/[0.12]",
};

function Score({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  if (value == null) return null;
  return (
    <div className="rounded-lg border border-line bg-edge/50 px-3 py-2">
      <div className="h3">{label}</div>
      <div className={`kpi mt-1 text-[17px] ${tone || "text-fg"}`}>{value}</div>
    </div>
  );
}

function Sec({ title, children, tone }: { title: string; children: React.ReactNode; tone?: "low" | "critical" }) {
  const c = tone === "low" ? "text-low" : tone === "critical" ? "text-critical" : "text-dim";
  return (
    <section className="card">
      <h3 className={`h3 mb-2.5 ${c}`}>{title}</h3>
      {children}
    </section>
  );
}

export default function ItemDetail() {
  const { id } = useParams<{ id: string }>();
  const [it, setIt] = useState<any>(null);
  const [related, setRelated] = useState<any[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    setIt(null); setErr("");
    api.item(id).then(setIt).catch((e) => setErr(String(e)));
    api.related(id).then((r) => setRelated(r.items || [])).catch(() => {});
  }, [id]);

  if (err) return <div className="card text-critical">{err}</div>;
  if (!it) return (
    <div className="space-y-4">
      <Skeleton className="h-[130px]" />
      <div className="grid gap-3 lg:grid-cols-3"><Skeleton className="h-[300px]" /><Skeleton className="h-[300px] lg:col-span-2" /></div>
    </div>
  );

  const chain = it.attack_chain?.steps || [];

  return (
    <div className="space-y-4">
      <Link href="/items" className="inline-flex items-center gap-1 text-[12px] text-faint transition-colors hover:text-fg">
        <ArrowLeft size={12} />返回情报库
      </Link>

      {/* 头卡 */}
      <div className="card space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <SevBadge s={it.severity} />
          {it.is_kev && <span className="tag-kev"><Flame size={10} strokeWidth={2.5} />CISA KEV · {it.kev_date_added?.slice(0, 10)}</span>}
          {it.has_poc && <span className="tag-accent"><Zap size={10} strokeWidth={2.5} />PoC 可用</span>}
          <LayerTag l={it.ai_layer} />
          <span className="tag">{it.item_type}</span>
          {(it.owasp_llm || []).map((o: string) => <span key={o} className="tag-ai">{o}</span>)}
          <span className="ml-auto flex gap-1.5">
            <a className="btn-ghost !px-2.5 !py-1 !text-[11px]" href={`${API}/api/items/${id}/stix`}
              download={`nereid-${id.slice(0, 8)}.stix.json`} title="导出 STIX 2.1 Bundle">
              <FileDown size={11} />STIX
            </a>
            <button className="btn-ghost !px-2.5 !py-1 !text-[11px]" onClick={() => api.enrich(id).then(() => location.reload())}>
              <RefreshCw size={11} />重新富化
            </button>
          </span>
        </div>
        <h1 className="text-[18px] font-semibold leading-snug tracking-[-0.005em]">{it.title_zh || it.title}</h1>
        {it.title_zh && <p className="text-[12.5px] text-dim">{it.title}</p>}
        <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-line/60 pt-2.5 text-[12px] text-faint">
          {it.url && (
            <a className="inline-flex items-center gap-1 text-accent hover:opacity-70" href={it.url} target="_blank">
              原文链接<ExternalLink size={10} />
            </a>
          )}
          <span>发布 <span className="tabular-nums text-dim">{it.published_at?.slice(0, 10) || "未知"}</span></span>
          <span>来源 <span className="text-dim">{(it.source_names || []).join(" / ")}</span></span>
          {it.reliability_score != null && (
            <span>可靠性 <span className="tabular-nums text-dim">{(it.reliability_score * 100).toFixed(0)}%</span></span>
          )}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        {/* 左栏评分 */}
        <div className="grid content-start grid-cols-2 gap-2 lg:col-span-1">
          {it.cvss_v31_score != null && (
            <div className="rounded-lg border border-line bg-edge/50 px-3 py-2">
              <div className="h3">CVSS v3.1</div>
              <div className="kpi mt-1 text-[17px]" style={{ color: SEV_COLOR[cvssToSev(it.cvss_v31_score)] }}>
                {it.cvss_v31_score}
              </div>
            </div>
          )}
          {it.cvss_v40_score != null && (
            <div className="rounded-lg border border-line bg-edge/50 px-3 py-2">
              <div className="h3">CVSS v4.0</div>
              <div className="kpi mt-1 text-[17px]" style={{ color: SEV_COLOR[cvssToSev(it.cvss_v40_score)] }}>
                {it.cvss_v40_score}
              </div>
            </div>
          )}
          <Score label="EPSS" value={it.epss_score != null ? `${(it.epss_score * 100).toFixed(2)}%` : null} />
          <Score label="EPSS 百分位" value={it.epss_percentile != null ? `${(it.epss_percentile * 100).toFixed(0)}%` : null} />
          <Score label="利用成熟度" value={it.exploit_maturity} />
          <Score label="AI 相关度" value={it.ai_relevance_score?.toFixed(2)} />
          <Score label="优先级" value={it.priority_score?.toFixed(2)} />
          <Score label="技术成熟度" value={it.technique_maturity} />
          {it.cve_ids?.length > 0 && (
            <div className="col-span-2 rounded-lg border border-line bg-edge/50 px-3 py-2">
              <div className="h3">CVE</div>
              <div className="mono mt-1 text-[12px] text-accent">{it.cve_ids.join("  ")}</div>
            </div>
          )}
          {it.cwe_ids?.length > 0 && (
            <div className="col-span-2 rounded-lg border border-line bg-edge/50 px-3 py-2">
              <div className="h3">CWE</div>
              <div className="mono mt-1 text-[12px]">{it.cwe_ids.join("  ")}</div>
            </div>
          )}
          {it.atlas_techniques?.length > 0 && (
            <div className="col-span-2 rounded-lg border border-line bg-edge/50 px-3 py-2">
              <div className="h3">MITRE ATLAS</div>
              <div className="mono mt-1 text-[12px] text-ai">{it.atlas_techniques.join("  ")}</div>
            </div>
          )}
          {it.products?.length > 0 && (
            <div className="col-span-2 rounded-lg border border-line bg-edge/50 px-3 py-2">
              <div className="h3">影响产品</div>
              <div className="mt-1 text-[12px] text-fg/90">{it.products.join("、")}</div>
            </div>
          )}
          {it.affected_versions && (
            <div className="col-span-2 rounded-lg border border-line bg-edge/50 px-3 py-2">
              <div className="h3">受影响版本</div>
              <pre className="mono mt-1 whitespace-pre-wrap text-[11px] text-fg/80">{it.affected_versions}</pre>
            </div>
          )}
        </div>

        {/* 右栏主体 */}
        <div className="space-y-3 lg:col-span-2">
          {(it.summary_zh || it.summary) && (
            <Sec title="摘要">
              <p className="text-[13px] leading-relaxed text-fg/90">{it.summary_zh || it.summary}</p>
            </Sec>
          )}

          {chain.length > 0 && (
            <Sec title="攻击链推演">
              <div className="flex flex-wrap items-center gap-1.5">
                {chain.map((s: any, i: number) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <div className="rounded-lg border border-accent/25 bg-accent/[0.08] px-3 py-2">
                      <div className="text-[10px] font-medium uppercase tracking-wide text-accent">{s.stage}</div>
                      <div className="mt-0.5 text-[12px] text-fg/90">{s.desc}</div>
                    </div>
                    {i < chain.length - 1 && <span className="px-0.5 text-faint">→</span>}
                  </div>
                ))}
              </div>
              {it.extra?.attack_chain_desc && <p className="mt-3 text-[12px] leading-relaxed text-dim">{it.extra.attack_chain_desc}</p>}
            </Sec>
          )}

          {it.d3fend?.length > 0 && (
            <section className="card border-low/20">
              <h3 className="h3 mb-2.5 flex items-center gap-1.5 text-low"><ShieldCheck size={12} />D3FEND 防御对策</h3>
              <div className="space-y-2">
                {it.d3fend.map((d: any) => (
                  <div key={d.id} className="flex items-start gap-2 text-[12.5px]">
                    <span className="mono mt-0.5 shrink-0 rounded border border-low/25 bg-low/[0.08] px-1.5 py-0.5 text-[10px] text-low">{d.id}</span>
                    <div><span className="font-medium text-fg/90">{d.name}</span>
                      <span className="ml-2 text-[11px] text-faint">{d.desc} · 对应 {d.for_technique}</span></div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {it.extra?.mitigation_zh && (
            <section className="card border-low/20">
              <h3 className="h3 mb-2 text-low">缓解建议</h3>
              <p className="text-[13px] leading-relaxed text-fg/90">{it.extra.mitigation_zh}</p>
            </section>
          )}

          {it.pocs?.length > 0 && (
            <Sec title={`PoC / EXP（${it.pocs.length}）`}>
              <div className="space-y-1">
                {it.pocs.map((p: any) => (
                  <a key={p.url} href={p.url} target="_blank"
                    className="group flex items-center gap-2 rounded-md px-2 py-1.5 text-[12.5px] transition-colors hover:bg-white/[0.04]">
                    <span className={`badge shrink-0 ${CRED_COLOR[p.credibility] || "tag"}`}>
                      {p.credibility === "malicious" && <Skull size={9} />}{p.credibility}
                    </span>
                    <span className="truncate text-fg/85 group-hover:text-fg">{p.title || p.url}</span>
                    <span className="ml-auto flex shrink-0 items-center gap-1 text-[11px] text-faint">
                      {p.platform}{p.stars ? ` · ★${p.stars}` : ""}<ExternalLink size={9} className="opacity-0 group-hover:opacity-60" />
                    </span>
                  </a>
                ))}
              </div>
            </Sec>
          )}

          {it.assets?.length > 0 && (
            <Sec title="受影响互联网资产">
              {it.assets.some((a: any) => a.is_simulated) && <span className="tag mb-2">模拟数据</span>}
              {it.assets.map((a: any, i: number) => (
                <div key={i} className="mb-2.5 text-[12.5px]">
                  <span className="text-dim">{a.platform} · {a.query}: </span>
                  <span className="kpi text-high">≈{a.total_count}</span><span className="text-faint"> 暴露</span>
                  <div className="mono mt-1 break-all text-[10.5px] leading-relaxed text-faint">
                    {(a.sample || []).slice(0, 6).map((s: any) => `${s.ip}:${s.port}(${s.country || "?"})`).join("  ")}
                  </div>
                </div>
              ))}
            </Sec>
          )}

          {it.papers?.length > 0 && (
            <Sec title={`关联论文/分析（${it.papers.length}）`}>
              <div className="space-y-1.5">
                {it.papers.map((p: any, i: number) => (
                  <div key={i} className="text-[12.5px]">
                    {p.url
                      ? <a className="text-accent hover:opacity-70" href={p.url} target="_blank">{p.title}</a>
                      : <span className="text-fg/85">{p.title}</span>}
                    <span className="ml-2 text-[11px] text-faint">{p.source}{p.year ? ` · ${p.year}` : ""}{p.venue ? ` · ${p.venue}` : ""}</span>
                  </div>
                ))}
              </div>
            </Sec>
          )}
        </div>
      </div>

      {related.length > 0 && (
        <Sec title="相关情报">
          <div className="grid gap-2 md:grid-cols-2">
            {related.map((r: any) => (
              <Link key={r.id} href={`/items/${r.id}`}
                className="rounded-lg border border-line bg-edge/40 p-2.5 text-[12.5px] text-fg/85 transition-colors hover:border-linestrong hover:bg-raised">
                {r.title_zh || r.title}
              </Link>
            ))}
          </div>
        </Sec>
      )}
    </div>
  );
}
