"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { API, api } from "@/lib/api";
import { PageHeader, Empty, Skeleton, Sev } from "@/components/ui";
import { zh, ENRICH_DIM } from "@/lib/labels";
import { PeekDrawer, confText, confTone, type PeekTarget } from "@/components/PeekDrawer";
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
  /* peek 抽屉：本地状态为准（响应即时），?peek= 进 URL 供刷新恢复 */
  const [peekId, setPeekId] = useState<string | null>(sp.get("peek"));

  /* URL → 抽屉状态同步（刷新恢复 / 地址栏直改） */
  const spPeek = sp.get("peek");
  useEffect(() => { setPeekId(spPeek); }, [spPeek]);

  /** searchParams 写回（保留 status 等其他参数，不滚屏） */
  const replaceParams = useCallback((mut: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(sp.toString());
    mut(p);
    const qs = p.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [sp, router, pathname]);

  const setTab = (v: Tab) => replaceParams((p) => {
    if (v === "needs_review") p.delete("status"); else p.set("status", v);
  });

  const openPeek = useCallback((id: string) => {
    setPeekId(id);
    replaceParams((p) => p.set("peek", id));
  }, [replaceParams]);

  const closePeek = useCallback(() => {
    setPeekId(null);
    replaceParams((p) => p.delete("peek"));
  }, [replaceParams]);

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

  const [undoInfo, setUndoInfo] = useState<{ id: string; title: string; action: string } | null>(null);
  const undoT = useRef<ReturnType<typeof setTimeout> | null>(null);

  function toast(text: string, undo?: { id: string; title: string; action: string }) {
    setMsg(text); setUndoInfo(undo ?? null);
    if (undoT.current) clearTimeout(undoT.current);
    undoT.current = setTimeout(() => { setMsg(""); setUndoInfo(null); }, undo ? 5000 : 2500);
  }

  /** 撤销上一次复核动作：undo 端点把条目送回待复核；reject 撤销时补一次重富化（清空过） */
  async function undoLast() {
    const u = undoInfo;
    if (!u) return;
    setUndoInfo(null); setMsg("");
    if (undoT.current) clearTimeout(undoT.current);
    try {
      const r = await fetch(`${API}/api/review/${encodeURIComponent(u.id)}/undo`, { method: "POST" });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      if (u.action === "reject") await api.enrich(u.id).catch(() => {});
      load();
      toast(`已撤销，回到待复核：${u.title.slice(0, 24)}`);
    } catch (e) {
      toast(`撤销失败：${e}`);
    }
  }

  async function act(it: PeekTarget, action: "confirm" | "reject") {
    setBusy(it.id + action);
    try {
      const r = await fetch(`${API}/api/review/${encodeURIComponent(it.id)}/${action}`, { method: "POST" });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const idx = items.findIndex((x) => x.id === it.id);
      // 操作成功后该条目状态已变更，从当前队列移除
      const rest = items.filter((x) => x.id !== it.id);
      setItems(rest);
      setCount((c) => Math.max(0, c - 1));
      const name = (it.title || it.id).slice(0, 30);
      toast(action === "confirm" ? `已确认入库：${name}` : `已回炉重富化：${name}`,
        { id: it.id, title: it.title || it.id, action });
      // 抽屉内复核 → 自动推进到下一条待办（原索引位已是后继）；队列清空则关抽屉
      if (peekId === it.id && idx >= 0) {
        if (rest.length === 0) closePeek();
        else openPeek(rest[Math.min(idx, rest.length - 1)].id);
      }
    } catch (e) {
      toast(`操作失败：${e}`);
    } finally {
      setBusy(null);
    }
  }

  async function reEnrich(it: PeekTarget) {
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

  const peekIdx = peekId ? items.findIndex((x) => x.id === peekId) : -1;

  return (
    <div>
      <PageHeader title="复核队列" desc="低置信/富化异常条目需人工确认；回炉后清空富化结果重新富化；点击行速览"
        right={<button className="btn" onClick={load}><RefreshCw size={12} strokeWidth={1.75} />刷新</button>} />

      {/* 状态 tabs — 下划线式，非药丸 */}
      <div className="flex h-10 items-stretch gap-5 border-b border-line">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)}
            className={`h-full border-b-2 text-[12px] transition-colors ${
              tab === v ? "border-accent font-medium text-fg" : "border-transparent text-faint hover:text-dim"}`}>
            {l}
            {tab === v && <span className="ml-1.5 font-mono text-[11px] text-faint">{count}</span>}
          </button>
        ))}
        <span className="ml-auto self-center text-[11px] text-faint">
          共 {count} 条
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
                  {/* 真 <Link> 保留 href 语义：⌘/Ctrl+click 开新标签；普通点击 → peek 抽屉 */}
                  <Link href={`/items/${it.id}`}
                    onClick={(e) => {
                      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                      e.preventDefault();
                      openPeek(it.id);
                    }}
                    className="stretched block truncate text-[13px] text-fg transition-colors hover:text-accent">
                    {it.title || it.id}
                  </Link>
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
                    <span className={`tnum font-mono text-[12px] ${confText(it.confidence)}`}>
                      {it.confidence != null ? `${Math.round(it.confidence * 100)}%` : "—"}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="flex max-w-[200px] flex-wrap gap-1">
                    {(it.weak_dims || []).length
                      ? it.weak_dims!.map((d) => (
                          <span key={d} className="badge">
                            <span className="dot" style={{ background: "var(--err)" }} />{zh(ENRICH_DIM, d)}
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
                    <button className="btn btn-sm btn-ghost" title="重新触发富化"
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

      {/* ── 右抽屉 peek：Chronicle/Elastic 式队列速览 ── */}
      <PeekDrawer
        id={peekId}
        index={peekIdx}
        total={items.length}
        title={peekIdx >= 0 ? items[peekIdx].title : undefined}
        busy={busy !== null}
        onClose={closePeek}
        onPrev={() => { if (peekIdx > 0) openPeek(items[peekIdx - 1].id); }}
        onNext={() => { if (peekIdx >= 0 && peekIdx < items.length - 1) openPeek(items[peekIdx + 1].id); }}
        onAct={act}
        onReEnrich={reEnrich}
      />

      {msg && (
        <div className="rise fixed bottom-5 right-5 z-[60] flex items-center gap-3 rounded-[8px] border border-line border-l-2 border-l-accent bg-panel px-4 py-2.5 text-[13px] text-fg">
          {msg}
          {undoInfo && (
            <button onClick={undoLast}
              className="font-mono text-[11px] uppercase tracking-[0.06em] text-accent hover:underline">
              撤销
            </button>
          )}
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
