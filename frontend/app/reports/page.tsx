"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { FileText, FilePlus2, Download } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader, Empty, Skeleton } from "@/components/ui";
import { zh, REPORT_TYPE } from "@/lib/labels";

export default function ReportsPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => { api.reports().then((d) => { setRows(d.reports || []); setLoaded(true); }).catch(() => setLoaded(true)); };
  useEffect(() => { load(); }, []);

  function toast(t: string) { setMsg(t); setTimeout(() => setMsg(""), 3000); }

  async function generate() {
    setGenerating(true);
    await api.dailyReport().catch(() => {});
    toast("日报生成中（LLM 撰写约 10-20s）…");
    setTimeout(load, 15000);
    setTimeout(() => setGenerating(false), 15000);
  }

  async function exportMd(id: string) {
    const r = await api.report(id).catch(() => null);
    if (!r) { toast("导出失败：报告不可达"); return; }
    const blob = new Blob([r.content_md || ""], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(r.title || r.id).replace(/[\\/:*?"<>|\s]+/g, "_")}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div>
      <PageHeader title="情报报告" desc="AI 分析师按周期聚合生成"
        right={
          <button className="btn btn-acc" disabled={generating} onClick={generate}>
            <FilePlus2 size={12} strokeWidth={1.75} />{generating ? "生成中…" : "生成日报"}
          </button>
        } />

      {!loaded ? (
        <div className="space-y-px">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9" />)}</div>
      ) : rows.length === 0 ? (
        <Empty text="暂无报告" hint="点击右上角「生成日报」聚合近 24h 情报" />
      ) : (
        <table className="dt">
          <thead>
            <tr><th>生成时间</th><th>标题</th><th>类型</th><th className="r">覆盖条目</th><th className="r">操作</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="rowlink">
                <td className="num text-faint">{r.created_at?.slice(0, 16).replace("T", " ")}</td>
                <td>
                  <div className="flex items-center gap-2">
                    <FileText size={13} strokeWidth={1.75} className="shrink-0 text-faint" />
                    <Link href={`/reports/${r.id}`}
                      className="stretched text-[13px] text-fg transition-colors hover:text-accent">
                      {r.title}
                    </Link>
                  </div>
                </td>
                <td><span className="badge">{zh(REPORT_TYPE, r.report_type)}</span></td>
                <td className="r num text-dim">{r.stats?.total ?? r.stats?.items ?? "—"}</td>
                <td className="r">
                  <div className="z-act flex justify-end gap-1.5">
                    <button className="btn btn-sm btn-ghost" title="导出 Markdown" onClick={() => exportMd(r.id)}>
                      <Download size={11} strokeWidth={1.75} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {msg && (
        <div className="panel rise fixed bottom-5 right-5 z-[60] border-l-2 border-l-accent px-4 py-2.5 text-[13px] text-fg">
          {msg}
        </div>
      )}
    </div>
  );
}
