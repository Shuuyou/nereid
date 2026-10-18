"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Layers, MessageSquareText, Share2, Radio,
  FileText, GitBranch, ClipboardCheck, Compass,
} from "lucide-react";

const NAV = [
  { href: "/", label: "态势总览", icon: LayoutDashboard },
  { href: "/items", label: "情报库", icon: Layers },
  { href: "/qa", label: "深度问答", icon: MessageSquareText },
  { href: "/graph", label: "知识图谱", icon: Share2 },
  { href: "/sources", label: "数据源", icon: Radio },
  { href: "/reports", label: "报告", icon: FileText },
  { href: "/pipeline", label: "流水线", icon: GitBranch },
  { href: "/review", label: "复核队列", icon: ClipboardCheck },
  { href: "/for-you", label: "为你推荐", icon: Compass },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="flex gap-0.5 overflow-x-auto" aria-label="主导航">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link key={href} href={href}
            className={`nav-item flex items-center gap-1.5 ${active ? "nav-item-active" : ""}`}>
            <Icon size={14} strokeWidth={1.75} className={active ? "text-accent" : "text-faint"} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
