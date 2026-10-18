"use client";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, Plus } from "lucide-react";
import { api } from "@/lib/api";

export default function ReportsPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [cur, setCur] = useState<any>(null);
  const [generating, setGenerating] = useState(false);

  const load = () => { api.reports().then((d) => setRows(d.reports || [])).catch(() => {}); };
  useEffect(() => { load(); }, []);

  return (
    <div className="grid gap-4 lg:grid-cols-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h1 className="h2">情报报告</h1>
          <button className="btn-soft !py-1.5 !text-[12px]" disabled={generating}
            onClick={async () => { setGenerating(true); await api.dailyReport().catch(() => {}); setTimeout(load, 15000); setTimeout(() => setGenerating(false), 15000); }}>
            <Plus size={12} />{generating ? "生成中…" : "生成日报"}
          </button>
        </div>
        {rows.map((r) => {
          const active = cur?.id === r.id;
          return (
            <button key={r.id} onClick={() => api.report(r.id).then(setCur)}
              className={`card card-hover w-full text-left transition-colors ${active ? "border-accent/40 bg-accent/[0.06]" : ""}`}>
              <div className="flex items-start gap-2">
                <FileText size={14} strokeWidth={1.5} className={`mt-0.5 shrink-0 ${active ? "text-accent" : "text-faint"}`} />
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium text-fg/90">{r.title}</div>
                  <div className="mt-1 text-[11px] text-faint">
                    <span className="tag !px-1">{r.report_type}</span>
                    <span className="ml-2 tabular-nums">{r.created_at?.slice(0, 16).replace("T", " ")}</span>
                  </div>
                </div>
              </div>
            </button>
          );
        })}
        {rows.length === 0 && <div className="card text-[12px] text-faint">暂无报告，点击「生成日报」</div>}
      </div>
      <div className="card lg:col-span-3 overflow-y-auto">
        {cur ? (
          <div className="md max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{cur.content_md}</ReactMarkdown>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-[13px] text-faint">选择左侧报告查看</div>
        )}
      </div>
    </div>
  );
}
