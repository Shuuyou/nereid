"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { API } from "@/lib/api";
import { SevBadge } from "@/components/cards";
import { CheckCircle2 } from "lucide-react";

const TABS = [
  ["needs_review", "待复核"],
  ["confirmed", "已确认"],
  ["auto", "自动通过"],
] as const;
type Tab = (typeof TABS)[number][0];

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

function confCls(c?: number) {
  if (c == null) return "bg-border";
  if (c >= 0.7) return "bg-low";
  if (c >= 0.4) return "bg-medium";
  return "bg-critical";
}

export default function ReviewPage() {
  const [tab, setTab] = useState<Tab>("needs_review");
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

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
    setBusy(it.id);
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

  return (
    <div className="space-y-4">
      <div className="mb-1 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h2">HITL 复核队列</h1>
          <p className="mt-0.5 text-[12px] text-faint">
            {tab === "needs_review" ? <>待复核 <span className="text-accent">{count}</span> 条 · 低置信/富化异常需人工确认</>
              : <>共 {count} 条 · review_status = {tab}</>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-line p-0.5">
            {TABS.map(([v, l]) => (
              <button key={v} onClick={() => setTab(v)}
                className={`rounded-md px-3 py-1 text-[11px] transition-colors ${tab === v ? "bg-white/[0.08] text-fg" : "text-faint hover:text-dim"}`}>
                {l}
              </button>
            ))}
          </div>
          <button className="btn-ghost !px-2 !py-1 !text-[11px]" onClick={load}>刷新</button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">{[0,1,2].map(i => <div key={i} className="skeleton h-14" />)}</div>
      ) : items.length === 0 ? (
        <div className="card flex flex-col items-center gap-2 py-14">
          <CheckCircle2 size={28} strokeWidth={1.5} className="text-low" />
          <div className="text-[13px] text-dim">{tab === "needs_review" ? "队列已清空" : "该状态下无条目"}</div>
        </div>
      ) : (
        <div className="card overflow-x-auto !p-0">
          <table className="tbl">
            <thead>
              <tr><th>标题</th><th>CVE</th><th>严重级</th><th>置信度</th><th>薄弱维度</th><th>首次发现</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id}>
                  <td className="max-w-md">
                    <Link href={`/items/${it.id}`} className="line-clamp-2 font-medium hover:text-accent">
                      {it.title || it.id}
                    </Link>
                  </td>
                  <td>
                    {(it.cve || []).length
                      ? it.cve!.map((c) => <span key={c} className="tag mono mr-1">{c}</span>)
                      : <span className="text-xs text-dim">—</span>}
                  </td>
                  <td><SevBadge s={it.severity} /></td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/[0.07]">
                        <div className={`h-full rounded-full ${confCls(it.confidence)}`}
                          style={{ width: `${Math.round((it.confidence ?? 0) * 100)}%` }} />
                      </div>
                      <span className="mono text-[11px] text-dim">{it.confidence != null ? it.confidence.toFixed(2) : "—"}</span>
                    </div>
                  </td>
                  <td>
                    <div className="flex max-w-[220px] flex-wrap gap-1">
                      {(it.weak_dims || []).length
                        ? it.weak_dims!.map((d) => (
                            <span key={d} className="tag">
                              <span className="h-1.5 w-1.5 rounded-full bg-critical" />{d}
                            </span>
                          ))
                        : <span className="text-xs text-dim">—</span>}
                    </div>
                  </td>
                  <td className="text-[11px] text-faint">
                    {it.first_seen_at ? it.first_seen_at.slice(5, 16).replace("T", " ") : "—"}
                  </td>
                  <td>
                    <div className="flex gap-1.5">
                      <button
                        className="rounded-md border border-low/30 bg-low/[0.08] px-2 py-1 text-[11px] text-low transition-colors hover:bg-low/[0.15] disabled:opacity-40"
                        disabled={busy === it.id} onClick={() => act(it, "confirm")}>
                        确认
                      </button>
                      <button
                        className="rounded-md border border-critical/30 bg-critical/[0.08] px-2 py-1 text-[11px] text-critical transition-colors hover:bg-critical/[0.15] disabled:opacity-40"
                        disabled={busy === it.id} onClick={() => act(it, "reject")}>
                        回炉
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {msg && (
        <div className="card fixed bottom-6 right-6 z-50 border-accent/30 bg-overlay px-4 py-3 text-[13px] shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
          {msg}
        </div>
      )}
    </div>
  );
}
