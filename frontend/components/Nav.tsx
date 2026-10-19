"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Sun, MessageSquareText, Inbox, Layers, Share2,
  FileText, SlidersHorizontal, Radio, GitBranch,
} from "lucide-react";

const GROUPS: { label: string; items: { href: string; label: string; icon: any }[] }[] = [
  {
    label: "研判",
    items: [
      { href: "/", label: "今日值班台", icon: Sun },
      { href: "/review", label: "情报队列", icon: Inbox },
      { href: "/qa", label: "调查", icon: MessageSquareText },
    ],
  },
  {
    label: "知识",
    items: [
      { href: "/items", label: "情报检索", icon: Layers },
      { href: "/graph", label: "知识图谱", icon: Share2 },
      { href: "/reports", label: "报告", icon: FileText },
    ],
  },
  {
    label: "配置",
    items: [
      { href: "/for-you", label: "关注需求", icon: SlidersHorizontal },
      { href: "/sources", label: "数据源", icon: Radio },
      { href: "/pipeline", label: "流水线", icon: GitBranch },
    ],
  },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-5 px-2.5 pt-3" aria-label="主导航">
      {GROUPS.map((g) => (
        <div key={g.label}>
          <div className="mb-1 px-2 font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-[#a49f8f]">
            {g.label}
          </div>
          <div className="flex flex-col gap-px">
            {g.items.map(({ href, label, icon: Icon }) => {
              const active = href === "/" ? path === "/" : path.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex h-[30px] items-center gap-2 rounded-[6px] px-2 text-[13px] transition-colors duration-100 ${
                    active
                      ? "bg-white font-medium text-[#211f26] shadow-[0_1px_2px_rgba(60,50,90,.06),0_0_0_1px_rgba(33,31,38,.05)]"
                      : "text-[#6e6a75] hover:bg-[#efede7] hover:text-[#211f26]"
                  }`}
                >
                  <Icon
                    size={14}
                    strokeWidth={1.75}
                    className={active ? "text-[#157a77]" : "text-[#a49f8f]"}
                  />
                  {label}
                  {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#157a77]" />}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
