"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ExternalLink, RefreshCw, FileDown, ChevronDown } from "lucide-react";
import { API, api } from "@/lib/api";
import { LayerTag, cvssToSev } from "@/components/cards";
import { Skeleton, SpecRow, SpecDot, Sev, SevPill, St } from "@/components/ui";
import { SEV_COLOR } from "@/lib/theme";

/* ── 左栏属性行：label 小灰 + 值右对齐，hairline 分隔 ── */
function Attr({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  if (children == null || children === "") return null;
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-[7px] last:border-0">
      <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.08em] text-faint">{label}</span>
      <span className={`min-w-0 break-words text-right text-[12px] text-dim ${mono ? "tnum font-mono text-[11.5px]" : ""}`}>
        {children}
      </span>
    </div>
  );
}

/* ── 左栏分组 ── */
function Rail({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-6 first:mt-0">
      <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-faint">{title}</div>
      {children}
    </div>
  );
}

function IdChips({ ids }: { ids: string[] }) {
  if (!ids?.length) return null;
  return (
    <span className="flex flex-wrap justify-end gap-1">
      {ids.map((c) => <span key={c} className="badge mono">{c}</span>)}
    </span>
  );
}

const CRED_DOT: Record<string, string> = {
  trusted: "#2e7d5b", community: "#71717a", suspicious: "#b07c00", malicious: "#d92638",
};

export default function ItemDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [it, setIt] = useState<any>(null);
  const [related, setRelated] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [why, setWhy] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setIt(null); setErr(""); setWhy({});
    api.item(id).then(setIt).catch((e) => setErr(String(e)));
    api.related(id).then((r) => setRelated(r.items || [])).catch(() => {});
  }, [id]);

  /** 智能返回：站内来源走 router.back() 保留上下文（筛选/滚动），站外/直开落到 /items */
  const goBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1 && document.referrer.startsWith(window.location.origin)) {
      router.back();
    } else {
      router.push("/items");
    }
  };

  if (err) return <div className="panel panel-b text-err">{err}</div>;
  if (!it) return (
    <div className="space-y-4">
      <Skeleton className="h-[120px]" />
      <div className="grid gap-8 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Skeleton className="h-[340px]" /><Skeleton className="h-[340px]" />
      </div>
    </div>
  );

  const ex = it.extra || {};
  const chain = it.attack_chain?.steps || [];
  const ssvc = ex.ssvc;
  const enrichDims = Object.entries(it.enrichment || {})
    .filter(([, v]) => v && typeof v === "object");
  const pct = (v?: number) => (v == null ? null : `${(v * 100).toFixed(0)}%`);

  /* 评分构成行：指标 / 值 / 依据 / 可展开“为什么” */
  const scoreRows: { k: string; label: string; value: React.ReactNode; basis: string; whyText?: string }[] = [
    it.cvss_v31_score != null && {
      k: "cvss31", label: "CVSS v3.1",
      value: <span style={{ color: SEV_COLOR[cvssToSev(it.cvss_v31_score)] }}>{it.cvss_v31_score.toFixed(1)}</span>,
      basis: ex.cvss_source ? `src ${ex.cvss_source}` : "采集器内联",
      whyText: `向量 ${it.cvss_v31_vector || "—"} · 分值来源 ${ex.cvss_source || "collector"}（CNA/ADP 优先于 NVD Secondary）`,
    },
    it.cvss_v40_score != null && {
      k: "cvss40", label: "CVSS v4.0",
      value: <span style={{ color: SEV_COLOR[cvssToSev(it.cvss_v40_score)] }}>{it.cvss_v40_score.toFixed(1)}</span>,
      basis: "v4.0 metric",
      whyText: `向量 ${it.cvss_v40_vector || "—"}`,
    },
    it.epss_score != null && {
      k: "epss", label: "EPSS",
      value: `${(it.epss_score * 100).toFixed(2)}%`,
      basis: it.epss_percentile != null ? `pctl ${(it.epss_percentile * 100).toFixed(0)}%` : "—",
      whyText: `FIRST 官方 30 天利用概率 · 快照 ${ex.epss_as_of || (ex.epss_fetched_at || "").slice(0, 10) || "—"} · 模型 ${ex.epss_model_version || "—"}`,
    },
    it.is_kev && {
      k: "kev", label: "CISA KEV",
      value: <span className="text-err">在列</span>,
      basis: it.kev_date_added ? `added ${it.kev_date_added.slice(0, 10)}` : "—",
      whyText: `要求措施：${ex.kev_required_action || "—"}`,
    },
    ssvc && {
      k: "ssvc", label: "SSVC",
      value: ssvc.exploitation || "—",
      basis: `auto:${ssvc.automatable || "?"} impact:${ssvc.technical_impact || "?"}`,
      whyText: `CISA Vulnrichment 决策点 · ${ssvc.ts_parsed ? ssvc.ts_parsed.slice(0, 10) : "无时间戳"}`,
    },
    it.exploit_maturity && {
      k: "maturity", label: "利用成熟度",
      value: it.exploit_maturity,
      basis: "kev/ssvc/poc 综合",
      whyText: { weaponized: "KEV 在列或 SSVC exploitation=active → 武器化", poc: "存在公开 PoC 代码", none: "未见公开利用证据" }[it.exploit_maturity as string] || "综合 KEV/SSVC/PoC 信号判定",
    },
    it.ai_relevance_score != null && {
      k: "airel", label: "AI 相关度",
      value: it.ai_relevance_score.toFixed(2),
      basis: "≥0.30 计入",
      whyText: "实体/向量规则综合打分，≥0.30 进入 AI 相关情报集合",
    },
    it.priority_score != null && {
      k: "prio", label: "优先级",
      value: it.priority_score.toFixed(2),
      basis: "ingest._priority",
      whyText: "两段式：KEV/weaponized/SSVC-active 直置顶桶 [6,8]；其余 65%·CVSS + 35%·(EPSS+利用成熟度+AI 相关)",
    },
  ].filter(Boolean) as any[];

  /* ── 分诊动线锚点目录：簇内第一个有数据的块承担锚点落点（无数据分区条件渲染，锚点同步缺席） ── */
  const hasSummary = !!(it.summary_zh || it.summary);
  const hasImpact = !!(ex.impact_zh || ex.exploitability_zh || ex.mitigation_zh || ex.kev_required_action || it.affected_versions);
  const mapAnchor = it.mappings?.length > 0 ? "sec-mappings"
    : chain.length > 0 ? "sec-chain"
    : it.d3fend?.length > 0 ? "sec-d3fend" : "";
  const evAnchor = it.pocs?.length > 0 ? "sec-pocs"
    : it.assets?.length > 0 ? "sec-assets"
    : it.papers?.length > 0 ? "sec-papers"
    : ex.references?.length > 0 ? "sec-refs" : "";
  const toc: [string, string][] = [];
  if (hasSummary) toc.push(["#sec-summary", "摘要"]);
  if (scoreRows.length) toc.push(["#sec-score", "评分"]);
  if (hasImpact) toc.push(["#sec-impact", "影响"]);
  if (mapAnchor) toc.push([`#${mapAnchor}`, "映射"]);
  if (evAnchor) toc.push([`#${evAnchor}`, "证据"]);
  if (related.length) toc.push(["#sec-related", "相关"]);

  return (
    <div>
      <SpecRow>
        <span>FIG_03</span><SpecDot />
        <span><Link href="/items" className="hover:text-accent">情报检索</Link> / <span className="text-dim">详情</span></span><SpecDot />
        <span className="truncate">{it.id}</span>
        <button onClick={goBack}
          className="ml-auto inline-flex items-center gap-1 transition-colors hover:text-accent"
          title="返回来源页">
          <ArrowLeft size={11} />返回
        </button>
      </SpecRow>

      {/* ── 头区：标题 + 标记 chips + 时间戳 + 操作 ── */}
      <div className="mt-4">
        <div className="flex items-start justify-between gap-4">
          <h1 className="min-w-0 text-[15px] font-semibold leading-snug tracking-[-0.005em] text-fg">
            {it.title_zh || it.title}
          </h1>
          <div className="flex shrink-0 gap-1.5">
            <a className="btn btn-sm" href={`${API}/api/items/${id}/stix`}
              download={`nereid-${id.slice(0, 8)}.stix.json`} title="导出 STIX 2.1 Bundle">
              <FileDown size={12} />STIX
            </a>
            <button className="btn btn-sm" onClick={() => api.enrich(id).then(() => location.reload())}>
              <RefreshCw size={12} />重新富化
            </button>
            {it.url && (
              <a className="btn btn-ghost btn-sm" href={it.url} target="_blank">
                原文<ExternalLink size={11} />
              </a>
            )}
          </div>
        </div>
        {it.title_zh && <p className="mt-1 text-[12px] text-faint">{it.title}</p>}

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <SevPill level={it.severity} />
          <span className="badge">{it.item_type || "—"}</span>
          <LayerTag l={it.ai_layer} />
          {(it.cve_ids || []).map((c: string) => <span key={c} className="badge mono">{c}</span>)}
          {it.is_kev && (
            <span className="badge"><span className="dot" style={{ background: "#d92638" }} />
              KEV{it.kev_date_added ? ` ${it.kev_date_added.slice(0, 10)}` : ""}
            </span>
          )}
          {it.has_poc && <span className="badge"><span className="dot" style={{ background: "#b07c00" }} />PoC</span>}
          {(it.owasp_llm || []).map((o: string) => <span key={o} className="badge mono">{o}</span>)}
          {ex.is_demo && <span className="badge mono">DEMO</span>}
          {it.review_status === "needs_review" && <St tone="warn">待复核</St>}
        </div>

        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-faint">
          <span>发布 <span className="tnum text-dim">{it.published_at?.slice(0, 10) || "—"}</span></span>
          <span>收录 <span className="tnum text-dim">{it.first_seen_at?.slice(0, 16).replace("T", " ") || "—"}</span></span>
          <span>来源 <span className="text-dim">{(it.source_names || []).join(" / ") || "—"}</span></span>
          {it.source_count > 1 && <span className="text-dim">×{it.source_count} 源确认</span>}
        </div>
      </div>

      {/* ── DualPane：280px 属性栏 │ 主区 ── */}
      <div className="mt-6 grid gap-x-10 gap-y-8 lg:grid-cols-[280px_minmax(0,1fr)]">

        {/* 左栏：固定属性表 */}
        <aside className="min-w-0">
          <Rail title="属性">
            <Attr label="Item ID" mono><span title={it.id}>{it.id.length > 22 ? `${it.id.slice(0, 22)}…` : it.id}</span></Attr>
            <Attr label="置信度" mono>{pct(it.confidence)}</Attr>
            <Attr label="可靠性" mono>{pct(it.reliability_score)}</Attr>
            <Attr label="技术成熟度">{it.technique_maturity}</Attr>
            <Attr label="复核状态">{it.review_status}</Attr>
          </Rail>

          {(it.cve_ids?.length || it.ghsa_ids?.length || it.cnvd_ids?.length || it.cnnvd_ids?.length ||
            it.edb_ids?.length || it.cwe_ids?.length) ? (
            <Rail title="标识符">
              {it.cve_ids?.length > 0 && <Attr label="CVE"><IdChips ids={it.cve_ids} /></Attr>}
              {it.ghsa_ids?.length > 0 && <Attr label="GHSA"><IdChips ids={it.ghsa_ids} /></Attr>}
              {it.cnvd_ids?.length > 0 && <Attr label="CNVD"><IdChips ids={it.cnvd_ids} /></Attr>}
              {it.cnnvd_ids?.length > 0 && <Attr label="CNNVD"><IdChips ids={it.cnnvd_ids} /></Attr>}
              {it.edb_ids?.length > 0 && <Attr label="EDB"><IdChips ids={it.edb_ids} /></Attr>}
              {it.cwe_ids?.length > 0 && <Attr label="CWE"><IdChips ids={it.cwe_ids} /></Attr>}
            </Rail>
          ) : null}

          {(it.owasp_asi?.length || it.atlas_techniques?.length || it.attack_techniques?.length) ? (
            <Rail title="AI 分类 / 技术">
              {it.owasp_asi?.length > 0 && <Attr label="OWASP ASI"><IdChips ids={it.owasp_asi} /></Attr>}
              {it.attack_techniques?.length > 0 && <Attr label="ATT&CK"><IdChips ids={it.attack_techniques.slice(0, 8)} /></Attr>}
              {it.atlas_techniques?.length > 0 && <Attr label="ATLAS"><IdChips ids={it.atlas_techniques.slice(0, 8)} /></Attr>}
            </Rail>
          ) : null}

          {(it.vendors?.length || it.products?.length || it.packages?.length) ? (
            <Rail title="影响面">
              <Attr label="厂商">{(it.vendors || []).join("、") || null}</Attr>
              <Attr label="产品">{(it.products || []).join("、") || null}</Attr>
              {it.packages?.length > 0 && <Attr label="包" mono>{it.packages.length} purl</Attr>}
            </Rail>
          ) : null}

          {(it.sources?.length ? it.sources : (it.source_names || []).map((n: string) => ({ source_name: n }))).length > 0 && (
            <Rail title="来源溯源">
              {(it.sources?.length ? it.sources : (it.source_names || []).map((n: string) => ({ source_name: n })))
                .map((s: any, i: number) => (
                  <Attr key={i} label={s.is_primary ? "主源" : `源 ${i + 1}`}>
                    {s.url
                      ? <a className="inline-flex items-center gap-1 text-dim transition-colors hover:text-accent"
                          href={s.url} target="_blank">{s.source_name}<ExternalLink size={9} /></a>
                      : s.source_name}
                  </Attr>
                ))}
            </Rail>
          )}

          {enrichDims.length > 0 && (
            <Rail title="富化维度">
              {enrichDims.map(([k, v]: [string, any]) => (
                <Attr key={k} label={k}>
                  <St tone={v.status === "ok" ? "ok" : v.status === "error" ? "err" : v.status === "partial" ? "warn" : "dim"}>
                    {v.status}{v.confidence != null ? ` ${(v.confidence * 100).toFixed(0)}%` : ""}
                  </St>
                </Attr>
              ))}
            </Rail>
          )}
        </aside>

        {/* 右主区：.sect 分区（分诊动线：摘要→评分→影响→映射/攻击链→证据附件） */}
        <div className="min-w-0">
          {toc.length > 1 && (
            <nav className="mb-4 font-mono text-[10px] uppercase tracking-[0.08em] text-faint">
              <span className="mr-2">§</span>
              {toc.map(([href, label], i) => (
                <span key={href}>
                  {i > 0 && " · "}
                  <a href={href} className="transition-colors hover:text-accent">{label}</a>
                </span>
              ))}
            </nav>
          )}

          {(it.summary_zh || it.summary) && (
            <div id="sec-summary" className="scroll-mt-[60px]">
              <h2 className="sect-title">摘要</h2>
              <p className="mt-2.5 text-[13px] leading-relaxed text-dim">{it.summary_zh || it.summary}</p>
              {it.summary_zh && it.summary && it.summary !== it.summary_zh && (
                <details className="mt-2">
                  <summary className="cursor-pointer font-mono text-[10.5px] uppercase tracking-[0.06em] text-faint transition-colors hover:text-dim">
                    原文摘要
                  </summary>
                  <p className="mt-2 text-[12.5px] leading-relaxed text-faint">{it.summary}</p>
                </details>
              )}
              {it.content_text && (
                <details className="mt-2">
                  <summary className="cursor-pointer font-mono text-[10.5px] uppercase tracking-[0.06em] text-faint transition-colors hover:text-dim">
                    原始正文摘录
                  </summary>
                  <pre className="mono mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-panel p-3 text-[11px] leading-relaxed text-dim">
                    {it.content_text.slice(0, 4000)}
                  </pre>
                </details>
              )}
            </div>
          )}

          {scoreRows.length > 0 && (
            <div id="sec-score" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">评分构成</h2>
              <div className="sect-sub">CVSS / EPSS / KEV / SSVC，行内展开评分依据</div>
              <table className="dt mt-3">
                <thead>
                  <tr><th className="w-[110px]">指标</th><th className="r w-[110px]">值</th><th>依据</th><th className="r w-[64px]"></th></tr>
                </thead>
                <tbody>
                  {scoreRows.map((r) => (
                    <ScoreRow key={r.k} r={r}
                      open={!!why[r.k]}
                      onToggle={() => setWhy((w) => ({ ...w, [r.k]: !w[r.k] }))} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(ex.impact_zh || ex.exploitability_zh || ex.mitigation_zh || ex.kev_required_action || it.affected_versions) && (
            <div id="sec-impact" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">影响与修复</h2>
              <div className="mt-3 space-y-3">
                {ex.impact_zh && (
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint">影响</div>
                    <p className="mt-1 text-[12.5px] leading-relaxed text-dim">{ex.impact_zh}</p>
                  </div>
                )}
                {ex.exploitability_zh && (
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint">可利用性</div>
                    <p className="mt-1 text-[12.5px] leading-relaxed text-dim">{ex.exploitability_zh}</p>
                  </div>
                )}
                {ex.kev_required_action && (
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint">KEV 要求措施</div>
                    <p className="mt-1 text-[12.5px] leading-relaxed text-warn">{ex.kev_required_action}</p>
                  </div>
                )}
                {ex.mitigation_zh && (
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint">缓解建议</div>
                    <p className="mt-1 text-[12.5px] leading-relaxed text-dim">{ex.mitigation_zh}</p>
                  </div>
                )}
                {it.affected_versions && (
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-faint">受影响版本</div>
                    <pre className="mono mt-1 whitespace-pre-wrap text-[11.5px] leading-relaxed text-dim">{it.affected_versions}</pre>
                  </div>
                )}
              </div>
            </div>
          )}

          {it.mappings?.length > 0 && (
            <div id="sec-mappings" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">技术映射 <span className="ml-1 font-normal text-faint">{it.mappings.length}</span></h2>
              <table className="dt mt-3">
                <thead>
                  <tr><th>CVE</th><th>CWE</th><th>CAPEC</th><th>ATT&CK</th><th>ATLAS</th><th className="r">置信</th></tr>
                </thead>
                <tbody>
                  {it.mappings.map((m: any, i: number) => (
                    <tr key={i}>
                      <td className="num text-dim">{m.cve_id || "—"}</td>
                      <td className="num text-dim">{m.cwe_id || "—"}</td>
                      <td className="num text-dim">{m.capec_id || "—"}</td>
                      <td className="num text-dim">{m.attack_technique || "—"}</td>
                      <td className="num text-dim">{m.atlas_technique || "—"}</td>
                      <td className="r num text-faint">{m.confidence != null ? m.confidence.toFixed(2) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {chain.length > 0 && (
            <div id="sec-chain" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">攻击链推演</h2>
              <div className="sect-sub">ATT&CK 步序，{chain.length} 阶段</div>
              <ol className="mt-3">
                {chain.map((s: any, i: number) => (
                  <li key={i} className="flex gap-3 border-b border-line py-2 last:border-0">
                    <span className="num w-6 shrink-0 pt-px text-faint">{String(i + 1).padStart(2, "0")}</span>
                    <div className="min-w-0">
                      <span className="text-[12px] font-medium text-fg">{s.stage}</span>
                      <div className="mt-0.5 text-[12.5px] leading-relaxed text-dim">{s.desc}</div>
                    </div>
                  </li>
                ))}
              </ol>
              {ex.attack_chain_desc && (
                <p className="mt-3 text-[12.5px] leading-relaxed text-dim">{ex.attack_chain_desc}</p>
              )}
            </div>
          )}

          {it.d3fend?.length > 0 && (
            <div id="sec-d3fend" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">D3FEND 防御对策 <span className="ml-1 font-normal text-faint">{it.d3fend.length}</span></h2>
              <div className="mt-2">
                {it.d3fend.map((d: any) => (
                  <div key={d.id} className="flex items-baseline gap-3 border-b border-line py-2 last:border-0">
                    <span className="badge mono shrink-0">{d.id}</span>
                    <div className="min-w-0">
                      <span className="text-[12.5px] font-medium text-fg">{d.name}</span>
                      <span className="ml-2 text-[11.5px] text-faint">{d.desc} → {d.for_technique}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {it.pocs?.length > 0 && (
            <div id="sec-pocs" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">PoC / EXP <span className="ml-1 font-normal text-faint">{it.pocs.length}</span></h2>
              <table className="dt mt-3">
                <thead>
                  <tr>
                    <th className="w-[104px]">可信度</th><th>链接</th>
                    <th className="w-[96px]">平台</th><th className="r w-[64px]">Stars</th><th className="w-[96px]">获取</th>
                  </tr>
                </thead>
                <tbody>
                  {it.pocs.map((p: any) => (
                    <tr key={p.url}>
                      <td>
                        <span className="badge">
                          <span className="dot" style={{ background: CRED_DOT[p.credibility] || "#71717a" }} />
                          {p.credibility}
                        </span>
                      </td>
                      <td>
                        <a className="block truncate text-dim transition-colors hover:text-accent"
                          href={p.url} target="_blank" title={p.url}>
                          {p.title || p.url}
                        </a>
                      </td>
                      <td className="num text-faint">{p.platform}</td>
                      <td className="r num text-dim">{p.stars ?? "—"}</td>
                      <td className="num text-faint">{p.fetched_at?.slice(0, 10)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {it.assets?.length > 0 && (
            <div id="sec-assets" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">资产暴露</h2>
              <div className="sect-sub">
                互联网测绘聚合{it.assets.some((a: any) => a.is_simulated) ? "（含模拟数据）" : ""}
              </div>
              <div className="mt-2">
                {it.assets.map((a: any, i: number) => (
                  <div key={i} className="border-b border-line py-2.5 last:border-0">
                    <div className="flex items-baseline gap-3">
                      <span className="badge mono shrink-0">{a.platform}</span>
                      <span className="min-w-0 truncate text-[12px] text-dim" title={a.query}>{a.query}</span>
                      <span className="ml-auto shrink-0">
                        <span className="tnum font-mono text-[13px] text-high">≈{(a.total_count || 0).toLocaleString()}</span>
                        <span className="ml-1 text-[11px] text-faint">暴露</span>
                      </span>
                    </div>
                    <div className="mono mt-1.5 break-all text-[10.5px] leading-relaxed text-faint">
                      {(a.sample || []).slice(0, 6).map((s: any) => `${s.ip}:${s.port}(${s.country || "?"})`).join("  ")}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {it.papers?.length > 0 && (
            <div id="sec-papers" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">关联论文 / 分析 <span className="ml-1 font-normal text-faint">{it.papers.length}</span></h2>
              <div className="mt-2">
                {it.papers.map((p: any, i: number) => (
                  <div key={i} className="flex items-baseline gap-3 border-b border-line py-2 last:border-0">
                    {p.url
                      ? <a className="min-w-0 truncate text-[12.5px] text-dim transition-colors hover:text-accent" href={p.url} target="_blank">{p.title}</a>
                      : <span className="min-w-0 truncate text-[12.5px] text-dim">{p.title}</span>}
                    <span className="ml-auto shrink-0 font-mono text-[10.5px] text-faint">
                      {[p.source, p.venue, p.year].filter(Boolean).join(" · ")}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ex.references?.length > 0 && (
            <div id="sec-refs" className="sect scroll-mt-[60px]">
              <h2 className="sect-title">参考链接 <span className="ml-1 font-normal text-faint">{ex.references.length}</span></h2>
              <div className="mt-2">
                {ex.references.slice(0, 10).map((u: string, i: number) => (
                  <a key={i} href={u} target="_blank"
                    className="flex items-center gap-2 border-b border-line py-1.5 font-mono text-[11px] text-faint transition-colors last:border-0 hover:text-accent">
                    <ExternalLink size={10} className="shrink-0" />
                    <span className="truncate">{u}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 相关情报：hairline 行列表 */}
      {related.length > 0 && (
        <div id="sec-related" className="sect scroll-mt-[60px]">
          <h2 className="sect-title">相关情报</h2>
          <div className="mt-2 divide-y divide-[rgba(33,31,38,0.06)]">
            {related.map((r: any) => (
              <Link key={r.id} href={`/items/${r.id}`}
                className="group flex items-center gap-3 py-2 transition-colors hover:bg-surface">
                <Sev level={r.severity} />
                <span className="min-w-0 flex-1 truncate text-[12.5px] text-dim transition-colors group-hover:text-fg">
                  {r.title_zh || r.title}
                </span>
                <span className="num shrink-0 text-[11px] text-faint">
                  {r.published_at ? r.published_at.slice(0, 10) : ""}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* 评分行 + 可展开“为什么”子行 */
function ScoreRow({ r, open, onToggle }: { r: any; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr>
        <td className="text-dim">{r.label}</td>
        <td className="r num text-[13px] text-fg">{r.value}</td>
        <td className="num text-faint">{r.basis}</td>
        <td className="r">
          {r.whyText && (
            <button onClick={onToggle}
              className="inline-flex items-center gap-0.5 font-mono text-[10px] uppercase tracking-[0.06em] text-faint transition-colors hover:text-accent">
              为什么<ChevronDown size={10} className={`transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
          )}
        </td>
      </tr>
      {open && r.whyText && (
        <tr>
          <td colSpan={4} className="!pt-0">
            <div className="mono -mt-1 border-l-2 border-line2 py-1 pl-3 text-[11px] leading-relaxed text-faint">
              {r.whyText}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
