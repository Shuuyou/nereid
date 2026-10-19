"use client";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { api } from "@/lib/api";
import { C, echartsBase } from "@/lib/theme";
import { SpecRow, SpecDot, Sev, St } from "@/components/ui";
import { Search, Share2, ExternalLink, RotateCcw } from "lucide-react";

const Chart = dynamic(() => import("echarts-for-react"), { ssr: false });

/** 实体类型色板 — severity 色仅用于实体区分，不承担语义 */
const KIND_COLOR: Record<string, string> = {
  Item: C.accent, CVE: C.critical, CWE: C.high, CAPEC: C.medium,
  Technique: "#a78bfa", Product: C.low, Vendor: "#7fb3e8", GHSA: "#f472b6",
  Package: "#5eead4", ASI: "#f0abfc",
};
const kindColor = (k: string) => KIND_COLOR[k] || C.faint;

interface GNode { id: string; label: string; kind: string; severity?: string; score?: number }
interface GLink { source: string; target: string; type: string }
interface Sel { node: GNode; degree: number; neighbors: { id: string; label: string; kind: string; rel: string }[] }

export default function GraphPage() {
  const [entity, setEntity] = useState("CVE-2024-37032");
  const [query, setQuery] = useState("CVE-2024-37032");
  const [data, setData] = useState<{ nodes: GNode[]; links: GLink[] }>({ nodes: [], links: [] });
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [kinds, setKinds] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Sel | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => { api.kgStats().then(setStats).catch(() => {}); }, []);
  useEffect(() => {
    if (!query) return;
    setLoading(true);
    setSel(null);
    api.kgSubgraph(query, 2)
      .then((d) => { setData({ nodes: d.nodes || [], links: d.links || [] }); setKinds(new Set()); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [query]);

  const allKinds: string[] = useMemo(
    () => Array.from(new Set<string>(data.nodes.map((n) => String(n.kind)))).sort(),
    [data]);
  const activeKinds = kinds.size ? kinds : new Set(allKinds);
  const toggleKind = (k: string) => {
    const base = kinds.size ? new Set(kinds) : new Set(allKinds);
    if (base.has(k)) base.delete(k); else base.add(k);
    setKinds(base);
  };

  // 过滤后视图
  const nodes = useMemo(() => data.nodes.filter((n) => activeKinds.has(String(n.kind))), [data, kinds]);
  const nodeIds = useMemo(() => new Set(nodes.map((n) => n.id)), [nodes]);
  const links = useMemo(() => data.links.filter((l) => nodeIds.has(l.source) && nodeIds.has(l.target)), [data, nodeIds]);

  // 度（用于标签稀疏化 + 详情面板）
  const degree = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of data.links) {
      m.set(l.source, (m.get(l.source) || 0) + 1);
      m.set(l.target, (m.get(l.target) || 0) + 1);
    }
    return m;
  }, [data]);

  const opt = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      ...echartsBase.tooltip,
      formatter: (p: any) => p.dataType === "node"
        ? `<div style="font-family:JetBrains Mono;font-size:10.5px;color:#8a8694">${p.data.category}</div>` +
          `<div style="font-size:12px;color:#211f26;max-width:260px">${p.data.lbl || p.data.id}</div>`
        : `${p.data.rel || ""}`,
    },
    series: [{
      type: "graph", layout: "force", roam: true, draggable: true,
      force: { repulsion: 220, edgeLength: 110, gravity: 0.08 },
      // 标签稀疏化：仅 Item 与高度数节点默认出 label
      label: { show: false },
      categories: allKinds.map((c) => ({ name: c, itemStyle: { color: kindColor(c) } })),
      data: nodes.map((n) => {
        const deg = degree.get(n.id) || 0;
        const key = n.kind === "Item" || deg >= 3;
        return {
          id: n.id, name: n.id, category: n.kind, lbl: n.label,
          symbolSize: n.kind === "Item" ? 14 : Math.min(11, 6 + deg),
          itemStyle: { color: kindColor(String(n.kind)), borderColor: C.bg, borderWidth: 1 },
          label: key ? {
            show: true, position: "right" as const, color: C.dim, fontSize: 10,
            fontFamily: "JetBrains Mono, monospace",
            formatter: (p: any) => (p.data.lbl || "").slice(0, 26),
          } : undefined,
        };
      }),
      links: links.map((l) => ({
        source: l.source, target: l.target, rel: l.type,
        lineStyle: { color: "rgba(33,31,38,0.2)", width: 1 },
      })),
      emphasis: { focus: "adjacency", lineStyle: { color: C.accent, width: 1.5 } },
    }],
  }), [nodes, links, allKinds, degree]);

  function pick(p: any) {
    if (p.dataType !== "node" || !p.data?.id) return;
    const n = data.nodes.find((x) => x.id === p.data.id);
    if (!n) return;
    const neighbors = data.links
      .filter((l) => l.source === n.id || l.target === n.id)
      .map((l) => {
        const other = l.source === n.id ? l.target : l.source;
        const on = data.nodes.find((x) => x.id === other);
        return { id: other, label: on?.label || other, kind: on?.kind || "Node", rel: l.type };
      })
      .slice(0, 30);
    setSel({ node: n, degree: degree.get(n.id) || 0, neighbors });
  }

  function recenter(id: string) {
    setEntity(id);
    setQuery(id);
  }

  /** 空态示例：取优先级最高的 KEV 条目 → 以其 CVE/条目 id 居中展开 */
  async function recenterKev() {
    try {
      const d = await api.items({ kev: true, size: 1, sort: "priority" });
      const it = (d.items || [])[0];
      const t = it?.cve_ids?.[0] || it?.id;
      if (t) { setNote(""); recenter(t); }
      else setNote("未找到 KEV 条目（先在流水线页运行采集）");
    } catch { setNote("后端不可达，无法取 KEV 条目"); }
  }

  return (
    <div>
      <SpecRow>
        <span>FIG_07</span><SpecDot />
        <span>KNOWLEDGE GRAPH</span><SpecDot />
        <span>{stats ? `${(stats.nodes ?? 0).toLocaleString()} NODES / ${(stats.edges ?? 0).toLocaleString()} EDGES` : "NEO4J"}</span>
        <span className="ml-auto flex items-center gap-1.5 normal-case tracking-normal">
          <St tone={loading ? "live" : "dim"}>{loading ? "LOADING" : `${nodes.length}/${links.length} SHOWN`}</St>
        </span>
      </SpecRow>

      <div className="flex gap-4" style={{ height: "calc(100vh - 148px)" }}>
        {/* ── 左栏：检索 + 类型过滤 ── */}
        <div className="flex w-[212px] shrink-0 flex-col">
          <div className="relative">
            <Search size={12} strokeWidth={1.75} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
            <input className="input w-full !pl-7" value={entity}
              onChange={(e) => setEntity(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && entity.trim() && setQuery(entity.trim())}
              placeholder="CVE-xxxx / 产品 / 技术ID" />
          </div>
          <button className="btn mt-2 w-full" onClick={() => entity.trim() && setQuery(entity.trim())}>
            展开子图
          </button>
          <div className="mt-4 border-t border-line pt-3">
            <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.08em] text-faint">类型过滤</div>
            <div className="flex flex-wrap gap-1.5">
              {allKinds.length === 0 && <span className="text-[12px] text-faint">—</span>}
              {allKinds.map((k) => (
                <button key={k} onClick={() => toggleKind(k)}
                  className={`badge transition-colors ${activeKinds.has(k) ? "" : "opacity-40"}`}>
                  <span className="dot" style={{ background: kindColor(k) }} />{k}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-auto text-[12px] leading-relaxed text-faint">
            拖拽平移，滚轮缩放<br />点击节点查看属性<br />label 仅默认显示关键节点
          </div>
        </div>

        {/* ── 主画布 ── */}
        <div className="relative min-w-0 flex-1 overflow-hidden rounded-md border border-line bg-panel">
          {nodes.length > 0 ? (
            <Chart option={opt} style={{ height: "100%" }} notMerge
              onEvents={{ click: pick }} />
          ) : loading ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-[13px] text-faint">
              <Share2 size={18} strokeWidth={1.5} className="animate-pulse opacity-60" />
              加载子图…
            </div>
          ) : (
            /* 空态引导：说状态 + 示例直达动作 + 无输入时的推荐入口 */
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <Share2 size={18} strokeWidth={1.5} className="text-faint opacity-60" />
              <div className="text-[13px] text-dim">
                {query ? `「${query}」暂无邻边数据` : "输入实体名以展开子图"}
              </div>
              <div className="text-[12px] text-faint">等待 KG 同步，或换个实体试试：</div>
              <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
                <button className="btn btn-sm" onClick={recenterKev}>以 KEV 实体为中心</button>
                <button className="btn btn-sm" onClick={() => recenter("CVE-2024-37032")}>以 CVE-2024-37032 为中心</button>
              </div>
              {!entity.trim() && (
                <Link href="/items?kev=1"
                  className="mt-1 inline-flex items-center gap-1 font-mono text-[12px] text-accent transition-colors hover:underline">
                  推荐入口：KEV 条目<ExternalLink size={10} />
                </Link>
              )}
              {note && <div className="text-[12px] text-err">{note}</div>}
            </div>
          )}
          <div className="pointer-events-none absolute left-3 top-2.5 font-mono text-[11px] uppercase tracking-[0.08em] text-faint">
            SUBGRAPH {query} DEPTH 2
          </div>
        </div>

        {/* ── 右栏：选中实体属性 ── */}
        <div className="panel flex w-[264px] shrink-0 flex-col overflow-hidden">
          <div className="panel-h">
            <span className="t">ENTITY</span>
            {sel && <span className="mono text-[11px] text-faint">deg {sel.degree}</span>}
          </div>
          <div className="flex-1 overflow-y-auto">
            {!sel ? (
              <div className="panel-b text-[12px] leading-relaxed text-faint">
                点击画布中的节点<br />查看实体属性与一跳邻居
              </div>
            ) : (
              <div className="panel-b space-y-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: kindColor(String(sel.node.kind)) }} />
                    <span className="badge mono">{sel.node.kind}</span>
                    {sel.node.severity && <Sev level={sel.node.severity} />}
                  </div>
                  <div className="mt-2 break-words text-[13px] font-medium leading-snug text-fg">
                    {sel.node.label}
                  </div>
                  <div className="mono mt-1 break-all text-[11px] text-faint">{sel.node.id}</div>
                  {sel.node.score != null && (
                    <div className="num mt-1 text-[12px] text-dim">score {sel.node.score}</div>
                  )}
                  <div className="mt-2.5 flex flex-col items-start gap-0.5">
                    {sel.node.kind === "Item" && (
                      <Link href={`/items/${sel.node.id}`}
                        className="inline-flex items-center gap-1 font-mono text-[12px] text-accent transition-colors hover:underline">
                        查看情报详情<ExternalLink size={10} />
                      </Link>
                    )}
                    {sel.node.kind !== "Item" && (
                      <Link href={`/items?q=${encodeURIComponent(sel.node.label || sel.node.id)}&ai_only=0`}
                        className="inline-flex items-center gap-1 font-mono text-[12px] text-dim transition-colors hover:text-accent">
                        检索相关情报<Search size={10} />
                      </Link>
                    )}
                    <button className="mt-1 inline-flex items-center gap-1 font-mono text-[12px] text-dim transition-colors hover:text-accent"
                      onClick={() => recenter(sel.node.id)}>
                      <RotateCcw size={10} />以此实体为中心展开
                    </button>
                  </div>
                </div>
                <div className="border-t border-line pt-3">
                  <div className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.08em] text-faint">
                    一跳邻居 {sel.neighbors.length}
                  </div>
                  <div className="space-y-px">
                    {sel.neighbors.map((nb, i) => (
                      <button key={i} onClick={() => recenter(nb.id)}
                        className="group flex w-full items-center gap-2 rounded-[5px] px-1.5 py-1.5 text-left transition-colors hover:bg-surface">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: kindColor(String(nb.kind)) }} />
                        <span className="min-w-0 flex-1 truncate text-[12px] text-dim group-hover:text-fg">{nb.label}</span>
                        <span className="mono shrink-0 text-[11px] text-faint">{nb.rel}</span>
                      </button>
                    ))}
                    {sel.neighbors.length === 0 && <div className="px-1 text-[12px] text-faint">孤立节点</div>}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
