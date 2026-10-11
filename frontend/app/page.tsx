"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { api, subscribeFeed } from "@/lib/api";
import { SevBadge, LayerTag, ItemCard } from "@/components/cards";

const Chart = dynamic(() => import("echarts-for-react"), { ssr: false });

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [fresh, setFresh] = useState<any>(null);
  const [live, setLive] = useState<any[]>([]);
  const [liveOn, setLiveOn] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api.stats(), api.items({ size: 8, sort: "priority", ai_only: true }), api.freshness()])
      .then(([s, it, f]) => { setStats(s); setItems(it.items || []); setFresh(f); })
      .catch((e) => setErr(String(e)));
    // SSE 实时情报流：新条目实时进 ticker，并刷新 24h 计数
    const off = subscribeFeed((item) => {
      setLiveOn(true);
      setLive((l) => [item, ...l].slice(0, 6));
    });
    return off;
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
          <h3 className="mb-2 text-sm font-medium text-dim">情报时效（披露→入库滞后）</h3>
          {fresh ? (
            <div className="grid grid-cols-4 gap-3 pt-2">
              {[["P50", fresh.p50_min], ["P90", fresh.p90_min], ["P95", fresh.p95_min]].map(([k, v]: any) => (
                <div key={k as string} className="text-center">
                  <div className="text-xs text-dim">{k}</div>
                  <div className="text-xl font-bold text-accent">{v != null ? `${(v / 60).toFixed(1)}h` : "—"}</div>
                </div>
              ))}
              <div className="text-center">
                <div className="text-xs text-dim">&lt;1h 入库</div>
                <div className="text-xl font-bold text-low">{fresh.buckets?.["<1h"] ?? "—"}</div>
              </div>
            </div>
          ) : <div className="text-dim text-sm">—</div>}
        </div>
        <div className="card">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-medium text-dim">
            <span className={`inline-block h-2 w-2 rounded-full ${liveOn ? "bg-low animate-pulse" : "bg-dim"}`} />
            实时监测流 {liveOn && <span className="text-low text-xs">LIVE</span>}
          </h3>
          <div className="space-y-2 text-xs">
            {live.length === 0 && <div className="text-dim">等待新情报推送…（采集器运行中自动出现）</div>}
            {live.map((it) => (
              <a key={it.id + it.first_seen_at} href={`/items/${it.id}`} className="block truncate text-fg hover:text-accent">
                <span className="text-dim">{new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</span>{" "}
                {it.title_zh || it.title}
              </a>
            ))}
          </div>
        </div>
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
