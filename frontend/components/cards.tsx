/** AI 层标签：pastel 分类色（color-as-taxonomy，L1-L6 一一映射） */
export function LayerTag({ l }: { l?: string }) {
  const tones: Record<string, [string, string]> = {
    L1: ["L1 基础设施", "bg-mint text-mint-ink"],
    L2: ["L2 模型数据", "bg-lav text-lav-ink"],
    L3: ["L3 应用智能体", "bg-sky text-sky-ink"],
    L4: ["L4 供应链", "bg-peach text-peach-ink"],
    L5: ["L5 政策治理", "bg-butter text-butter-ink"],
    L6: ["L6 滥用威胁", "bg-rose text-rose-ink"],
  };
  const t = l ? tones[l] : null;
  return t ? (
    <span className={`inline-flex items-center rounded-badge px-2 py-0.5 font-mono text-[11px] font-medium ${t[1]}`}>
      {t[0]}
    </span>
  ) : null;
}

export function cvssToSev(score: number): string {
  if (score >= 9) return "critical";
  if (score >= 7) return "high";
  if (score >= 4) return "medium";
  if (score > 0) return "low";
  return "none";
}
