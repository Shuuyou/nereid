"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ItemCard } from "@/components/cards";

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
  const sel = "rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-fg";

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" placeholder="搜索标题/CVE/产品…"
          value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} />
        <select className={sel} value={f.layer} onChange={(e) => setF({ ...f, layer: e.target.value, page: 1 })}>
          {LAYERS.map((l) => <option key={l} value={l}>{l || "全部层级"}</option>)}
        </select>
        <select className={sel} value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value, page: 1 })}>
          {SEV.map((s) => <option key={s} value={s}>{s || "全部严重级"}</option>)}
        </select>
        <select className={sel} value={f.item_type} onChange={(e) => setF({ ...f, item_type: e.target.value, page: 1 })}>
          {TYPES.map((t) => <option key={t} value={t}>{t || "全部类型"}</option>)}
        </select>
        {([["kev", "仅 KEV"], ["poc", "仅 PoC"], ["ai_only", "AI 相关"]] as const).map(([k, label]) => (
          <label key={k} className="flex cursor-pointer items-center gap-1.5 text-sm text-dim">
            <input type="checkbox" checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked, page: 1 })}
              className="accent-cyan-400" />{label}
          </label>
        ))}
        <span className="ml-auto text-sm text-dim">共 {data.total} 条</span>
      </div>

      {loading ? <div className="text-dim">加载中…</div> : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.items.map((it: any) => <ItemCard key={it.id} item={it} />)}
        </div>
      )}

      <div className="flex items-center justify-center gap-3 text-sm">
        <button className="btn-ghost" disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })}>← 上一页</button>
        <span className="text-dim">{f.page} / {pages}</span>
        <button className="btn-ghost" disabled={f.page >= pages} onClick={() => setF({ ...f, page: f.page + 1 })}>下一页 →</button>
      </div>
    </div>
  );
}
