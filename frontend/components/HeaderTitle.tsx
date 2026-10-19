"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

/** 各路由的默认顶栏标题（无会话态时兜底） */
const ROUTE_TITLE: [RegExp, string][] = [
  [/^\/qa/, "调查"],
  [/^\/review/, "复核队列"],
  [/^\/items\/[^/]+/, "情报详情"],
  [/^\/items/, "情报检索"],
  [/^\/graph/, "知识图谱"],
  [/^\/reports/, "报告"],
  [/^\/pipeline/, "流水线"],
  [/^\/sources/, "数据源"],
  [/^\/for-you/, "关注需求"],
  [/^\/$/, "今日值班台"],
];

/** 顶栏动态标题：QA 页通过 `nereid:title` CustomEvent 上报当前调查标题 */
export function HeaderTitle() {
  const pathname = usePathname() || "/";
  const [custom, setCustom] = useState<string | null>(null);

  useEffect(() => {
    const on = (e: Event) => setCustom((e as CustomEvent<string | null>).detail ?? null);
    window.addEventListener("nereid:title", on);
    return () => window.removeEventListener("nereid:title", on);
  }, []);

  // 路由切换时丢掉上一页的标题
  useEffect(() => { setCustom(null); }, [pathname]);

  const base = ROUTE_TITLE.find(([re]) => re.test(pathname))?.[1] || "捞针";
  const title = pathname.startsWith("/qa") && custom ? custom : base;
  return (
    <span className="truncate text-[13px] font-medium text-dim" title={title}>
      {title}
    </span>
  );
}
