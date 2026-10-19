"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { Empty, SpecRow, SpecDot, Sev } from "@/components/ui";
import { PeekDrawer } from "@/components/PeekDrawer";

const LAYERS = ["", "L1", "L2", "L3", "L4", "L5", "L6"];
const LAYER_NAMES: Record<string, string> = {
  L1: "L1 基础设施", L2: "L2 模型数据", L3: "L3 应用智能体",
  L4: "L4 供应链", L5: "L5 政策治理", L6: "L6 滥用威胁",
};
const SEV: [string, string][] = [
  ["", "严重级"], ["critical", "严重"], ["high", "高危"], ["medium", "中危"], ["low", "低危"],
];
const TYPES: [string, string][] = [
  ["", "类型"], ["vuln", "vuln"], ["advisory", "advisory"], ["exploit", "exploit"],
  ["article", "article"], ["paper", "paper"], ["incident", "incident"], ["policy", "policy"],
];
const SORTS: [string, string][] = [
  ["priority", "优先级"], ["published", "披露时间"], ["seen", "入库时间"],
];
const PAGE_SIZE = 20;

type Filters = {
  q: string; layer: string; severity: string; item_type: string;
  kev: boolean; poc: boolean; ai_only: boolean; page: number; sort: string;
};

function filtersFromParams(sp: URLSearchParams): Filters {
  return {
    q: sp.get("q") || "",
    layer: sp.get("layer") || "",
    severity: sp.get("severity") || "",
    item_type: sp.get("item_type") || "",
    kev: sp.get("kev") === "1",
    poc: sp.get("poc") === "1",
    ai_only: sp.get("ai_only") !== "0",
    page: Math.max(1, parseInt(sp.get("page") || "1", 10) || 1),
    sort: sp.get("sort") || "priority",
  };
}

function paramsFromFilters(f: Filters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.layer) p.set("layer", f.layer);
  if (f.severity) p.set("severity", f.severity);
  if (f.item_type) p.set("item_type", f.item_type);
  if (f.kev) p.set("kev", "1");
  if (f.poc) p.set("poc", "1");
  if (!f.ai_only) p.set("ai_only", "0");
  if (f.page > 1) p.set("page", String(f.page));
  if (f.sort !== "priority") p.set("sort", f.sort);
  return p;
}

function ItemsInner() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [data, setData] = useState<any>({ items: [], total: 0 });
  const [q, setQ] = useState(() => sp.get("q") || "");
  const [f, setF] = useState<Filters>(() => filtersFromParams(sp));
  const [loading, setLoading] = useState(true);
  const [peekId, setPeekId] = useState<string | null>(() => sp.get("peek"));

  /** 抽屉开关：?peek= 进 URL（刷新可恢复、可分享），保留其余筛选参数 */
  const setPeek = useCallback((id: string | null) => {
    setPeekId(id);
    const p = new URLSearchParams(sp.toString());
    if (id) p.set("peek", id); else p.delete("peek");
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp, router, pathname]);

  // 查询词防抖 → 写入过滤器
  useEffect(() => {
    const t = setTimeout(() => setF((s) => ({ ...s, q: q.trim(), page: 1 })), 320);
    return () => clearTimeout(t);
  }, [q]);

  // 过滤器 → URL（可分享/后退不丢）
  useEffect(() => {
    const qs = paramsFromFilters(f).toString();
    const cur = sp.toString();
    if (qs !== cur) router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f]);

  const load = useCallback(() => {
    setLoading(true);
    const params: Record<string, string | number | boolean> = { size: PAGE_SIZE, ...f };
    // 输入恰为 CVE-ID 时走专用等值过滤（cve_ids 数组 contains），其余走 ilike
    if (/^CVE-\d{4}-\d{4,}$/i.test(f.q)) { params.cve = f.q.toUpperCase(); params.q = ""; }
    api.items(params)
      .then(setData).catch(() => setData({ items: [], total: 0 }))
      .finally(() => setLoading(false));
  }, [f]);
  useEffect(load, [load]);

  const total = data.total || 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const range = total === 0 ? "0" : `${(f.page - 1) * PAGE_SIZE + 1}–${Math.min(f.page * PAGE_SIZE, total)}`;
  const clearFilters = () => {
    setQ("");
    setF({ q: "", layer: "", severity: "", item_type: "", kev: false, poc: false, ai_only: true, page: 1, sort: "priority" });
  };

  return (
    <div>
      <SpecRow>
        <span>FIG_02</span><SpecDot />
        <span>INTEL LIBRARY</span><SpecDot />
        <span>{total.toLocaleString()} ITEMS</span>
      </SpecRow>

      {/* 查询条：全宽 mono（Shodan/Elastic 式） */}
      <div className="relative mt-4">
        <Search size={14} strokeWidth={1.75}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <input
          className="input h-9 w-full !pl-9 font-mono text-[13px]"
          placeholder="筛选: CVE-ID / 关键词 / 类型…"
          value={q} onChange={(e) => setQ(e.target.value)}
          spellCheck={false}
        />
      </div>

      {/* facet 行：下拉 + 开关 chips（无侧栏） */}
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <select className="input w-auto" value={f.layer}
          onChange={(e) => setF({ ...f, layer: e.target.value, page: 1 })}>
          {LAYERS.map((l) => <option key={l} value={l}>{l ? LAYER_NAMES[l] : "AI 层"}</option>)}
        </select>
        <select className="input w-auto" value={f.severity}
          onChange={(e) => setF({ ...f, severity: e.target.value, page: 1 })}>
          {SEV.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select className="input w-auto font-mono" value={f.item_type}
          onChange={(e) => setF({ ...f, item_type: e.target.value, page: 1 })}>
          {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <div className="mx-1 h-4 w-px bg-line2" />
        {([["kev", "KEV"], ["poc", "PoC"], ["ai_only", "AI 相关"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setF({ ...f, [k]: !f[k], page: 1 })}
            className={`h-6 rounded-[5px] border px-2.5 text-[12px] transition-colors ${
              f[k]
                ? "border-accent/50 bg-[rgba(21,122,119,0.1)] text-accent"
                : "border-line text-faint hover:border-line2 hover:text-dim"}`}>
            {label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-faint">sort</span>
          <select className="input w-auto" value={f.sort}
            onChange={(e) => setF({ ...f, sort: e.target.value, page: 1 })}>
            {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      {/* 高密度数据表（行=stretched-link 真锚，支持 Cmd+click 新标签） */}
      <div className="mt-3 overflow-x-auto">
        <table className="dt table-fixed">
          <thead>
            <tr>
              <th className="w-[84px]">级别</th>
              <th>标题</th>
              <th className="w-[148px]">CVE</th>
              <th className="w-[92px]">类型</th>
              <th className="r w-[72px]">EPSS</th>
              <th className="w-[150px]">来源</th>
              <th className="w-[100px]">披露</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <tr key={i}><td colSpan={7}><div className="skel h-5" /></td></tr>
              ))
            ) : data.items.length === 0 ? (
              <tr><td colSpan={7} className="!border-0 !p-0">
                <div className="py-4">
                  <Empty text="没有匹配的情报"
                    hint="试试放宽筛选条件或关闭「AI 相关」" />
                </div>
                <div className="-mt-2 flex justify-center pb-2">
                  <button className="btn btn-sm" onClick={clearFilters}>清除全部筛选</button>
                </div>
              </td></tr>
            ) : data.items.map((it: any, ri: number) => (
              <tr key={it.id} className="rowlink cursor-pointer" onClick={() => setPeek(it.id)}
                title="点击行速览">
                <td><Sev level={it.severity} /></td>
                <td>
                  <div className="flex items-center gap-2">
                    <Link href={`/items/${it.id}`}
                      className="min-w-0 truncate text-fg/90 transition-colors hover:text-accent"
                      onClick={(e) => e.stopPropagation()}
                      title={`${it.title_zh ? `${it.title_zh}\n` : ""}整页详情（Cmd+点击新标签）`}>
                      {it.title_zh || it.title}
                    </Link>
                    {it.is_kev && (
                      <span className="badge z-act shrink-0">
                        <span className="dot" style={{ background: "#d92638" }} />KEV
                      </span>
                    )}
                    {it.has_poc && (
                      <span className="badge z-act shrink-0">
                        <span className="dot" style={{ background: "#b07c00" }} />PoC
                      </span>
                    )}
                  </div>
                </td>
                <td className="num truncate text-dim">
                  {(it.cve_ids || []).length
                    ? <>{it.cve_ids[0]}{it.cve_ids.length > 1 && <span className="text-faint"> +{it.cve_ids.length - 1}</span>}</>
                    : "—"}
                </td>
                <td><span className="badge mono">{it.item_type || "—"}</span></td>
                <td className="r num text-dim">
                  {it.epss_score != null ? `${(it.epss_score * 100).toFixed(1)}%` : "—"}
                </td>
                <td className="truncate text-dim">
                  {(it.source_names || []).slice(0, 2).join(" · ")}
                  {(it.source_names || []).length > 2 && (
                    <span className="text-faint"> +{it.source_names.length - 2}</span>
                  )}
                  {!it.source_names?.length && "—"}
                </td>
                <td className="num text-faint">{it.published_at ? it.published_at.slice(0, 10) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 分页：mono 小字 */}
      <div className="mt-3 flex items-center justify-between font-mono text-[11px] uppercase tracking-[0.06em] text-faint">
        <span>{range} / {total.toLocaleString()}</span>
        <div className="flex items-center gap-1">
          <button className="btn btn-ghost btn-sm" disabled={f.page <= 1}
            onClick={() => setF({ ...f, page: f.page - 1 })}>
            <ChevronLeft size={12} />Prev
          </button>
          <span className="px-2 tnum">P{f.page} / {pages}</span>
          <button className="btn btn-ghost btn-sm" disabled={f.page >= pages}
            onClick={() => setF({ ...f, page: f.page + 1 })}>
            Next<ChevronRight size={12} />
          </button>
        </div>
      </div>

      {/* 行点击速览抽屉（只读模式：无复核动作）；j/k 翻页、Esc 关 */}
      {(() => {
        const items = data.items || [];
        const idx = items.findIndex((i: any) => i.id === peekId);
        const row = idx >= 0 ? items[idx] : null;
        return (
          <PeekDrawer
            readonly
            id={peekId}
            index={idx}
            total={items.length}
            title={row ? row.title_zh || row.title : undefined}
            onClose={() => setPeek(null)}
            onPrev={() => idx > 0 && setPeek(items[idx - 1].id)}
            onNext={() => idx >= 0 && idx < items.length - 1 && setPeek(items[idx + 1].id)}
          />
        );
      })()}
    </div>
  );
}

export default function ItemsPage() {
  return (
    <Suspense>
      <ItemsInner />
    </Suspense>
  );
}
