"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { api, subscribeFeed } from "@/lib/api";
import { ItemCard } from "@/components/cards";
import { StatStrip, St, Skeleton, SpecRow, SpecDot, Sev } from "@/components/ui";
import { C, SERIES, echartsBase } from "@/lib/theme";

const Chart = dynamic(() => import("echarts-for-react"), { ssr: false });

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [fresh, setFresh] = useState<any>(null);
  const [expo, setExpo] = useState<any>(null);
  const [review, setReview] = useState<any>(null);
  const [live, setLive] = useState<any[]>([]);
  const [liveOn, setLiveOn] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([
      api.stats(),
      api.items({ size: 7, sort: "priority", ai_only: true }),
      api.freshness(),
      api.assetExposure(),
      fetch("/api/review?status=needs_review&size=1").then(r => r.ok ? r.json() : null).catch(() => null),
    ])
      .then(([s, it, f, e, rv]) => { setStats(s); setItems(it.items || []); setFresh(f); setExpo(e); setReview(rv); })
      .catch((e) => setErr(String(e)));
    const off = subscribeFeed((item) => {
      setLiveOn(true);
      setLive((l) => [item, ...l].slice(0, 9));
    });
    return off;
  }, []);

  if (err) return <div className="panel panel-b text-err">后端连接失败：{err}</div>;
  if (!stats) return (
    <div className="space-y-6">
      <Skeleton className="h-[84px]" />
      <div className="grid gap-5 lg:grid-cols-3">
        <Skeleton className="h-[300px] lg:col-span-2" /><Skeleton className="h-[300px]" />
      </div>
    </div>
  );

  const now = new Date();
  const pending = review?.total ?? review?.items?.length ?? null;

  const layerOpt = {
    backgroundColor: "transparent",
    color: SERIES,
    tooltip: echartsBase.tooltip,
    series: [{
      type: "pie", radius: ["60%", "78%"],
      label: { show: false },
      itemStyle: { borderColor: C.bg, borderWidth: 2, borderRadius: 3 },
      data: Object.entries(stats.by_layer || {}).filter(([k]) => k && k !== "null")
        .map(([k, v]) => ({ name: k, value: v })),
    }],
    graphic: [{
      type: "text", left: "center", top: "44%", style: {
        text: (stats.ai_items || 0).toLocaleString(), fill: C.fg, fontSize: 20,
        fontWeight: 500, fontFamily: "JetBrains Mono", textAlign: "center",
      },
    }, {
      type: "text", left: "center", top: "55%", style: {
        text: "AI 相关条目", fill: C.faint, fontSize: 10, textAlign: "center",
      },
    }],
    legend: { ...echartsBase.legend, bottom: 0, left: "center" },
  };
  const trendOpt = {
    backgroundColor: "transparent",
    grid: { left: 36, right: 14, top: 16, bottom: 26 },
    tooltip: { ...echartsBase.tooltip, trigger: "axis" },
    xAxis: { type: "category", ...echartsBase.categoryAxis, boundaryGap: false, data: (stats.trend_14d || []).map((t: any) => t.date.slice(5)) },
    yAxis: { type: "value", ...echartsBase.valueAxis },
    series: [{
      type: "line", smooth: 0.35, showSymbol: false,
      data: (stats.trend_14d || []).map((t: any) => t.count),
      lineStyle: { color: C.accent, width: 1.6 },
      itemStyle: { color: C.accent },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: "rgba(90,180,196,0.16)" }, { offset: 1, color: "rgba(90,180,196,0)" }],
        },
      },
    }],
  };

  return (
    <div>
      <SpecRow>
        <span>FIG_01</span><SpecDot />
        <span>态势总览 · SITUATION</span><SpecDot />
        <span>{now.toISOString().slice(0, 16).replace("T", " ")}Z</span><SpecDot />
        <span>{(stats.total_items || 0).toLocaleString()} ITEMS</span>
        <span className="ml-auto flex items-center gap-1.5 normal-case tracking-normal">
          <St tone={liveOn ? "live" : "dim"}>{liveOn ? "LIVE" : "IDLE"}</St>
        </span>
      </SpecRow>

      {/* hairline stat strip — 不包卡 */}
      <StatStrip stats={[
        { label: "情报总量", value: (stats.total_items || 0).toLocaleString() },
        { label: "24h 新增", value: stats.new_24h ?? "—", tone: "accent" },
        { label: "AI 相关", value: (stats.ai_items || 0).toLocaleString() },
        { label: "KEV 在野", value: stats.kev_count ?? "—", tone: "critical" },
        { label: "待复核", value: pending ?? "—", tone: pending > 0 ? "high" : "fg" },
        { label: "数据源", value: `${stats.sources?.healthy ?? 0}/${stats.sources?.total ?? 0}`, tone: "ok" },
      ]} />

      <div className="mt-6 grid gap-x-8 gap-y-6 lg:grid-cols-3">
        {/* 主区 2/3 */}
        <div className="lg:col-span-2">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="sect-title">14 天情报流入趋势</h2>
            {fresh && (
              <span className="font-mono text-[10.5px] text-faint">
                披露→入库 P50 {fresh.p50_min != null ? (fresh.p50_min < 60 ? `${fresh.p50_min.toFixed(0)}m` : `${(fresh.p50_min / 60).toFixed(1)}h`) : "—"}
                {"  ·  "}P95 {fresh.p95_min != null ? (fresh.p95_min < 60 ? `${fresh.p95_min.toFixed(0)}m` : `${(fresh.p95_min / 60).toFixed(1)}h`) : "—"}
              </span>
            )}
          </div>
          <Chart option={trendOpt} style={{ height: 216 }} notMerge />

          <div className="sect">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="sect-title">高优先级 AI 情报</h2>
              <Link href="/items" className="font-mono text-[11px] text-faint transition-colors hover:text-accent">全部 →</Link>
            </div>
            <div className="divide-y divide-[rgba(255,255,255,0.06)]">
              {items.map((it) => (
                <Link key={it.id} href={`/items/${it.id}`}
                  className="group flex items-center gap-3 px-1 py-2.5 transition-colors hover:bg-[#121315]">
                  <Sev level={it.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] text-fg group-hover:text-accent">{it.title_zh || it.title}</div>
                    <div className="mt-0.5 flex items-center gap-2 font-mono text-[10.5px] text-faint">
                      {it.cve_ids?.slice(0, 2).map((c: string) => <span key={c}>{c}</span>)}
                      <span>{(it.source_names || []).slice(0, 2).join(" · ")}</span>
                    </div>
                  </div>
                  {it.epss_score != null && (
                    <span className="tnum font-mono text-[11px] text-dim" title="EPSS">
                      {(it.epss_score * 100).toFixed(1)}%
                    </span>
                  )}
                  <span className="tnum font-mono text-[11px] text-faint">
                    {it.published_at ? it.published_at.slice(0, 10) : ""}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </div>

        {/* 右栏 1/3 */}
        <div>
          {/* 实时监测流 */}
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="sect-title">实时监测流</h2>
            <St tone={liveOn ? "live" : "dim"}>{liveOn ? "接收中" : "待连接"}</St>
          </div>
          <div className="rounded-md border border-line">
            {live.length === 0 && (
              <div className="px-3 py-8 text-center text-[12px] text-faint">等待新情报推送…</div>
            )}
            <div className="divide-y divide-[rgba(255,255,255,0.05)]">
              {live.map((it) => (
                <Link key={it.id + it.first_seen_at} href={`/items/${it.id}`}
                  className="rise group flex items-baseline gap-2 px-3 py-2 transition-colors hover:bg-[#121315]">
                  <span className="tnum shrink-0 font-mono text-[10px] text-faint">
                    {new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  <span className="truncate text-[12px] text-dim group-hover:text-fg">
                    {it.title_zh || it.title}
                  </span>
                </Link>
              ))}
            </div>
          </div>

          {/* AI 层分布 */}
          <div className="sect">
            <h2 className="sect-title mb-2">AI 安全层分布</h2>
            <Chart option={layerOpt} style={{ height: 200 }} notMerge />
          </div>
        </div>
      </div>

      {expo && expo.products?.length > 0 && (
        <div className="sect">
          <h2 className="sect-title">
            影子 AI 资产暴露
            <span className="ml-2 font-normal normal-case text-faint">
              互联网测绘聚合{expo.products.some((p: any) => p.simulated) ? " · 含模拟数据" : ""}
            </span>
          </h2>
          <table className="dt mt-3">
            <thead>
              <tr><th>产品</th><th className="r">暴露量</th><th className="r">关联条目</th><th>关联 CVE</th></tr>
            </thead>
            <tbody>
              {expo.products.slice(0, 8).map((p: any) => (
                <tr key={p.product}>
                  <td className="font-medium text-fg">{p.product}</td>
                  <td className="r num text-high">{p.total.toLocaleString()}</td>
                  <td className="r num text-dim">{p.items}</td>
                  <td className="mono text-[11px] text-faint">{p.cves?.slice(0, 3).join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
