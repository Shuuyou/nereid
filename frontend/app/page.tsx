"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { api, subscribeFeed, getDigest } from "@/lib/api";
import { St, Skeleton, Sev } from "@/components/ui";
import { CheckCheck, RotateCcw, ArrowRight, Newspaper } from "lucide-react";
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

/** 队列行：severity字形 + 标题(主) + 单行meta(次) + 一个数字 + 行内动作
    纪律：一行只允许一个视觉焦点；meta ≤3 段；重复的[KEV]前缀从标题剥离 */
function QueueRow({ it, kind, onConfirm, onReject }: {
  it: any; kind: "review" | "pri" | "kev";
  onConfirm?: (id: string) => void; onReject?: (id: string) => void;
}) {
  const title = String(it.title_zh || it.title || "").replace(/^\s*[【\[]?KEV[】\]]\s*/i, "");
  const score = kind === "review" && it.confidence != null ? `置信 ${(it.confidence * 100).toFixed(0)}%`
    : it.epss_score != null ? `EPSS ${(it.epss_score * 100).toFixed(1)}%` : null;
  return (
    <div className="group flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-surface">
      <Sev level={it.severity} />
      <Link href={`/items/${it.id}`} className="min-w-0 flex-1">
        <div className="truncate text-[14.5px] font-medium leading-snug text-fg group-hover:text-accent">
          {title}
        </div>
        <div className="mt-1 flex items-center gap-2.5 text-[12px] text-faint">
          {(it.cve || it.cve_ids || []).slice(0, 1).map((c: string) =>
            <span key={c} className="font-mono">{c}</span>)}
          {it.is_kev && <span className="font-medium text-err">KEV</span>}
          {score && <span className="tnum">{score}</span>}
          <span className="tnum">{relTime(it.published_at || it.first_seen_at)}</span>
        </div>
      </Link>
      {kind === "review" ? (
        <span className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button title="确认" onClick={() => onConfirm?.(it.id)}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-line text-ok transition-colors hover:bg-mint">
            <CheckCheck size={13} strokeWidth={2} />
          </button>
          <button title="回炉重富化" onClick={() => onReject?.(it.id)}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-line text-warn transition-colors hover:bg-butter">
            <RotateCcw size={13} strokeWidth={2} />
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
      {/* 页内无标题：顶栏已显示"今日值班台"+日期（不重复） */}

      {/* 指标行：数字+灰标签的文字链（Linear/Stripe 式——无icon无卡片无彩色，可点击下钻） */}
      <div className="mt-1 flex flex-wrap items-baseline gap-x-9 gap-y-2 border-b border-line pb-4">
        {([
          { label: "待复核", v: reviewTotal, href: "/review?status=needs_review" },
          { label: "24h 新增", v: stats.new_24h ?? "—", href: "/items" },
          { label: "KEV 在野", v: (stats.kev_count ?? 0).toLocaleString(), href: "/items?kev=1" },
          { label: "AI 相关", v: (stats.ai_items || 0).toLocaleString(), href: "/items" },
          { label: "数据源", v: `${stats.sources?.healthy ?? 0}/${stats.sources?.total ?? 0}`, href: "/sources" },
        ] as const).map((m) => (
          <Link key={m.label} href={m.href} className="group block">
            <span className={`block mono text-[26px] font-medium leading-none tnum transition-colors group-hover:text-accent ${
              m.label === "待复核" && reviewTotal > 0 ? "text-err" : "text-fg"}`}>{m.v}</span>
            <span className="mt-1 block text-[12px] text-faint transition-colors group-hover:text-dim">{m.label}</span>
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
            {/* 待复核组 */}
            <div className="flex items-center gap-2.5 border-b border-line px-3 py-2">
              <span className="text-[12px] font-medium text-fg">待复核</span>
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
            <div className="flex items-center gap-2.5 border-y border-line px-3 py-2">
              <span className="text-[12px] font-medium text-fg">高优先级</span>
              <span className="ml-auto mono text-[12px] text-faint">{queue.length}</span>
            </div>
            <div className="divide-y divide-[rgba(33,31,38,0.05)]">
              {queue.slice(0, 5).map((it) => <QueueRow key={it.id} it={it} kind="pri" />)}
            </div>
            {/* KEV 组 */}
            <div className="flex items-center gap-2.5 px-3 py-2">
              <span className="text-[12px] font-medium text-fg">新 KEV</span>
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
              {fresh?.p50_min != null && (
                <span className="text-[11px] text-faint" title="入库时效中位数">
                  入库时效 {fresh.p50_min < 60 ? `${fresh.p50_min.toFixed(0)} 分钟` : `${(fresh.p50_min / 60).toFixed(1)} 小时`}
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
