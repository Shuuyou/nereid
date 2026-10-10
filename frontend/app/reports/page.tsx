"use client";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
        <div className="card flex items-center justify-between">
          <h1 className="font-semibold">情报报告</h1>
          <button className="btn text-xs" disabled={generating}
            onClick={async () => { setGenerating(true); await api.dailyReport().catch(() => {}); setTimeout(load, 15000); setTimeout(() => setGenerating(false), 15000); }}>
            {generating ? "生成中…" : "生成日报"}
          </button>
        </div>
        {rows.map((r) => (
          <button key={r.id} onClick={() => api.report(r.id).then(setCur)}
            className={`card w-full text-left text-sm hover:border-accent/50 ${cur?.id === r.id ? "border-accent/50" : ""}`}>
            <div className="font-medium">{r.title}</div>
            <div className="mt-1 text-xs text-dim">{r.report_type} · {r.created_at?.slice(0, 16).replace("T", " ")}</div>
          </button>
        ))}
        {rows.length === 0 && <div className="card text-sm text-dim">暂无报告，点击"生成日报"</div>}
      </div>
      <div className="card lg:col-span-3 prose prose-invert prose-sm max-w-none overflow-y-auto [&_h1]:text-lg [&_h2]:text-base">
        {cur ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{cur.content_md}</ReactMarkdown> : <span className="text-dim">选择左侧报告查看</span>}
      </div>
    </div>
  );
}
