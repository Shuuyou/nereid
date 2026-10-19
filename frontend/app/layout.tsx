import "./globals.css";
import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Search } from "lucide-react";

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
          <aside className="flex w-[232px] shrink-0 flex-col border-r border-[rgba(255,255,255,0.07)] bg-[#0d0e10]">
            <Link
              href="/"
              className="flex h-12 shrink-0 items-center gap-2 border-b border-[rgba(255,255,255,0.07)] px-4"
            >
              {/* 深海针标 */}
              <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden>
                <line x1="8" y1="1" x2="8" y2="11" stroke="#5ab4c4" strokeWidth="1.4" strokeLinecap="round" />
                <circle cx="8" cy="12.8" r="1.9" fill="none" stroke="#5ab4c4" strokeWidth="1.3" />
              </svg>
              <span className="text-[13.5px] font-semibold tracking-wide text-[#eceef0]">捞针</span>
              <span className="font-mono text-[11px] lowercase tracking-[0.08em] text-[#64676d]">nereid</span>
            </Link>
            <div className="flex-1 overflow-y-auto">
              <Nav />
            </div>
            <div className="border-t border-[rgba(255,255,255,0.07)] px-4 py-3">
              <div className="spec-row">
                <span className="dot" style={{ background: "#57ab5a" }} />
                SYS · ONLINE
              </div>
            </div>
          </aside>

          {/* ── 主列：顶条 + 内容 ── */}
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-12 shrink-0 items-center gap-3 border-b border-[rgba(255,255,255,0.07)] bg-[#08090a] px-5">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-[#64676d]">
                Nereid · Threat Intel Workbench
              </span>
              <div className="ml-auto flex items-center gap-3">
                <button
                  className="flex h-7 items-center gap-2 rounded-[6px] border border-[rgba(255,255,255,0.09)] bg-[#121315] px-2.5 text-[11.5px] text-[#64676d] transition-colors hover:border-[rgba(255,255,255,0.16)] hover:text-[#a9adb3]"
                  title="全局搜索（即将上线）"
                >
                  <Search size={12} strokeWidth={2} />
                  <span>搜索情报…</span>
                  <kbd className="rounded border border-[rgba(255,255,255,0.1)] bg-[#0d0e10] px-1 font-mono text-[9.5px] text-[#64676d]">⌘K</kbd>
                </button>
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
