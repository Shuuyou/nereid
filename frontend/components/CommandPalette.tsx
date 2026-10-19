"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, CornerDownLeft, LayoutGrid, List, MessagesSquare, BookOpen, Workflow, Compass, FileText, Crosshair, Database, HeartPulse, Zap, FilePlus2, Hash, CircleHelp, Terminal, Keyboard } from "lucide-react";
import { api } from "@/lib/api";

type Cmd = { id: string; label: string; hint?: string; icon: any; run: () => void };

const NAV: [string, string, any][] = [
  ["/", "今日值班台", LayoutGrid],
  ["/review", "待复核队列", List],
  ["/qa", "深度调查", MessagesSquare],
  ["/items", "情报检索", BookOpen],
  ["/graph", "知识图谱", Compass],
  ["/reports", "报告", FileText],
  ["/for-you", "关注需求", Crosshair],
  ["/sources", "数据源", Database],
  ["/pipeline", "流水线", Workflow],
];

/** ? 帮助：面板键位 + 复核抽屉（PeekDrawer）键盘流 */
const HELP: [string, string][] = [
  ["⌘K", "开关命令面板"],
  ["↑ ↓", "移动选择 · ↵ 执行 · esc 关闭"],
  [">", "动作命令前缀（如：> 采集所有源）"],
  ["#", "按 ID 直跳条目（如：#CVE-2025-…）"],
  ["?", "显示本帮助"],
  ["j / k", "复核抽屉：上一条 / 下一条"],
  ["c", "复核抽屉：确认入库"],
  ["r", "复核抽屉：回炉重富化"],
  ["e", "复核抽屉：重新富化"],
];

/** 顶栏触发钮（client 组件，供 server layout 直接嵌入） */
export function PaletteButton() {
  return (
    <button
      onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
      className="flex h-7 items-center gap-2 rounded-[8px] border border-line bg-paper px-2.5 font-mono text-[12px] text-faint transition-colors hover:border-line2 hover:text-dim"
      title="全局搜索 (⌘K)">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
      <span>搜索</span>
      <kbd className="rounded-[3px] border border-line bg-surface px-1 font-mono text-[10px]">⌘K</kbd>
    </button>
  );
}

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<any[]>([]);
  const [sel, setSel] = useState(0);
  const [msg, setMsg] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const msgTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** 底部 toast（面板关闭后仍可见，与 review 页同款样式） */
  const toast = useCallback((t: string) => {
    setMsg(t);
    if (msgTimer.current) clearTimeout(msgTimer.current);
    msgTimer.current = setTimeout(() => setMsg(""), 3200);
  }, []);
  useEffect(() => () => { if (msgTimer.current) clearTimeout(msgTimer.current); }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => { if (open) { setQ(""); setSel(0); setHits([]); setTimeout(() => inputRef.current?.focus(), 10); } }, [open]);

  /** 输入前缀决定模式：> 动作命令 / # 条目直达 / ? 帮助 / 其余 = 导航+检索 */
  const lead = q.trimStart();
  const mode: "cmd" | "item" | "help" | "nav" =
    lead.startsWith(">") ? "cmd" : lead.startsWith("#") ? "item" : lead.startsWith("?") ? "help" : "nav";

  // 输入 → 检索情报（防抖；前缀模式下不触发）
  useEffect(() => {
    const t = setTimeout(() => {
      const v = q.trim();
      if (v.length >= 2 && !/^[>#?]/.test(v)) {
        api.items({ q: v, size: 5, ai_only: true })
          .then((d) => setHits(d.items || [])).catch(() => setHits([]));
      } else setHits([]);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  /** > 动作命令表（keys 供英文/拼音模糊匹配） */
  const ACTIONS = useMemo(() => [
    { keys: ["collect", "run", "all", "caiji"], label: "采集所有源", hint: "触发 41 个采集器", icon: Zap,
      run: () => { setOpen(false); api.runAll().then(() => toast("已触发全源采集")).catch((e) => toast(`采集触发失败：${e}`)); } },
    { keys: ["report", "daily", "ribao"], label: "生成日报", hint: "LLM 聚合近 24h · 约 10-20s", icon: FilePlus2,
      run: () => { setOpen(false); api.dailyReport().then(() => { toast("日报生成中，完成后见报告页"); router.push("/reports"); }).catch((e) => toast(`日报生成失败：${e}`)); } },
    { keys: ["qa", "ask", "diaocha"], label: "新建调查", hint: "/qa", icon: MessagesSquare,
      run: () => { setOpen(false); router.push("/qa"); } },
    { keys: ["review", "fuhe"], label: "复核队列", hint: "/review", icon: List,
      run: () => { setOpen(false); router.push("/review"); } },
    { keys: ["health", "zijian"], label: "系统自检", hint: "后端连通性探测", icon: HeartPulse,
      run: () => { setOpen(false); api.health().then(() => toast("后端服务正常")).catch((e) => toast(`后端不可达：${e}`)); } },
    { keys: ["sources", "source", "shujuyuan"], label: "管理数据源", hint: "/sources", icon: Database,
      run: () => { setOpen(false); router.push("/sources"); } },
    { keys: ["pipeline", "dag", "liushuixian"], label: "流水线 DAG", hint: "/pipeline", icon: Workflow,
      run: () => { setOpen(false); router.push("/pipeline"); } },
  ], [router, toast]);

  const cmds: Cmd[] = useMemo(() => {
    if (mode === "cmd") {
      const kw = lead.slice(1).trim().toLowerCase();
      return ACTIONS
        .filter((a) => !kw || a.label.toLowerCase().includes(kw)
          || a.keys.some((k) => k.includes(kw))
          || kw.split("").every((c) => a.label.includes(c)))
        .map((a) => ({ id: `act-${a.label}`, label: a.label, hint: a.hint, icon: a.icon, run: a.run }));
    }
    if (mode === "item") {
      const id = lead.slice(1).trim();
      if (!id) return [{ id: "item-hint", label: "继续输入条目 ID…", hint: "#CVE-… / 内部 ID", icon: Hash, run: () => {} }];
      return [{
        id: `jump-${id}`, label: `跳转条目 #${id}`, hint: `/items/${id}`, icon: Hash,
        run: () => {
          api.item(id)
            .then(() => { setOpen(false); router.push(`/items/${encodeURIComponent(id)}`); })
            .catch(() => toast(`条目不存在：#${id}`));
        },
      }];
    }
    if (mode === "help") {
      return HELP.map(([k, d]) => ({ id: `help-${k}`, label: d, hint: k, icon: Keyboard, run: () => {} }));
    }
    const kw = q.trim().toLowerCase();
    const nav = NAV
      .filter(([, l]) => !kw || l.toLowerCase().includes(kw) || kw.split("").every((c) => l.toLowerCase().includes(c)))
      .map(([href, label, icon]) => ({
        id: `nav-${href}`, label, hint: href, icon,
        run: () => { setOpen(false); router.push(href); },
      }));
    const items = hits.map((it: any) => ({
      id: `item-${it.id}`, label: it.title_zh || it.title,
      hint: (it.cve_ids || [])[0] || it.item_type || "", icon: BookOpen,
      run: () => { setOpen(false); router.push(`/items/${it.id}`); },
    }));
    return kw ? [...items, ...nav] : nav;
  }, [q, hits, router, mode, lead, ACTIONS, toast]);

  useEffect(() => { setSel(0); }, [cmds.length, mode]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-idx="${sel}"]`)?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(cmds.length - 1, s + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === "Enter" && cmds[sel]) { e.preventDefault(); cmds[sel].run(); }
  };

  const ModeIcon = mode === "cmd" ? Terminal : mode === "item" ? Hash : mode === "help" ? CircleHelp : Search;
  const section = mode === "cmd" ? "动作命令" : mode === "item" ? "条目直达" : mode === "help" ? "快捷键"
    : (q.trim().length >= 2 && hits.length > 0 ? "情报" : "");

  return (
    <>
      {msg && (
        <div className="rise fixed bottom-5 right-5 z-[120] rounded-[8px] border border-line border-l-2 border-l-accent bg-panel px-4 py-2.5 text-[13px] text-fg">
          {msg}
        </div>
      )}
      {open && (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[14vh]"
      onClick={() => setOpen(false)}
      style={{ animation: "fadeIn 150ms ease-out" }}>
      <div className="absolute inset-0 bg-ink/30" />
      <div className="relative w-[560px] overflow-hidden rounded-nest border border-line bg-paper shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        style={{ animation: "riseIn 200ms cubic-bezier(0.23,1,0.32,1)" }}>
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <ModeIcon size={14} strokeWidth={2} className="shrink-0 text-faint" />
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKey} placeholder="检索情报 / 跳转页面 · > 命令 · #ID · ? 帮助"
            className="h-11 flex-1 bg-transparent text-[13px] text-fg outline-none placeholder:text-faint" />
          <kbd className="rounded-[4px] border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-faint">ESC</kbd>
        </div>
        <div ref={listRef} className="max-h-[46vh] overflow-y-auto p-1.5">
          {cmds.length === 0 && (
            <div className="px-3 py-8 text-center text-[12px] text-faint">{mode === "cmd" ? "无匹配命令" : "无匹配结果"}</div>
          )}
          {section && (
            <div className="px-2.5 pb-1 pt-1.5 font-mono text-[11px] uppercase tracking-[0.08em] text-faint">{section}</div>
          )}
          {cmds.map((c, i) => (
            <button key={c.id} data-idx={i} onClick={c.run}
              onMouseEnter={() => setSel(i)}
              className={`flex w-full items-center gap-2.5 rounded-[8px] px-2.5 py-2 text-left transition-colors ${
                i === sel ? "bg-surface2" : ""}`}>
              <c.icon size={13} strokeWidth={2} className="shrink-0 text-faint" />
              <span className="min-w-0 flex-1 truncate text-[13px] text-fg">{c.label}</span>
              {c.hint && <span className="shrink-0 font-mono text-[11px] text-faint">{c.hint}</span>}
              {i === sel && <CornerDownLeft size={11} className="shrink-0 text-faint" />}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 border-t border-line px-4 py-2 font-mono text-[11px] text-faint">
          <span>↑↓ 移动</span><span>↵ 打开</span><span>esc 关闭</span>
          <span className="ml-auto">&gt; 命令 · # 条目 · ? 帮助</span>
        </div>
      </div>
    </div>
      )}
    </>
  );
}
