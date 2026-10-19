"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { API, api } from "@/lib/api";
import { SpecRow, SpecDot, PageHeader, Empty, Skeleton, Sev } from "@/components/ui";
import { Check, Undo2, RefreshCw } from "lucide-react";

const TABS = [
  ["needs_review", "待复核"],
  ["confirmed", "已确认"],
  ["auto", "自动通过"],
] as const;
type Tab = (typeof TABS)[number][0];
const TAB_VALUES = new Set<string>(TABS.map(([v]) => v));

interface ReviewItem {
  id: string;
  title: string;
  cve?: string[];
  severity?: string;
  confidence?: number;
  review_status: string;
  weak_dims?: string[];
  first_seen_at?: string | null;
}

/** 置信度 → 语义色（高可信 ok / 中 warn / 低 err，不吃品牌色） */
function confTone(c?: number) {
  if (c == null) return "bg-surface2";
  if (c >= 0.7) return "bg-ok";
  if (c >= 0.4) return "bg-warn";
  return "bg-err";
}
function confText(c?: number) {
  if (c == null) return "text-faint";
  if (c >= 0.7) return "text-ok";
  if (c >= 0.4) return "text-warn";
  return "text-err";
}

function ReviewInner() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const tabParam = sp.get("status") || "";
  const tab: Tab = TAB_VALUES.has(tabParam) ? (tabParam as Tab) : "needs_review";
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  const setTab = (v: Tab) => {
    const p = new URLSearchParams(sp.toString());
    if (v === "needs_review") p.delete("status"); else p.set("status", v);
    router.replace(p.toString() ? `${pathname}?${p}` : pathname, { scroll: false });
  };

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/review?status=${tab}&limit=50`, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then((d) => {
        setItems(d.items || []);
        setCount(d.count ?? (d.items || []).length);
      })
      .catch(() => { setItems([]); setCount(0); })
      .finally(() => setLoading(false));
  }, [tab]);
  useEffect(load, [load]);

  function toast(text: string) {
    setMsg(text);
    setTimeout(() => setMsg(""), 2500);
  }

  async function act(it: ReviewItem, action: "confirm" | "reject") {
    setBusy(it.id + action);
    try {
      const r = await fetch(`${API}/api/review/${encodeURIComponent(it.id)}/${action}`, { method: "POST" });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      // 操作成功后该条目状态已变更，从当前队列移除
      setItems((rows) => rows.filter((x) => x.id !== it.id));
      setCount((c) => Math.max(0, c - 1));
      const name = (it.title || it.id).slice(0, 30);
      toast(action === "confirm" ? `已确认入库：${name}` : `已回炉重富化：${name}`);
    } catch (e) {
      toast(`操作失败：${e}`);
    } finally {
      setBusy(null);
    }
  }

  async function reEnrich(it: ReviewItem) {
    setBusy(it.id + "enrich");
    try {
      await api.enrich(it.id);
      toast(`重富化已触发：${(it.title || it.id).slice(0, 30)}`);
    } catch (e) {
      toast(`触发失败：${e}`);
    } finally {
      setBusy(null);
    }
  }

  const pendingLabel = tab === "needs_review" ? "PENDING" : tab === "confirmed" ? "CONFIRMED" : "AUTO";

  return (
    <div>
      <SpecRow>
        <span>FIG_04</span><SpecDot />
        <span>REVIEW QUEUE</span><SpecDot />
        <span>{count} {pendingLabel}</span>
      </SpecRow>

      <PageHeader title="HITL 复核队列" desc="低置信 / 富化异常条目需人工确认 · reject 后清空富化结果回炉"
        right={<button className="btn" onClick={load}><RefreshCw size={12} strokeWidth={1.75} />刷新</button>} />

      {/* 状态 tabs — 下划线式，非药丸 */}
      <div className="flex h-10 items-stretch gap-5 border-b border-line">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)}
            className={`h-full border-b-2 text-[12px] transition-colors ${
              tab === v ? "border-accent font-medium text-fg" : "border-transparent text-faint hover:text-dim"}`}>
            {l}
            {tab === v && <span className="ml-1.5 font-mono text-[10.5px] text-faint">{count}</span>}
          </button>
        ))}
        <span className="ml-auto self-center font-mono text-[10.5px] uppercase tracking-[0.06em] text-faint">
          review_status = {tab}
        </span>
      </div>

      {loading ? (
        <div className="mt-4 space-y-px">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9" />)}
        </div>
      ) : items.length === 0 ? (
        <div className="mt-4">
          <Empty text={tab === "needs_review" ? "队列已清空" : "该状态下无条目"}
            hint={tab === "needs_review" ? "所有待复核条目均已处理" : undefined} />
        </div>
      ) : (
        <table className="dt mt-2">
          <thead>
            <tr>
              <th>条目</th>
              <th>CVE</th>
              <th>严重级</th>
              <th>置信度</th>
              <th>薄弱维度</th>
              <th>首次发现</th>
              <th className="r">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id} className="rowlink">
                <td className="max-w-[380px]">
                  <Link href={`/items/${it.id}`}
                    className="stretched block truncate text-[12.5px] text-fg transition-colors hover:text-accent">
                    {it.title || it.id}
                  </Link>
                  <div className="mono mt-0.5 text-[10px] text-faint">{it.id}</div>
                </td>
                <td>
                  {(it.cve || []).length
                    ? it.cve!.map((c) => <span key={c} className="badge mono">{c}</span>)
                    : <span className="text-faint">—</span>}
                </td>
                <td><Sev level={it.severity} /></td>
                <td>
                  <div className="flex items-center gap-2">
                    <div className="h-[3px] w-16 rounded-full bg-surface2">
                      <div className={`h-full rounded-full ${confTone(it.confidence)}`}
                        style={{ width: `${Math.round((it.confidence ?? 0) * 100)}%` }} />
                    </div>
                    <span className={`tnum font-mono text-[11px] ${confText(it.confidence)}`}>
                      {it.confidence != null ? `${Math.round(it.confidence * 100)}%` : "—"}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="flex max-w-[200px] flex-wrap gap-1">
                    {(it.weak_dims || []).length
                      ? it.weak_dims!.map((d) => (
                          <span key={d} className="badge mono">
                            <span className="dot" style={{ background: "var(--err)" }} />{d}
                          </span>
                        ))
                      : <span className="text-faint">—</span>}
                  </div>
                </td>
                <td className="num text-faint">
                  {it.first_seen_at ? it.first_seen_at.slice(5, 16).replace("T", " ") : "—"}
                </td>
                <td className="r z-act">
                  <div className="flex justify-end gap-1.5">
                    <button className="btn btn-sm !border-ok/40 !text-ok hover:!bg-ok/10"
                      disabled={busy !== null} onClick={() => act(it, "confirm")}>
                      <Check size={11} strokeWidth={2} />确认
                    </button>
                    <button className="btn btn-sm !border-err/40 !text-err hover:!bg-err/10"
                      disabled={busy !== null} onClick={() => act(it, "reject")}>
                      <Undo2 size={11} strokeWidth={2} />回炉
                    </button>
                    <button className="btn btn-sm btn-ghost" title="重新触发富化 worker"
                      disabled={busy !== null} onClick={() => reEnrich(it)}>
                      <RefreshCw size={11} strokeWidth={1.75} />重富化
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {msg && (
        <div className="rise fixed bottom-5 right-5 z-50 rounded-[8px] border border-line border-l-2 border-l-accent bg-panel px-4 py-2.5 text-[12.5px] text-fg">
          {msg}
        </div>
      )}
    </div>
  );
}

export default function ReviewPage() {
  return (
    <Suspense>
      <ReviewInner />
    </Suspense>
  );
}
