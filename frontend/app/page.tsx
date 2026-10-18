"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { api, subscribeFeed } from "@/lib/api";
import { ItemCard } from "@/components/cards";
import { StatCard, Dot, Skeleton, PageHeader } from "@/components/ui";
import { C, SERIES, SEV_COLOR, echartsBase } from "@/lib/theme";

const Chart = dynamic(() => import("echarts-for-react"), { ssr: false });

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [fresh, setFresh] = useState<any>(null);
  const [expo, setExpo] = useState<any>(null);
  const [live, setLive] = useState<any[]>([]);
  const [liveOn, setLiveOn] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api.stats(), api.items({ size: 8, sort: "priority", ai_only: true }), api.freshness(), api.assetExposure()])
      .then(([s, it, f, e]) => { setStats(s); setItems(it.items || []); setFresh(f); setExpo(e); })
      .catch((e) => setErr(String(e)));
    const off = subscribeFeed((item) => {
      setLiveOn(true);
      setLive((l) => [item, ...l].slice(0, 6));
    });
    return off;
  }, []);

  if (err) return <div className="card text-critical">后端连接失败：{err}</div>;
  if (!stats) return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[86px]" />)}
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <Skeleton className="h-[280px] lg:col-span-2" /><Skeleton className="h-[280px]" />
      </div>
    </div>
  );

  const layerOpt = {
    backgroundColor: "transparent",
    color: SERIES,
    tooltip: echartsBase.tooltip,
    series: [{
      type: "pie", radius: ["58%", "76%"],
      label: { color: C.faint, fontSize: 10 },
      labelLine: { lineStyle: { color: C.line } },
      itemStyle: { borderColor: C.panel, borderWidth: 2, borderRadius: 4 },
      data: Object.entries(stats.by_layer || {}).filter(([k]) => k && k !== "null")
        .map(([k, v]) => ({ name: k, value: v })),
    }],
    graphic: [{
      type: "text", left: "center", top: "46%", style: {
        text: (stats.ai_items || 0).toLocaleString(), fill: C.fg, fontSize: 22,
        fontWeight: 600, fontVariantNumeric: "tabular-nums", textAlign: "center",
      },
    }, {
      type: "text", left: "center", top: "56%", style: {
        text: "AI 相关", fill: C.faint, fontSize: 10, textAlign: "center",
      },
    }],
  };
  const trendOpt = {
    backgroundColor: "transparent",
    grid: { left: 34, right: 12, top: 18, bottom: 26 },
    tooltip: { ...echartsBase.tooltip, trigger: "axis" },
    xAxis: { type: "category", ...echartsBase.categoryAxis, boundaryGap: false, data: (stats.trend_14d || []).map((t: any) => t.date.slice(5)) },
    yAxis: { type: "value", ...echartsBase.valueAxis },
    series: [{
      type: "line", smooth: true, showSymbol: false,
      data: (stats.trend_14d || []).map((t: any) => t.count),
      lineStyle: { color: C.accent, width: 2 },
      itemStyle: { color: C.accent },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: "rgba(62,200,232,0.22)" }, { offset: 1, color: "rgba(62,200,232,0)" }],
        },
      },
    }],
  };

  return (
    <div className="space-y-5">
      {/* 顶部 KPI 带深渊光晕 */}
      <div className="relative">
        <div className="abyss-glow pointer-events-none absolute -inset-x-4 -top-6 h-48" />
        <div className="relative grid grid-cols-2 gap-3 md:grid-cols-6">
          <StatCard label="情报总量" value={(stats.total_items || 0).toLocaleString()} />
          <StatCard label="24h 新增" value={stats.new_24h} tone="accent" />
          <StatCard label="AI 相关" value={stats.ai_items} tone="accent" />
          <StatCard label="KEV 在野" value={stats.kev_count} tone="critical" />
          <StatCard label="PoC 可用" value={stats.poc_count} tone="high" />
          <StatCard label="数据源" value={`${stats.sources?.healthy || 0}/${stats.sources?.total || 0}`} tone="low" />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h3 className="h3 mb-3">情报时效 · 披露→入库滞后</h3>
          {fresh ? (
            <div className="grid grid-cols-4 gap-3 pt-2">
              {[["P50", fresh.p50_min], ["P90", fresh.p90_min], ["P95", fresh.p95_min]].map(([k, v]: any) => (
                <div key={k as string}>
                  <div className="h3">{k}</div>
                  <div className="kpi mt-1 text-[20px] text-accent">
                    {v != null ? (v < 60 ? `${v.toFixed(0)}m` : `${(v / 60).toFixed(1)}h`) : "—"}
                  </div>
                </div>
              ))}
              <div>
                <div className="h3">&lt;1h 入库</div>
                <div className="kpi mt-1 text-[20px] text-low">{fresh.buckets?.["<1h"] ?? "—"}</div>
              </div>
            </div>
          ) : <Skeleton className="h-14" />}
        </div>

        {/* 实时监测流 */}
        <div className="card">
          <h3 className="h3 mb-3 flex items-center gap-2">
            <Dot tone={liveOn ? "low" : "dim"} glow={liveOn} />
            实时监测流
            {liveOn && <span className="ml-auto text-micro font-medium tracking-[0.1em] text-low">LIVE</span>}
          </h3>
          <div className="space-y-1 text-[12px]">
            {live.length === 0 && (
              <div className="flex items-center gap-2 py-2 text-faint">
                <span className="dot bg-faint breathe" />等待新情报推送…
              </div>
            )}
            {live.map((it) => (
              <Link key={it.id + it.first_seen_at} href={`/items/${it.id}`}
                className="feed-in group flex items-baseline gap-2 truncate rounded px-1 -mx-1 py-1 hover:bg-white/[0.04]">
                <span className="mono shrink-0 text-[10px] text-faint">
                  {new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
                </span>
                <span className="truncate text-fg/85 group-hover:text-accent transition-colors">
                  {it.title_zh || it.title}
                </span>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h3 className="h3 mb-2">14 天情报趋势</h3>
          <Chart option={trendOpt} style={{ height: 224 }} notMerge />
        </div>
        <div className="card">
          <h3 className="h3 mb-2">AI 安全层分布</h3>
          <Chart option={layerOpt} style={{ height: 224 }} notMerge />
        </div>
      </div>

      {expo && expo.products?.length > 0 && (
        <div className="card">
          <h3 className="h3 mb-3">
            影子 AI 资产暴露
            <span className="ml-2 normal-case tracking-normal text-faint">
              （互联网测绘聚合{expo.products.some((p: any) => p.simulated) ? " · 含模拟数据" : ""}）
            </span>
          </h3>
          <div className="grid gap-2 md:grid-cols-3 lg:grid-cols-5">
            {expo.products.slice(0, 10).map((p: any) => (
              <div key={p.product} className="rounded-lg border border-line bg-edge/60 px-3 py-2.5 transition-colors hover:border-linestrong">
                <div className="truncate text-[13px] font-medium text-fg">{p.product}</div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="kpi text-[18px] text-high">{p.total.toLocaleString()}</span>
                  <span className="text-[10px] text-faint">暴露 · {p.items} 条</span>
                </div>
                {p.cves?.[0] && <div className="mono mt-1 truncate text-[10px] text-faint">{p.cves.slice(0, 2).join(", ")}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="h2">高优先级 AI 情报</h2>
          <Link href="/items" className="text-[12px] text-accent transition-opacity hover:opacity-70">全部 →</Link>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((it) => <ItemCard key={it.id} item={it} />)}
        </div>
      </div>
    </div>
  );
}
