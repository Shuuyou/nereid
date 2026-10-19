"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, FileDown, Copy, Check } from "lucide-react";
import { api } from "@/lib/api";
import { SpecRow, SpecDot, Empty, Skeleton } from "@/components/ui";

export default function ReportDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [r, setR] = useState<any>(null);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setR(null); setErr(""); setCopied(false);
    api.report(id).then(setR).catch((e) => setErr(String(e)));
  }, [id]);

  /** 智能返回：站内来源 router.back() 保留列表上下文，站外/直开落到 /reports */
  const goBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1 && document.referrer.startsWith(window.location.origin)) {
      router.back();
    } else {
      router.push("/reports");
    }
  };

  /** 导出 Markdown：正文 Blob 直接下载，文件名取标题（清洗非法字符） */
  function exportMd() {
    const blob = new Blob([r.content_md || ""], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(r.title || r.id).replace(/[\\/:*?"<>|\s]+/g, "_")}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  /** 复制全文：clipboard API 兜底 execCommand（http://IP 部署时非安全上下文） */
  async function copyAll() {
    const text = r?.content_md || "";
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  const spec = (
    <SpecRow>
      <span>FIG_RP</span><SpecDot />
      <span><Link href="/reports" className="transition-colors hover:text-accent">REPORTS</Link></span><SpecDot />
      <span className="truncate">{id}</span>
      <button onClick={goBack}
        className="ml-auto inline-flex items-center gap-1 transition-colors hover:text-accent"
        title="返回来源页">
        <ArrowLeft size={11} strokeWidth={2} />返回
      </button>
    </SpecRow>
  );

  if (err) return (
    <div>
      {spec}
      <Empty text="报告加载失败" hint="报告不存在或后端不可达" />
      <div className="mt-3 flex justify-center">
        <Link href="/reports" className="btn btn-sm">返回报告列表</Link>
      </div>
    </div>
  );

  if (!r) return (
    <div>
      {spec}
      <div className="mt-4 space-y-4">
        <Skeleton className="h-[72px]" />
        <Skeleton className="h-[440px]" />
      </div>
    </div>
  );

  const st = r.stats || {};
  const covered = st.total ?? st.items;

  return (
    <div>
      {spec}

      {/* ── 头区：标题 + 类型徽标 + 元数据 + 操作 ── */}
      <div className="mt-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-snug tracking-[-0.005em] text-fg">{r.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="badge mono">{r.report_type || "—"}</span>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[12px] text-faint">
            <span>生成 <span className="tnum text-dim">{r.created_at?.slice(0, 16).replace("T", " ") || "—"}</span></span>
            {covered != null && <span>覆盖 <span className="tnum text-dim">{covered} 条</span></span>}
            {st.ai != null && <span>AI 相关 <span className="tnum text-dim">{st.ai}</span></span>}
            {st.kev != null && <span>KEV <span className="tnum text-dim">{st.kev}</span></span>}
          </div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <button className="btn btn-sm" onClick={exportMd} title="下载 Markdown 源文件">
            <FileDown size={12} strokeWidth={2} />导出 .md
          </button>
          <button className="btn btn-sm btn-ghost" onClick={copyAll} title="复制 Markdown 全文">
            {copied
              ? <><Check size={12} strokeWidth={2} className="text-ok" /><span className="text-ok">已复制</span></>
              : <><Copy size={12} strokeWidth={2} />复制全文</>}
          </button>
        </div>
      </div>

      {/* ── 正文：Markdown 排版列 ── */}
      <div className="sect">
        {r.content_md ? (
          <div className="prose-a mx-auto max-w-[680px] pb-4 pt-1">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{r.content_md}</ReactMarkdown>
          </div>
        ) : (
          <Empty text="报告正文为空" />
        )}
      </div>
    </div>
  );
}
