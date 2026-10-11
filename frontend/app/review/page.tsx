"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { API } from "@/lib/api";
import { SevBadge } from "@/components/cards";

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
      <div className="card flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-lg font-semibold">HITL 复核队列</h1>
          <p className="text-sm text-dim">
            {tab === "needs_review" ? <>待复核 <span className="text-accent">{count}</span> 条 · 低置信/富化异常条目需人工确认</>
              : <>共 {count} 条 · review_status = {tab}</>}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="flex rounded-lg border border-border p-0.5">
            {TABS.map(([v, l]) => (
              <button key={v} onClick={() => setTab(v)}
                className={`rounded-md px-3 py-1 text-xs transition-colors ${tab === v ? "bg-accent/15 text-accent" : "text-dim hover:text-fg"}`}>
                {l}
              </button>
            ))}
          </div>
          <button className="btn-ghost !px-2 !py-1 text-xs" onClick={load}>刷新</button>
        </div>
      </div>

      {loading ? (
        <div className="card text-dim">加载中…</div>
      ) : items.length === 0 ? (
        <div className="card flex flex-col items-center gap-2 py-14 text-dim">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-low/15 text-xl text-low">✓</span>
          {tab === "needs_review" ? "队列已清空" : "该状态下无条目"}
        </div>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-dim">
                <th className="p-3">标题</th>
                <th className="p-3">CVE</th>
                <th className="p-3">严重级</th>
                <th className="p-3">置信度</th>
                <th className="p-3">薄弱维度</th>
                <th className="p-3">首次发现</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="border-b border-border/50 hover:bg-border/30">
                  <td className="max-w-md p-3">
                    <Link href={`/items/${it.id}`} className="line-clamp-2 font-medium hover:text-accent">
                      {it.title || it.id}
                    </Link>
                  </td>
                  <td className="p-3">
                    {(it.cve || []).length
                      ? it.cve!.map((c) => <span key={c} className="tag mono mr-1">{c}</span>)
                      : <span className="text-xs text-dim">—</span>}
                  </td>
                  <td className="p-3"><SevBadge s={it.severity} /></td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded bg-border">
                        <div className={`h-1.5 rounded ${confCls(it.confidence)}`}
                          style={{ width: `${Math.round((it.confidence ?? 0) * 100)}%` }} />
                      </div>
                      <span className="text-xs text-dim">
                        {it.confidence != null ? it.confidence.toFixed(2) : "—"}
                      </span>
                    </div>
                  </td>
                  <td className="p-3">
                    <div className="flex max-w-[220px] flex-wrap gap-1">
                      {(it.weak_dims || []).length
                        ? it.weak_dims!.map((d) => (
                            <span key={d} className="tag inline-flex items-center gap-1">
                              <span className="h-1.5 w-1.5 rounded-full bg-critical" />{d}
                            </span>
                          ))
                        : <span className="text-xs text-dim">—</span>}
                    </div>
                  </td>
                  <td className="p-3 text-xs text-dim">
                    {it.first_seen_at ? it.first_seen_at.slice(5, 16).replace("T", " ") : "—"}
                  </td>
                  <td className="p-3">
                    <div className="flex gap-1.5">
                      <button
                        className="rounded border border-low/40 bg-low/10 px-2 py-1 text-xs text-low transition-colors hover:bg-low/20 disabled:opacity-40"
                        disabled={busy === it.id} onClick={() => act(it, "confirm")}>
                        确认
                      </button>
                      <button
                        className="rounded border border-critical/40 bg-critical/10 px-2 py-1 text-xs text-critical transition-colors hover:bg-critical/20 disabled:opacity-40"
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
        <div className="card fixed bottom-6 right-6 z-50 border-accent/40 px-4 py-3 text-sm shadow-lg">
          {msg}
        </div>
      )}
    </div>
  );
}
