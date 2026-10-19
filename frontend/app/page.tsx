"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { api, subscribeFeed, getDigest } from "@/lib/api";
import { St, Skeleton, SpecRow, SpecDot, Sev } from "@/components/ui";
import { CheckCheck, RotateCcw, ArrowRight, Flame, Crosshair, Newspaper, TrendingUp, Layers, Database } from "lucide-react";
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
        <div className="truncate text-[14px] font-medium text-fg group-hover:text-accent">
          {it.title_zh || it.title}
        </div>
        <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-faint">
          {(it.cve || it.cve_ids || []).slice(0, 2).map((c: string) => <span key={c}>{c}</span>)}
          {it.is_kev && <span className="font-semibold text-crit">KEV</span>}
          {(it.source_names || []).slice(0, 1).map((s: string) => <span key={s}>{s}</span>)}
          {it.source_count > 1 && <span className="text-dim">×{it.source_count}源</span>}
        </div>
      </Link>
      {kind === "review" && it.confidence != null && (
        <span className="tnum w-10 text-right font-mono text-[12px] text-dim" title="AI 置信度">
          {(it.confidence * 100).toFixed(0)}%
        </span>
      )}
      {it.epss_score != null && kind !== "review" && (
        <span className="tnum w-12 text-right font-mono text-[12px] text-dim" title="EPSS">
          {(it.epss_score * 100).toFixed(1)}%
        </span>
      )}
      <span className="tnum w-11 text-right font-mono text-[11px] text-faint">
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
        <span>今日值班台</span><SpecDot />
        <span>{now.toISOString().slice(0, 16).replace("T", " ")}Z</span>
        <span className="ml-auto flex items-center gap-1.5 normal-case tracking-normal">
          <St tone={liveOn ? "live" : "dim"}>{liveOn ? "LIVE" : "IDLE"}</St>
        </span>
      </SpecRow>

      {/* 指标卡：白卡为底，pastel 只留给语义图标芯片——色彩即分类不是装饰 */}
      <div className="mt-1 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        {([
          { label: "待复核", sub: "队列待人工确认", v: reviewTotal, chip: "bg-rose text-rose-ink", icon: Crosshair, href: "/review?status=needs_review" },
          { label: "24h 新增", sub: "情报流入", v: stats.new_24h ?? "—", chip: "bg-mint text-mint-ink", icon: TrendingUp, href: "/items" },
          { label: "KEV 在野", sub: "已确认被利用", v: stats.kev_count ?? "—", chip: "bg-peach text-peach-ink", icon: Flame, href: "/items?kev=1" },
          { label: "AI 相关", sub: "命中画像占比", v: (stats.ai_items || 0).toLocaleString(), chip: "bg-lav text-lav-ink", icon: Layers, href: "/items" },
          { label: "数据源", sub: "健康 / 总数", v: `${stats.sources?.healthy ?? 0}/${stats.sources?.total ?? 0}`, chip: "bg-sky text-sky-ink", icon: Database, href: "/sources" },
        ] as const).map((m) => (
          <Link key={m.label} href={m.href}
            className={`tile group flex flex-col justify-between transition-transform duration-100 hover:-translate-y-px ${
              m.label === "待复核" && reviewTotal > 0 ? "tile-rose" : "tile-white"}`}>
            <span className="flex items-center gap-2">
              <span className={`flex h-6 w-6 items-center justify-center rounded-[8px] ${m.chip}`}>
                <m.icon size={13} strokeWidth={2} />
              </span>
              <span className="tile-kicker">{m.label}</span>
            </span>
            <span className="tile-metric mt-4">{m.v}</span>
            <span className="tile-sub mt-1.5">{m.sub}</span>
          </Link>
        ))}
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-12">
        {/* ── 左：需要你处理（可操作队列）── */}
        <div className="lg:col-span-7">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="sect-title">需要你处理</h2>
            <Link href="/review" className="font-mono text-[12px] text-faint transition-colors hover:text-accent">
              全部队列 →
            </Link>
          </div>
          <div className="tile tile-white !p-0 overflow-hidden">
            {/* 待复核组 — pastel 标签条 */}
            <div className="flex items-center gap-2.5 border-b border-line bg-surface px-3 py-2">
              <span className="h-2 w-2 rounded-[3px] bg-rose" style={{ background: "var(--rose-ink)" }} />
              <span className="text-[12px] font-medium text-fg">待复核</span>
              <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-faint">AI 初判待确认</span>
              <span className="ml-auto mono text-[12px] text-faint">{reviewTotal}</span>
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
            <div className="flex items-center gap-2.5 border-y border-line bg-surface px-3 py-2">
              <span className="h-2 w-2 rounded-[3px]" style={{ background: "var(--sky-ink)" }} />
              <span className="text-[12px] font-medium text-fg">高优先级</span>
              <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-faint">AI 情报</span>
              <span className="ml-auto mono text-[12px] text-faint">{queue.length}</span>
            </div>
            <div className="divide-y divide-[rgba(33,31,38,0.05)]">
              {queue.slice(0, 5).map((it) => <QueueRow key={it.id} it={it} kind="pri" />)}
            </div>
            {/* KEV 组 */}
            <div className="flex items-center gap-2.5 bg-surface px-3 py-2">
              <span className="h-2 w-2 rounded-[3px]" style={{ background: "var(--peach-ink)" }} />
              <span className="text-[12px] font-medium text-fg">新 KEV</span>
              <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-faint">在野利用</span>
              <span className="ml-auto mono text-[12px] text-faint">{kev.length}</span>
            </div>
            <div className="divide-y divide-[rgba(33,31,38,0.05)]">
              {kev.slice(0, 4).map((it) => <QueueRow key={it.id} it={it} kind="kev" />)}
            </div>
          </div>

        </div>

        {/* ── 右：晨报（深色锚点卡）+ 趋势 + 实时流 ── */}
        <div className="lg:col-span-5">
          <div className="tile tile-dark">
            <div className="tile-kicker" style={{ color: "#a49f8f" }}>晨报 MORNING BRIEF</div>
            <div className="mt-2 flex items-center gap-2">
              <Newspaper size={15} strokeWidth={1.75} className="text-[#7adfd8]" />
              <span className="text-[14px] font-semibold text-[#eceef0]">过去 7 天画像摘要</span>
              <span className="display-en italic ml-auto text-[15px] text-[#a49f8f]">your daily brief</span>
            </div>
            {digest?.digest ? (
              <div className="mt-3 space-y-2 text-[13px] leading-relaxed text-[#b9bcc4]">
                {String(digest.digest).split("\n").filter(Boolean).slice(0, 6).map((l: string, i: number) => (
                  <p key={i}>{l}</p>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-[13px] leading-relaxed text-[#8a8d96]">
                {digest ? "近 7 天无画像命中摘要。" : "配置「关注需求」画像后，此处将生成每日晨报——昨晚发生了什么、哪些与你相关。"}
              </p>
            )}
            {digest?.item_count != null && (
              <div className="mt-3 border-t border-[rgba(255,255,255,0.08)] pt-2 font-mono text-[11px] text-[#8a8d96]">
                命中 {digest.item_count} 条，画像 {localStorage.getItem("foryou_name") || "—"}
              </div>
            )}
          </div>

          {/* 趋势 */}
          <div className="mt-5">
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="sect-title">14 天情报流入</h2>
              {fresh && (
                <span className="font-mono text-[11px] text-faint">
                  P50 {fresh.p50_min != null ? (fresh.p50_min < 60 ? `${fresh.p50_min.toFixed(0)}m` : `${(fresh.p50_min / 60).toFixed(1)}h`) : "—"}
                  {"  "}P95 {fresh.p95_min != null ? (fresh.p95_min < 60 ? `${fresh.p95_min.toFixed(0)}m` : `${(fresh.p95_min / 60).toFixed(1)}h`) : "—"}
                </span>
              )}
            </div>
            <Chart option={trendOpt} style={{ height: 160 }} notMerge />
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
                    <span className="tnum shrink-0 font-mono text-[11px] text-faint">
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
              互联网测绘聚合{expo.products.some((p: any) => p.simulated) ? "（含模拟数据）" : ""}
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
                  <td className="mono text-[12px] text-faint">{p.cves?.slice(0, 3).join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
