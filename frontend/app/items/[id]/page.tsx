"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { SevBadge, LayerTag } from "@/components/cards";

const CRED_COLOR: Record<string, string> = {
  trusted: "text-low", community: "text-medium", suspicious: "text-high", malicious: "text-critical",
};

export default function ItemDetail() {
  const { id } = useParams<{ id: string }>();
  const [it, setIt] = useState<any>(null);
  const [related, setRelated] = useState<any[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.item(id).then(setIt).catch((e) => setErr(String(e)));
    api.related(id).then((r) => setRelated(r.items || [])).catch(() => {});
  }, [id]);

  if (err) return <div className="card text-critical">{err}</div>;
  if (!it) return <div className="text-dim">加载中…</div>;

  const chain = it.attack_chain?.steps || [];

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <SevBadge s={it.severity} />
          {it.is_kev && <span className="tag-kev">CISA KEV · {it.kev_date_added?.slice(0, 10)}</span>}
          {it.has_poc && <span className="tag-accent">PoC 可用</span>}
          <LayerTag l={it.ai_layer} />
          <span className="tag">{it.item_type}</span>
          {(it.owasp_llm || []).map((o: string) => <span key={o} className="tag-accent">{o}</span>)}
          <button className="btn-ghost ml-auto !py-1 !px-2 text-xs" onClick={() => api.enrich(id).then(() => location.reload())}>重新富化</button>
        </div>
        <h1 className="text-xl font-semibold leading-snug">{it.title_zh || it.title}</h1>
        {it.title_zh && <p className="text-sm text-dim">{it.title}</p>}
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-dim">
          {it.url && <a className="text-accent hover:underline" href={it.url} target="_blank">原文链接 ↗</a>}
          <span>发布: {it.published_at?.slice(0, 10) || "未知"}</span>
          <span>来源: {(it.source_names || []).join(" / ")}</span>
          <span>可靠性: {(it.reliability_score * 100).toFixed(0)}%</span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card grid grid-cols-2 gap-3 lg:col-span-1 content-start">
          {[["CVSS v3.1", it.cvss_v31_score], ["CVSS v4.0", it.cvss_v40_score],
            ["EPSS", it.epss_score != null ? `${(it.epss_score * 100).toFixed(2)}%` : null],
            ["EPSS 百分位", it.epss_percentile != null ? `${(it.epss_percentile * 100).toFixed(0)}%` : null],
            ["利用成熟度", it.exploit_maturity], ["AI 相关度", it.ai_relevance_score?.toFixed(2)],
            ["优先级", it.priority_score?.toFixed(2)], ["技术成熟度", it.technique_maturity],
          ].map(([k, v]: any) => v != null && (
            <div key={k}><div className="text-xs text-dim">{k}</div><div className="text-lg font-semibold">{String(v)}</div></div>
          ))}
          {(it.cve_ids?.length > 0) && <div className="col-span-2"><div className="text-xs text-dim">CVE</div><div className="mono text-sm">{it.cve_ids.join("  ")}</div></div>}
          {(it.cwe_ids?.length > 0) && <div className="col-span-2"><div className="text-xs text-dim">CWE</div><div className="mono text-sm">{it.cwe_ids.join("  ")}</div></div>}
          {(it.atlas_techniques?.length > 0) && <div className="col-span-2"><div className="text-xs text-dim">MITRE ATLAS</div><div className="mono text-sm">{it.atlas_techniques.join("  ")}</div></div>}
          {(it.products?.length > 0) && <div className="col-span-2"><div className="text-xs text-dim">影响产品</div><div className="text-sm">{it.products.join("、")}</div></div>}
          {it.affected_versions && <div className="col-span-2"><div className="text-xs text-dim">受影响版本</div><pre className="mono text-xs whitespace-pre-wrap">{it.affected_versions}</pre></div>}
        </div>

        <div className="space-y-4 lg:col-span-2">
          {(it.summary_zh || it.summary) && (
            <div className="card">
              <h3 className="mb-2 text-sm font-medium text-dim">摘要</h3>
              <p className="text-sm leading-relaxed">{it.summary_zh || it.summary}</p>
            </div>
          )}
          {chain.length > 0 && (
            <div className="card">
              <h3 className="mb-3 text-sm font-medium text-dim">攻击链推演</h3>
              <div className="flex flex-wrap items-center gap-2">
                {chain.map((s: any, i: number) => (
                  <div key={i} className="flex items-center gap-2">
                    <div className="rounded-lg border border-accent/30 bg-accent/10 px-3 py-2">
                      <div className="text-xs text-accent">{s.stage}</div>
                      <div className="text-sm">{s.desc}</div>
                    </div>
                    {i < chain.length - 1 && <span className="text-dim">→</span>}
                  </div>
                ))}
              </div>
              {it.extra?.attack_chain_desc && <p className="mt-3 text-sm text-dim">{it.extra.attack_chain_desc}</p>}
            </div>
          )}
          {it.extra?.mitigation_zh && (
            <div className="card border-low/30">
              <h3 className="mb-2 text-sm font-medium text-low">缓解建议</h3>
              <p className="text-sm leading-relaxed">{it.extra.mitigation_zh}</p>
            </div>
          )}

          {it.pocs?.length > 0 && (
            <div className="card">
              <h3 className="mb-2 text-sm font-medium text-dim">PoC / EXP（{it.pocs.length}）</h3>
              <div className="space-y-1.5">
                {it.pocs.map((p: any) => (
                  <a key={p.url} href={p.url} target="_blank" className="flex items-center gap-2 text-sm hover:text-accent">
                    <span className={`badge bg-border ${CRED_COLOR[p.credibility] || "text-dim"}`}>{p.credibility}</span>
                    <span className="truncate">{p.title || p.url}</span>
                    <span className="ml-auto shrink-0 text-xs text-dim">{p.platform}{p.stars ? ` · ★${p.stars}` : ""}</span>
                  </a>
                ))}
              </div>
            </div>
          )}

          {it.assets?.length > 0 && (
            <div className="card">
              <h3 className="mb-2 text-sm font-medium text-dim">
                受影响互联网资产{it.assets.some((a: any) => a.is_simulated) && <span className="tag ml-2">模拟数据</span>}
              </h3>
              {it.assets.map((a: any, i: number) => (
                <div key={i} className="mb-2 text-sm">
                  <span className="text-dim">{a.platform} · {a.query}: </span>
                  <span className="text-high">≈{a.total_count}</span> 暴露
                  <div className="mono mt-1 text-xs text-dim">
                    {(a.sample || []).slice(0, 6).map((s: any) => `${s.ip}:${s.port}(${s.country || "?"})`).join("  ")}
                  </div>
                </div>
              ))}
            </div>
          )}

          {it.papers?.length > 0 && (
            <div className="card">
              <h3 className="mb-2 text-sm font-medium text-dim">关联论文/分析（{it.papers.length}）</h3>
              {it.papers.map((p: any, i: number) => (
                <div key={i} className="mb-1.5 text-sm">
                  {p.url ? <a className="text-accent hover:underline" href={p.url} target="_blank">{p.title}</a> : p.title}
                  <span className="ml-2 text-xs text-dim">{p.source}{p.year ? ` · ${p.year}` : ""}{p.venue ? ` · ${p.venue}` : ""}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {related.length > 0 && (
        <div className="card">
          <h3 className="mb-3 text-sm font-medium text-dim">相关情报</h3>
          <div className="grid gap-2 md:grid-cols-2">
            {related.map((r: any) => (
              <Link key={r.id} href={`/items/${r.id}`} className="rounded-lg border border-border p-2 text-sm hover:border-accent/50">
                {r.title_zh || r.title}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
