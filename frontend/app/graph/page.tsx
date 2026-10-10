"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";

const Chart = dynamic(() => import("echarts-for-react"), { ssr: false });

const KIND_COLOR: Record<string, string> = {
  Item: "#4cc2ff", CVE: "#ff5c5c", CWE: "#ff9a3d", CAPEC: "#ffd23d",
  Technique: "#c678dd", Product: "#4dffa6", Vendor: "#56b6c2", GHSA: "#e06c75",
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
    legend: { data: cats, textStyle: { color: "#8b98a9" }, bottom: 0 },
    tooltip: {},
    series: [{
      type: "graph", layout: "force", roam: true, draggable: true,
      force: { repulsion: 220, edgeLength: 110, gravity: 0.08 },
      label: { show: true, color: "#e6edf3", fontSize: 10, formatter: (p: any) => (p.data.label || "").slice(0, 26) },
      categories: cats.map((c) => ({ name: c, itemStyle: { color: KIND_COLOR[c] || "#8b98a9" } })),
      data: data.nodes.map((n: any) => ({ id: n.id, name: n.id, label: n.label, category: n.kind, symbolSize: n.kind === "Item" ? 14 : 10 })),
      links: data.links.map((l: any) => ({ source: l.source, target: l.target, label: { show: false }, lineStyle: { color: "#3d4757" } })),
    }],
  };

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">知识图谱</h1>
        <input className="input max-w-sm" value={entity} onChange={(e) => setEntity(e.target.value)}
          placeholder="输入实体：CVE-xxxx / 产品名 / 技术ID" />
        {stats && <span className="text-sm text-dim">节点 {stats.nodes} · 边 {stats.edges}</span>}
        {loading && <span className="text-sm text-accent">查询中…</span>}
      </div>
      <div className="card h-[calc(100vh-240px)]">
        {data.nodes.length > 0
          ? <Chart option={opt} style={{ height: "100%" }} notMerge />
          : <div className="flex h-full items-center justify-center text-dim">无图谱数据（等待 KG 同步）</div>}
      </div>
    </div>
  );
}
