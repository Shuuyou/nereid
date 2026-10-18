"use client";
import { useCallback, useEffect, useState } from "react";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { ItemCard } from "@/components/cards";
import { Skeleton, Empty, PageHeader } from "@/components/ui";

const LAYERS = ["", "L1", "L2", "L3", "L4", "L5", "L6"];
const SEV = ["", "critical", "high", "medium", "low"];
const TYPES = ["", "vuln", "advisory", "exploit", "article", "paper", "incident", "policy"];

export default function ItemsPage() {
  const [data, setData] = useState<any>({ items: [], total: 0 });
  const [f, setF] = useState({ q: "", layer: "", severity: "", item_type: "", kev: false, poc: false, ai_only: true, page: 1 });
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api.items({ size: 20, sort: "priority", ...f })
      .then(setData).catch(() => setData({ items: [], total: 0 }))
      .finally(() => setLoading(false));
  }, [f]);
  useEffect(load, [load]);

  const pages = Math.max(1, Math.ceil((data.total || 0) / 20));

  return (
    <div className="space-y-4">
      <PageHeader title="情报库" desc={`${(data.total || 0).toLocaleString()} 条 · 按优先级排序`}
        right={
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <input className="input w-64 !pl-8" placeholder="搜索标题/CVE/产品…"
              value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} />
          </div>
        } />

      <div className="card flex flex-wrap items-center gap-2 !p-3">
        <select className="input" value={f.layer} onChange={(e) => setF({ ...f, layer: e.target.value, page: 1 })}>
          {LAYERS.map((l) => <option key={l} value={l}>{l || "全部层级"}</option>)}
        </select>
        <select className="input" value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value, page: 1 })}>
          {SEV.map((s) => <option key={s} value={s}>{s || "全部严重级"}</option>)}
        </select>
        <select className="input" value={f.item_type} onChange={(e) => setF({ ...f, item_type: e.target.value, page: 1 })}>
          {TYPES.map((t) => <option key={t} value={t}>{t || "全部类型"}</option>)}
        </select>
        <div className="mx-1 h-4 w-px bg-line" />
        {([["kev", "仅 KEV"], ["poc", "仅 PoC"], ["ai_only", "AI 相关"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setF({ ...f, [k]: !f[k], page: 1 })}
            className={`rounded-md border px-2.5 py-1 text-[12px] transition-colors ${
              f[k] ? "border-accent/40 bg-accent/[0.12] text-accent" : "border-line text-dim hover:border-linestrong hover:text-fg"}`}>
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-[104px]" />)}
        </div>
      ) : data.items.length === 0 ? (
        <Empty text="没有匹配的情报" hint="试试放宽筛选条件或关闭「AI 相关」" />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.items.map((it: any) => <ItemCard key={it.id} item={it} />)}
        </div>
      )}

      <div className="flex items-center justify-center gap-2 text-[12px]">
        <button className="btn-ghost !py-1.5" disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })}>
          <ChevronLeft size={13} />上一页
        </button>
        <span className="mono px-2 text-faint">{f.page} / {pages}</span>
        <button className="btn-ghost !py-1.5" disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })}>
          下一页<ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}
