"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getDigest, getPersonalized, getProfile, saveProfile, sendFeedback } from "@/lib/api";
import { LayerTag, SevBadge } from "@/components/cards";

type Tag = { type: string; value: string };

const ASSET_TYPES = ["product", "vendor", "package", "cpe", "cve"];
const INTEREST_TYPES = ["layer", "owasp", "keyword", "technique"];
const SEV_FLOORS: [string, string][] = [
  ["", "不限严重度"], ["none", "none 及以上"], ["low", "low 及以上"],
  ["medium", "medium 及以上"], ["high", "high 及以上"], ["critical", "仅 critical"],
];

const sel = "rounded-lg border border-border bg-bg px-2 py-1.5 text-sm text-fg";

function TagEditor({ types, tags, onChange, placeholder }: {
  types: string[]; tags: Tag[]; onChange: (t: Tag[]) => void; placeholder: string;
}) {
  const [t, setT] = useState(types[0]);
  const [v, setV] = useState("");
  const add = () => {
    const value = v.trim();
    if (!value) return;
    if (!tags.some((x) => x.type === t && x.value === value)) onChange([...tags, { type: t, value }]);
    setV("");
  };
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <select className={sel} value={t} onChange={(e) => setT(e.target.value)}>
          {types.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <input className="input" placeholder={placeholder} value={v}
          onChange={(e) => setV(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="btn shrink-0" onClick={add}>添加</button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((x, i) => (
          <span key={`${x.type}:${x.value}`} className="tag-accent inline-flex items-center gap-1">
            <span className="text-dim">{x.type}:</span>{x.value}
            <button className="text-dim hover:text-fg"
              onClick={() => onChange(tags.filter((_, j) => j !== i))}>×</button>
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ForYouPage() {
  const [name, setName] = useState("");
  const [assets, setAssets] = useState<Tag[]>([]);
  const [interests, setInterests] = useState<Tag[]>([]);
  const [floor, setFloor] = useState("low");
  const [feed, setFeed] = useState<any>({ count: 0, items: [] });
  const [digest, setDigest] = useState<any>(null);
  const [voted, setVoted] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");

  const loadAll = useCallback((n: string) => {
    if (!n) return;
    setLoading(true);
    getProfile(n)
      .then((p) => {
        const pf = p.profile || {};
        setAssets(pf.assets || []); setInterests(pf.interests || []);
        setFloor(pf.severity_floor ?? "low");
      })
      .catch(() => { /* 画像未建：保留当前编辑态 */ });
    getPersonalized(n, 7).then(setFeed).catch(() => setFeed({ count: 0, items: [] }));
    getDigest(n, 7).then(setDigest).catch(() => setDigest(null));
    setLoading(false);
  }, []);

  useEffect(() => {
    const n = localStorage.getItem("foryou_name") || "";
    setName(n);
    if (n) loadAll(n);
  }, [loadAll]);

  const save = async () => {
    if (!name.trim()) { setNotice("请先填写画像名"); return; }
    localStorage.setItem("foryou_name", name.trim());
    try {
      await saveProfile(name.trim(), {
        assets, interests, severity_floor: floor, channels: ["sse", "daily"],
      });
      setNotice("画像已保存，正在刷新推荐…");
      loadAll(name.trim());
      setTimeout(() => setNotice(""), 3000);
    } catch { setNotice("保存失败：后端不可达或参数错误"); }
  };

  const fb = async (itemId: string, signal: string) => {
    try {
      await sendFeedback(name.trim(), itemId, signal);
      if (signal === "mute") {
        setFeed((f: any) => ({ count: f.count, items: f.items.filter((x: any) => x.id !== itemId) }));
      } else {
        setVoted((m) => ({ ...m, [itemId]: signal }));
      }
    } catch { setNotice("反馈提交失败"); }
  };

  return (
    <div className="space-y-4">
      {/* 画像编辑器 */}
      <div className="card space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold">我的画像</h2>
          <input className="input max-w-56" placeholder="画像名（如 secops-01）"
            value={name} onChange={(e) => setName(e.target.value)} />
          <select className={sel} value={floor} onChange={(e) => setFloor(e.target.value)}>
            {SEV_FLOORS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button className="btn" onClick={save}>保存画像并推荐</button>
          <button className="btn-ghost" onClick={() => name.trim() && loadAll(name.trim())}>刷新</button>
          {notice && <span className="text-xs text-accent">{notice}</span>}
          {loading && <span className="text-xs text-dim">加载中…</span>}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="mb-1 text-xs text-dim">资产（product/vendor/package/cpe/cve）</div>
            <TagEditor types={ASSET_TYPES} tags={assets} onChange={setAssets}
              placeholder="如 vllm、ollama、nvidia…" />
          </div>
          <div>
            <div className="mb-1 text-xs text-dim">关注（layer/owasp/keyword/technique）</div>
            <TagEditor types={INTEREST_TYPES} tags={interests} onChange={setInterests}
              placeholder="如 L3、LLM01、prompt injection、AML.T0051…" />
          </div>
        </div>
      </div>

      {/* 个性化晨报 */}
      {digest && (
        <div className="card border-accent/30">
          <div className="mb-1 text-xs font-semibold text-accent">个性化晨报 · 近 7 天命中 {digest.count} 条</div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg/90">{digest.digest}</p>
        </div>
      )}

      {/* 推荐列表 */}
      <div className="flex items-center gap-2 text-sm text-dim">
        <span>为你推荐 {feed.count} 条</span>
        <span className="text-xs">（规则召回 ∪ 向量召回，按画像匹配度排序）</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {feed.items.map((it: any) => (
          <div key={it.id} className="card hover:border-accent/50 transition-colors">
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              <SevBadge s={it.severity} />
              {it.is_kev && <span className="tag-kev">KEV</span>}
              {it.has_poc && <span className="tag-accent">PoC</span>}
              <LayerTag l={it.ai_layer} />
              <span className="tag">{it.item_type}</span>
              {(it.cve_ids || []).slice(0, 2).map((c: string) => <span key={c} className="tag mono">{c}</span>)}
              {it.score != null && <span className="ml-auto text-xs text-accent">{Math.round(it.score * 100)}分</span>}
            </div>
            <Link href={`/items/${it.id}`} className="line-clamp-2 text-sm font-medium leading-snug hover:text-accent">
              {it.title_zh || it.title}
            </Link>
            <div className="mt-2 rounded-lg border border-accent/20 bg-accent/5 px-2 py-1.5 text-xs text-accent">
              为什么推荐：{it.why}
            </div>
            {(it.matched_entities || []).length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {it.matched_entities.map((m: Tag, i: number) => (
                  <span key={i} className="tag">{m.type}:{m.value}</span>
                ))}
              </div>
            )}
            <div className="mt-2 flex items-center gap-2 text-xs text-dim">
              <span className="truncate">{(it.source_names || []).slice(0, 2).join(" · ")}</span>
              {it.published_at && <span>{it.published_at.slice(0, 10)}</span>}
              <span className="ml-auto flex gap-1.5">
                {voted[it.id] ? (
                  <span className="tag-accent">已标记有用</span>
                ) : (
                  <>
                    <button className="btn-ghost px-2 py-1" onClick={() => fb(it.id, "useful")}>有用</button>
                    <button className="btn-ghost px-2 py-1" onClick={() => fb(it.id, "mute")}>不感兴趣</button>
                  </>
                )}
              </span>
            </div>
          </div>
        ))}
      </div>
      {!loading && feed.count === 0 && (
        <div className="card text-sm text-dim">
          暂无推荐。先填写画像名与资产/关注标签，点击「保存画像并推荐」；
          若已有画像，可降低严重度下限或扩大关注范围。
        </div>
      )}
    </div>
  );
}
