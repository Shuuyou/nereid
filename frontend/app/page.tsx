"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { api, subscribeFeed, getDigest } from "@/lib/api";
import { StatStrip, St, Skeleton, SpecRow, SpecDot, Sev } from "@/components/ui";
import { CheckCheck, RotateCcw, ArrowRight, Flame, Crosshair, Newspaper } from "lucide-react";
import { C, echartsBase } from "@/lib/theme";

const Chart = dynamic(() => import("echarts-for-react"), { ssr: false });

function relTime(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const m = Math.max(1, Math.round((Date.now() - d) / 60000));
  if (m < 60) return `${m}m前`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h前`;
  return `${Math.round(h / 24)}d前`;
}

/** 队列行：严重度 + 标题 + 元数据 + 行内动作（可办，不只是可看） */
function QueueRow({ it, kind, onConfirm, onReject }: {
  it: any; kind: "review" | "pri" | "kev";
  onConfirm?: (id: string) => void; onReject?: (id: string) => void;
}) {
  return (
    <div className="group flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-surface">
      <Sev level={it.severity} />
      <Link href={`/items/${it.id}`} className="min-w-0 flex-1">
        <div className="truncate text-[13px] text-fg group-hover:text-accent">
          {it.title_zh || it.title}
        </div>
        <div className="mt-0.5 flex items-center gap-2 font-mono text-[10.5px] text-faint">
          {(it.cve || it.cve_ids || []).slice(0, 2).map((c: string) => <span key={c}>{c}</span>)}
          {it.is_kev && <span className="font-semibold text-crit">KEV</span>}
          {(it.source_names || []).slice(0, 1).map((s: string) => <span key={s}>{s}</span>)}
          {it.source_count > 1 && <span className="text-dim">×{it.source_count}源</span>}
        </div>
      </Link>
      {kind === "review" && it.confidence != null && (
        <span className="tnum w-10 text-right font-mono text-[11px] text-dim" title="AI 置信度">
          {(it.confidence * 100).toFixed(0)}%
        </span>
      )}
      {it.epss_score != null && kind !== "review" && (
        <span className="tnum w-12 text-right font-mono text-[11px] text-dim" title="EPSS">
          {(it.epss_score * 100).toFixed(1)}%
        </span>
      )}
      <span className="tnum w-11 text-right font-mono text-[10.5px] text-faint">
        {relTime(it.published_at || it.first_seen_at)}
      </span>
      {kind === "review" ? (
        <span className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button title="确认" onClick={() => onConfirm?.(it.id)}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-line text-ok transition-colors hover:bg-mint">
            <CheckCheck size={12} strokeWidth={2} />
          </button>
          <button title="回炉重富化" onClick={() => onReject?.(it.id)}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-line text-warn transition-colors hover:bg-butter">
            <RotateCcw size={12} strokeWidth={2} />
          </button>
        </span>
      ) : (
        <Link href={`/items/${it.id}`} className="shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100">
          <ArrowRight size={13} />
        </Link>
      )}
    </div>
  );
}

export default function DutyDesk() {
  const [stats, setStats] = useState<any>(null);
  const [queue, setQueue] = useState<any[]>([]);      // 高优 AI 情报
  const [review, setReview] = useState<any[]>([]);    // 待复核
  const [reviewTotal, setReviewTotal] = useState(0);
  const [kev, setKev] = useState<any[]>([]);          // 新 KEV/武器化
  const [digest, setDigest] = useState<any>(null);
  const [fresh, setFresh] = useState<any>(null);
  const [expo, setExpo] = useState<any>(null);
  const [live, setLive] = useState<any[]>([]);
  const [liveOn, setLiveOn] = useState(false);
  const [err, setErr] = useState("");

  const loadReview = () =>
    fetch("/api/review?status=needs_review&size=6").then(r => r.ok ? r.json() : null)
      .then(rv => { setReview(rv?.items || []); setReviewTotal(rv?.count ?? rv?.items?.length ?? 0); })
      .catch(() => {});

  const reviewAction = (id: string, action: "confirm" | "reject") =>
    fetch(`/api/review/${id}/${action}`, { method: "POST" }).then(loadReview).catch(() => {});

  useEffect(() => {
    Promise.all([
      api.stats(), api.items({ size: 7, sort: "priority", ai_only: true }),
      api.items({ size: 5, kev: true, sort: "published" }),
      api.freshness(), api.assetExposure(),
    ]).then(([s, it, kv, f, e]) => {
      setStats(s); setQueue(it.items || []); setKev(kv.items || []); setFresh(f); setExpo(e);
    }).catch((e) => setErr(String(e)));
    loadReview();
    const name = typeof window !== "undefined" ? localStorage.getItem("foryou_name") : "";
    if (name) getDigest(name, 7).then(setDigest).catch(() => {});
    const off = subscribeFeed((item) => { setLiveOn(true); setLive((l) => [item, ...l].slice(0, 6)); });
    return off;
  }, []);

  if (err) return <div className="panel panel-b text-err">后端连接失败:{err}</div>;
  if (!stats) return (
    <div className="space-y-6">
      <Skeleton className="h-[84px]" />
      <div className="grid gap-5 lg:grid-cols-3">
        <Skeleton className="h-[320px] lg:col-span-2" /><Skeleton className="h-[320px]" />
      </div>
    </div>
  );

  const now = new Date();
  const trendOpt = {
    backgroundColor: "transparent",
    grid: { left: 30, right: 8, top: 10, bottom: 20 },
    tooltip: { ...echartsBase.tooltip, trigger: "axis" },
    xAxis: { ...echartsBase.categoryAxis, boundaryGap: false,
      data: (stats.trend_14d || []).map((t: any) => t.date.slice(5)) },
    yAxis: { ...echartsBase.valueAxis },
    series: [{
      type: "line", smooth: 0.35, showSymbol: false,
      data: (stats.trend_14d || []).map((t: any) => t.count),
      lineStyle: { color: C.acc, width: 1.6 }, itemStyle: { color: C.acc },
      areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: "rgba(21,122,119,0.16)" }, { offset: 1, color: "rgba(21,122,119,0)" }] } },
    }],
  };

  return (
    <div>
      <SpecRow>
        <span>DUTY_01</span><SpecDot />
        <span>今日值班台 · DUTY DESK</span><SpecDot />
        <span>{now.toISOString().slice(0, 16).replace("T", " ")}Z</span>
        <span className="ml-auto flex items-center gap-1.5 normal-case tracking-normal">
          <St tone={liveOn ? "live" : "dim"}>{liveOn ? "LIVE" : "IDLE"}</St>
        </span>
      </SpecRow>

      {/* hairline stat strip — 只留 actionable 指标 */}
      <StatStrip stats={[
        { label: "待复核", value: reviewTotal, tone: reviewTotal > 0 ? "high" : "fg" },
        { label: "24h 新增", value: stats.new_24h ?? "—", tone: "accent" },
        { label: "KEV 在野", value: stats.kev_count ?? "—", tone: "critical" },
        { label: "AI 相关", value: (stats.ai_items || 0).toLocaleString() },
        { label: "数据源", value: `${stats.sources?.healthy ?? 0}/${stats.sources?.total ?? 0}`, tone: "ok" },
      ]} />

      <div className="mt-6 grid gap-5 lg:grid-cols-12">
        {/* ── 左 2/3：需要你处理（可操作队列）── */}
        <div className="lg:col-span-8">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="sect-title">需要你处理</h2>
            <Link href="/review" className="font-mono text-[11px] text-faint transition-colors hover:text-accent">
              全部队列 →
            </Link>
          </div>
          <div className="tile tile-white !p-0 overflow-hidden">
            {/* 待复核组 */}
            <div className="flex items-center gap-2 border-b border-line bg-surface px-3 py-2">
              <Crosshair size={12} strokeWidth={1.75} className="text-high" />
              <span className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-dim">
                待复核 · AI 初判待确认
              </span>
              <span className="ml-auto mono text-[11px] text-faint">{reviewTotal}</span>
            </div>
            {review.length === 0 && <div className="px-3 py-4 text-[12px] text-faint">复核队列已清空 ✓</div>}
            <div className="divide-y divide-[rgba(33,31,38,0.05)]">
              {review.slice(0, 5).map((it) => (
                <QueueRow key={it.id} it={it} kind="review"
                  onConfirm={(id) => reviewAction(id, "confirm")}
                  onReject={(id) => reviewAction(id, "reject")} />
              ))}
            </div>
            {/* 高优组 */}
            <div className="flex items-center gap-2 border-y border-line bg-surface px-3 py-2">
              <Flame size={12} strokeWidth={1.75} className="text-crit" />
              <span className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-dim">
                高优先级 · AI 情报
              </span>
              <span className="ml-auto mono text-[11px] text-faint">{queue.length}</span>
            </div>
            <div className="divide-y divide-[rgba(33,31,38,0.05)]">
              {queue.slice(0, 5).map((it) => <QueueRow key={it.id} it={it} kind="pri" />)}
            </div>
            {/* KEV 组 */}
            <div className="flex items-center gap-2 border-y border-line bg-surface px-3 py-2">
              <Flame size={12} strokeWidth={1.75} className="text-crit" />
              <span className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-dim">
                新 KEV · 在野利用
              </span>
              <span className="ml-auto mono text-[11px] text-faint">{kev.length}</span>
            </div>
            <div className="divide-y divide-[rgba(33,31,38,0.05)]">
              {kev.slice(0, 4).map((it) => <QueueRow key={it.id} it={it} kind="kev" />)}
            </div>
          </div>

          {/* 趋势 */}
          <div className="sect">
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="sect-title">14 天情报流入</h2>
              {fresh && (
                <span className="font-mono text-[10.5px] text-faint">
                  披露→入库 P50 {fresh.p50_min != null ? (fresh.p50_min < 60 ? `${fresh.p50_min.toFixed(0)}m` : `${(fresh.p50_min / 60).toFixed(1)}h`) : "—"}
                  {"  ·  "}P95 {fresh.p95_min != null ? (fresh.p95_min < 60 ? `${fresh.p95_min.toFixed(0)}m` : `${(fresh.p95_min / 60).toFixed(1)}h`) : "—"}
                </span>
              )}
            </div>
            <Chart option={trendOpt} style={{ height: 180 }} notMerge />
          </div>
        </div>

        {/* ── 右 1/3：晨报（深色锚点卡）+ 实时流 ── */}
        <div className="lg:col-span-4">
          <div className="tile tile-dark">
            <div className="tile-kicker" style={{ color: "#a49f8f" }}>晨报 · Morning Brief</div>
            <div className="mt-2 flex items-center gap-2">
              <Newspaper size={15} strokeWidth={1.75} className="text-[#7adfd8]" />
              <span className="text-[14px] font-semibold text-[#eceef0]">过去 7 天 · 画像摘要</span>
            </div>
            {digest?.digest ? (
              <div className="mt-3 space-y-2 text-[12.5px] leading-relaxed text-[#b9bcc4]">
                {String(digest.digest).split("\n").filter(Boolean).slice(0, 6).map((l: string, i: number) => (
                  <p key={i}>{l}</p>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-[12.5px] leading-relaxed text-[#8a8d96]">
                {digest ? "近 7 天无画像命中摘要。" : "配置「关注需求」画像后，此处将生成每日晨报——昨晚发生了什么、哪些与你相关。"}
              </p>
            )}
            {digest?.item_count != null && (
              <div className="mt-3 border-t border-[rgba(255,255,255,0.08)] pt-2 font-mono text-[10.5px] text-[#8a8d96]">
                命中 {digest.item_count} 条 · 画像 {localStorage.getItem("foryou_name") || "—"}
              </div>
            )}
          </div>

          {/* 实时监测流 */}
          <div className="mt-5">
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="sect-title">实时监测流</h2>
              <St tone={liveOn ? "live" : "dim"}>{liveOn ? "接收中" : "待连接"}</St>
            </div>
            <div className="rounded-nest border border-line bg-paper">
              {live.length === 0 && (
                <div className="px-3 py-8 text-center text-[12px] text-faint">等待新情报推送…</div>
              )}
              <div className="divide-y divide-[rgba(33,31,38,0.05)]">
                {live.map((it) => (
                  <Link key={it.id + it.first_seen_at} href={`/items/${it.id}`}
                    className="rise group flex items-baseline gap-2 px-3 py-2 transition-colors hover:bg-surface">
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
          </div>
        </div>
      </div>

      {/* 资产暴露 */}
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
