"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getDigest, getPersonalized, getProfile, saveProfile, sendFeedback } from "@/lib/api";
import { SpecRow, SpecDot, Empty, Sev, St } from "@/components/ui";
import { Flame, Zap, ThumbsUp, ThumbsDown, Save, RefreshCw, Newspaper } from "lucide-react";

type Tag = { type: string; value: string };

const ASSET_TYPES = ["product", "vendor", "package", "cpe", "cve"];
const INTEREST_TYPES = ["layer", "owasp", "keyword", "technique"];
const SEV_FLOORS: [string, string][] = [
  ["", "不限严重度"], ["none", "none 及以上"], ["low", "low 及以上"],
  ["medium", "medium 及以上"], ["high", "high 及以上"], ["critical", "仅 critical"],
];

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
      <div className="flex gap-1.5">
        <select className="input w-[104px] shrink-0" value={t} onChange={(e) => setT(e.target.value)}>
          {types.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <input className="input min-w-0 flex-1" placeholder={placeholder} value={v}
          onChange={(e) => setV(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="btn shrink-0" onClick={add}>添加</button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((x, i) => (
          <span key={`${x.type}:${x.value}`} className="badge mono">
            <span className="text-faint">{x.type}:</span>{x.value}
            <button className="-mr-1 text-faint transition-colors hover:text-fg"
              onClick={() => onChange(tags.filter((_, j) => j !== i))}>×</button>
          </span>
        ))}
        {tags.length === 0 && <span className="text-[11px] text-faint">尚未定义</span>}
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
    <div>
      <SpecRow>
        <span>FIG_09</span><SpecDot />
        <span>PERSONALIZED FEED</span><SpecDot />
        <span>{feed.count || 0} HITS</span>
        {name && <><SpecDot /><span className="normal-case">{name}</span></>}
        <span className="ml-auto flex items-center gap-1.5 normal-case tracking-normal">
          <St tone={loading ? "live" : "dim"}>{loading ? "SYNC" : "IDLE"}</St>
        </span>
      </SpecRow>

      <div className="grid gap-x-8 gap-y-6 lg:grid-cols-[300px_1fr]">
        {/* ── 左栏：画像编辑 ── */}
        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="sect-title">我的画像</h2>
            <span className="font-mono text-[10.5px] text-faint">PUT /api/profile</span>
          </div>
          <div className="space-y-3">
            <div>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-faint">画像名</div>
              <div className="flex gap-1.5">
                <input className="input min-w-0 flex-1" placeholder="如 secops-01"
                  value={name} onChange={(e) => setName(e.target.value)} />
                <button className="btn shrink-0" title="重新拉取画像与推荐"
                  onClick={() => name.trim() && loadAll(name.trim())}>
                  <RefreshCw size={11} strokeWidth={1.75} />
                </button>
              </div>
            </div>
            <div>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-faint">严重度门槛</div>
              <select className="input w-full" value={floor} onChange={(e) => setFloor(e.target.value)}>
                {SEV_FLOORS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-faint">
                资产 · product/vendor/pkg/cpe/cve
              </div>
              <TagEditor types={ASSET_TYPES} tags={assets} onChange={setAssets}
                placeholder="vllm、ollama、nvidia…" />
            </div>
            <div>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-faint">
                关注 · layer/owasp/keyword/tech
              </div>
              <TagEditor types={INTEREST_TYPES} tags={interests} onChange={setInterests}
                placeholder="L3、LLM01、prompt injection…" />
            </div>
            <button className="btn btn-acc w-full" onClick={save}>
              <Save size={12} strokeWidth={1.75} />保存画像并推荐
            </button>
            {notice && <div className="text-[11.5px] text-accent">{notice}</div>}
          </div>

          {/* 晨报 */}
          {digest && digest.count > 0 && (
            <div className="panel mt-6">
              <div className="panel-h">
                <span className="t flex items-center gap-1.5">
                  <Newspaper size={11} strokeWidth={1.75} />MORNING DIGEST
                </span>
                <span className="mono text-[10px] text-faint">7d · {digest.count} hits</span>
              </div>
              <div className="panel-b">
                <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-dim">{digest.digest}</p>
              </div>
            </div>
          )}
        </div>

        {/* ── 主区：个性化流 ── */}
        <div className="min-w-0">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="sect-title">为你推荐</h2>
            <span className="font-mono text-[10.5px] text-faint">规则召回 ∪ 向量召回 · RRF · 画像加权</span>
          </div>
          {feed.items.length === 0 ? (
            <Empty text="暂无推荐"
              hint="先填写画像名与资产/关注标签，点击「保存画像并推荐」；已有画像可降低严重度门槛" />
          ) : (
            <div className="divide-y divide-[rgba(255,255,255,0.05)] border-t border-line">
              {feed.items.map((it: any) => (
                <div key={it.id} className="group py-3 transition-colors hover:bg-surface/60">
                  <div className="flex items-center gap-2.5 px-1">
                    <Sev level={it.severity} />
                    <Link href={`/items/${it.id}`}
                      className="min-w-0 flex-1 truncate text-[13px] text-fg transition-colors group-hover:text-accent">
                      {it.title_zh || it.title}
                    </Link>
                    {it.is_kev && (
                      <span className="badge mono !border-critical/40 !text-critical">
                        <Flame size={9} strokeWidth={2.5} />KEV
                      </span>
                    )}
                    {it.has_poc && (
                      <span className="badge mono"><Zap size={9} strokeWidth={2.5} />PoC</span>
                    )}
                    {it.ai_layer && <span className="badge mono">{it.ai_layer}</span>}
                    <span className="badge mono">{it.item_type}</span>
                    {(it.cve_ids || []).slice(0, 1).map((c: string) => (
                      <span key={c} className="badge mono">{c}</span>
                    ))}
                    {it.score != null && (
                      <span className="tnum shrink-0 font-mono text-[11px] text-accent" title="画像匹配分">
                        {Math.round(it.score * 100)}
                      </span>
                    )}
                  </div>
                  {it.why && (
                    <div className="mt-1.5 flex items-baseline gap-2 px-1">
                      <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-faint">why</span>
                      <span className="text-[11.5px] text-faint">{it.why}</span>
                    </div>
                  )}
                  {(it.matched_entities || []).length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1 px-1">
                      {it.matched_entities.map((m: Tag, i: number) => (
                        <span key={i} className="badge mono">{m.type}:{m.value}</span>
                      ))}
                    </div>
                  )}
                  <div className="mt-1.5 flex items-center gap-2 px-1 text-[11px] text-faint">
                    <span className="truncate">{(it.source_names || []).slice(0, 2).join(" · ")}</span>
                    {it.published_at && <span className="num">{it.published_at.slice(0, 10)}</span>}
                    <span className="ml-auto flex shrink-0 gap-1">
                      {voted[it.id] ? (
                        <span className="badge mono !border-ok/40 !text-ok">已标记有用</span>
                      ) : (
                        <>
                          <button className="btn btn-sm btn-ghost" title="有用 → 画像正权重"
                            onClick={() => fb(it.id, "useful")}>
                            <ThumbsUp size={11} strokeWidth={1.75} />有用
                          </button>
                          <button className="btn btn-sm btn-ghost" title="不感兴趣 → 降权并剔除"
                            onClick={() => fb(it.id, "mute")}>
                            <ThumbsDown size={11} strokeWidth={1.75} />不感兴趣
                          </button>
                        </>
                      )}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
