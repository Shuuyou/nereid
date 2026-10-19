"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Layers, MessageSquareText, Share2, Radio,
  FileText, GitBranch, ClipboardCheck, Compass,
} from "lucide-react";

const GROUPS: { label: string; items: { href: string; label: string; icon: any }[] }[] = [
  {
    label: "工作台",
    items: [
      { href: "/", label: "态势总览", icon: LayoutDashboard },
      { href: "/qa", label: "深度问答", icon: MessageSquareText },
      { href: "/review", label: "复核队列", icon: ClipboardCheck },
      { href: "/for-you", label: "为你推荐", icon: Compass },
    ],
  },
  {
    label: "情报",
    items: [
      { href: "/items", label: "情报库", icon: Layers },
      { href: "/graph", label: "知识图谱", icon: Share2 },
      { href: "/reports", label: "报告", icon: FileText },
    ],
  },
  {
    label: "系统",
    items: [
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
          <div className="mb-1 px-2 font-mono text-[10px] font-medium uppercase tracking-[0.1em] text-[#52555b]">
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
                      ? "bg-[#17181b] font-medium text-[#eceef0]"
                      : "text-[#a9adb3] hover:bg-[#121315] hover:text-[#eceef0]"
                  }`}
                >
                  <Icon
                    size={14}
                    strokeWidth={1.75}
                    className={active ? "text-[#5ab4c4]" : "text-[#64676d]"}
                  />
                  {label}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
