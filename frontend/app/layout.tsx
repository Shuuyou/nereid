import "./globals.css";
import Link from "next/link";
import { Nav } from "@/components/Nav";

export const metadata = {
  title: "捞针 · nereid — AI 安全情报系统",
  description: "智能体驱动的 AI 安全知识情报系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        {/* 海雪微粒：极稀疏的深海浮游光点 */}
        <div className="marine-snow" aria-hidden>
          {Array.from({ length: 22 }).map((_, i) => {
            const x = (i * 37 + 11) % 100;
            const d = 42 + ((i * 29) % 50);
            const size = i % 5 === 0 ? 2 : 1;
            const delay = -(i * 7) % d;
            return (
              <span key={i} className={i % 6 === 0 ? "glow" : ""} style={{
                left: `${x}%`, width: size, height: size,
                animationDuration: `${d}s`, animationDelay: `${delay}s`,
                opacity: 0,
                ["--o" as any]: i % 6 === 0 ? 0.55 : 0.22,
              }} />
            );
          })}
        </div>

        <header className="sticky top-0 z-50 border-b border-line bg-abyss/75 backdrop-blur-xl">
          <div className="mx-auto flex max-w-[1400px] items-center gap-6 px-4 py-3">
            <Link href="/" className="flex shrink-0 items-baseline gap-2">
              <span className="text-[15px] font-semibold tracking-wide text-fg">捞针</span>
              <span className="h-3 w-px translate-y-[1px] bg-linestrong" aria-hidden />
              <span className="font-mono text-[12px] lowercase tracking-[0.1em] text-dim">
                nereid<span className="text-accent" style={{ textShadow: "0 0 8px rgba(62,200,232,.8)" }}>·</span>
              </span>
            </Link>
            <Nav />
            <div className="ml-auto flex shrink-0 items-center gap-2 text-[11px] text-faint">
              <span className="dot bg-low dot-glow breathe" />在线
            </div>
          </div>
        </header>
        <main className="relative z-[1] mx-auto max-w-[1400px] px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
