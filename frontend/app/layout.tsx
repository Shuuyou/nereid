import "./globals.css";
import Link from "next/link";
import { Nav } from "@/components/Nav";

export const metadata = {
  title: "捞针 · nereid — AI 安全情报系统",
  description: "智能体驱动的 AI 安全知识情报系统",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="flex h-screen overflow-hidden">
          {/* ── 左侧栏 232px ── */}
          <aside className="flex w-[232px] shrink-0 flex-col border-r border-line bg-paper2">
            <Link
              href="/"
              className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-4"
            >
              {/* 深海针标 */}
              <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden>
                <line x1="8" y1="1" x2="8" y2="11" stroke="#157a77" strokeWidth="1.4" strokeLinecap="round" />
                <circle cx="8" cy="12.8" r="1.9" fill="none" stroke="#157a77" strokeWidth="1.3" />
              </svg>
              <span className="text-[13.5px] font-semibold tracking-wide text-ink">捞针</span>
              <span className="font-mono text-[11px] lowercase tracking-[0.08em] text-faint">nereid</span>
            </Link>
            <div className="flex-1 overflow-y-auto">
              <Nav />
            </div>
            <div className="border-t border-line px-4 py-3">
              <div className="spec-row">
                <span className="dot" style={{ background: "#2e7d5b" }} />
                SYS · ONLINE
              </div>
            </div>
          </aside>

          {/* ── 主列：顶条 + 内容 ── */}
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-canvas px-5">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-faint">
                Nereid · Threat Intel Workbench
              </span>
              <div className="ml-auto flex items-center gap-3">
                <span className="mono text-[11px] text-faint">
                  {new Date().toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "long" })}
                </span>
              </div>
            </header>
            <main className="min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto max-w-[1480px] px-6 py-5">{children}</div>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
