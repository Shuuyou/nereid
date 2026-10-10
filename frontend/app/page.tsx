"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { SevBadge, LayerTag, ItemCard } from "@/components/cards";

const Chart = dynamic(() => import("echarts-for-react"), { ssr: false });

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api.stats(), api.items({ size: 8, sort: "priority", ai_only: true })])
      .then(([s, it]) => { setStats(s); setItems(it.items || []); })
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="card text-critical">后端连接失败: {err}</div>;
  if (!stats) return <div className="text-dim">加载中…</div>;

  const layerOpt = {
    backgroundColor: "transparent",
    tooltip: {},
    series: [{
      type: "pie", radius: ["45%", "70%"],
      label: { color: "#8b98a9", fontSize: 11 },
      data: Object.entries(stats.by_layer || {}).filter(([k]) => k && k !== "null")
        .map(([k, v]) => ({ name: k, value: v })),
      itemStyle: { borderColor: "#0b0f14", borderWidth: 2 },
    }],
  };
  const trendOpt = {
    backgroundColor: "transparent",
    grid: { left: 40, right: 10, top: 20, bottom: 30 },
    xAxis: { type: "category", data: (stats.trend_14d || []).map((t: any) => t.date.slice(5)), axisLabel: { color: "#8b98a9", fontSize: 10 } },
    yAxis: { type: "value", axisLabel: { color: "#8b98a9" }, splitLine: { lineStyle: { color: "#1e2836" } } },
    series: [{ type: "line", smooth: true, areaStyle: { opacity: 0.15 }, data: (stats.trend_14d || []).map((t: any) => t.count), lineStyle: { color: "#4cc2ff" }, itemStyle: { color: "#4cc2ff" } }],
    tooltip: {},
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-6">
        {[
          ["情报总量", stats.total_items, "text-fg"],
          ["24h 新增", stats.new_24h, "text-accent"],
          ["AI 相关", stats.ai_items, "text-accent"],
          ["KEV 在野", stats.kev_count, "text-critical"],
          ["PoC 可用", stats.poc_count, "text-high"],
          ["数据源", `${stats.sources?.healthy || 0}/${stats.sources?.total || 0}`, "text-low"],
        ].map(([k, v, c]: any) => (
          <div key={k} className="card">
            <div className="text-xs text-dim">{k}</div>
            <div className={`mt-1 text-2xl font-bold ${c}`}>{v}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h3 className="mb-2 text-sm font-medium text-dim">14 天情报趋势</h3>
          <Chart option={trendOpt} style={{ height: 220 }} notMerge />
        </div>
        <div className="card">
          <h3 className="mb-2 text-sm font-medium text-dim">AI 安全层分布</h3>
          <Chart option={layerOpt} style={{ height: 220 }} notMerge />
        </div>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">高优先级 AI 情报</h2>
          <Link href="/items" className="text-sm text-accent hover:underline">全部 →</Link>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((it) => <ItemCard key={it.id} item={it} />)}
        </div>
      </div>
    </div>
  );
}
