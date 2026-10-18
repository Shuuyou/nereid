"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { C, echartsBase } from "@/lib/theme";

const Chart = dynamic(() => import("echarts-for-react"), { ssr: false });

const KIND_COLOR: Record<string, string> = {
  Item: C.accent, CVE: C.critical, CWE: C.high, CAPEC: C.medium,
  Technique: "#a78bfa", Product: C.low, Vendor: C.ai, GHSA: "#f472b6",
};

export default function GraphPage() {
  const [entity, setEntity] = useState("CVE-2024-37032");
  const [data, setData] = useState<any>({ nodes: [], links: [] });
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.kgStats().then(setStats).catch(() => {}); }, []);
  useEffect(() => {
    if (!entity) return;
    setLoading(true);
    api.kgSubgraph(entity, 2).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [entity]);

  const cats: string[] = Array.from(new Set<string>(data.nodes.map((n: any) => String(n.kind))));
  const opt = {
    backgroundColor: "transparent",
    legend: { data: cats, textStyle: { color: C.dim, fontSize: 11 }, itemWidth: 12, itemHeight: 8, bottom: 0, icon: "circle" },
    tooltip: { ...echartsBase.tooltip },
    series: [{
      type: "graph", layout: "force", roam: true, draggable: true,
      force: { repulsion: 220, edgeLength: 110, gravity: 0.08 },
      label: { show: true, color: C.fg, fontSize: 10, formatter: (p: any) => (p.data.label || "").slice(0, 26) },
      categories: cats.map((c) => ({ name: c, itemStyle: { color: KIND_COLOR[c] || C.dim } })),
      data: data.nodes.map((n: any) => ({
        id: n.id, name: n.id, label: n.label, category: n.kind,
        symbolSize: n.kind === "Item" ? 16 : 10,
        itemStyle: n.kind === "Item"
          ? { shadowBlur: 14, shadowColor: "rgba(62,200,232,0.5)" }
          : undefined,
      })),
      links: data.links.map((l: any) => ({
        source: l.source, target: l.target,
        label: { show: false },
        lineStyle: { color: "rgba(198,215,235,0.14)" },
      })),
      emphasis: { focus: "adjacency", lineStyle: { color: C.accent, width: 2 } },
    }],
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h2">知识图谱</h1>
          <p className="mt-0.5 text-[12px] text-faint">Neo4j 实体关系探索 · 双击节点可交互</p>
        </div>
        <div className="flex items-center gap-3">
          <input className="input w-72" value={entity} onChange={(e) => setEntity(e.target.value)}
            placeholder="实体：CVE-xxxx / 产品名 / 技术ID" />
          {stats && <span className="text-[12px] tabular-nums text-faint">{stats.nodes.toLocaleString()} 节点 · {stats.edges.toLocaleString()} 边</span>}
          {loading && <span className="dot bg-accent dot-glow-accent breathe" />}
        </div>
      </div>
      <div className="card h-[calc(100vh-240px)] !p-0 overflow-hidden">
        {data.nodes.length > 0
          ? <Chart option={opt} style={{ height: "100%" }} notMerge />
          : <div className="flex h-full items-center justify-center text-[13px] text-faint">无图谱数据（等待 KG 同步）</div>}
      </div>
    </div>
  );
}
