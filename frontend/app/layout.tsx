import "./globals.css";
import Link from "next/link";

export const metadata = { title: "捞针 · Nereid — AI 安全情报系统", description: "智能体驱动的 AI 安全知识情报系统" };

const NAV = [
  ["/", "态势总览"], ["/items", "情报库"], ["/qa", "深度问答"],
  ["/graph", "知识图谱"], ["/sources", "数据源"], ["/reports", "报告"],
  ["/pipeline", "流水线"], ["/review", "复核队列"], ["/for-you", "为你推荐"],
] as const;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="sticky top-0 z-50 border-b border-border bg-panel/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-lg font-bold text-accent">捞针</span>
              <span className="text-sm font-semibold text-dim">Nereid</span>
              <span className="hidden text-xs text-dim sm:inline">AI 安全情报系统</span>
            </Link>
            <nav className="flex gap-1 overflow-x-auto">
              {NAV.map(([href, label]) => (
                <Link key={href} href={href}
                  className="rounded px-3 py-1.5 text-sm text-dim hover:bg-border hover:text-fg whitespace-nowrap">
                  {label}
                </Link>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-2 text-xs text-dim">
              <span className="h-2 w-2 rounded-full bg-low animate-pulse" />在线
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
