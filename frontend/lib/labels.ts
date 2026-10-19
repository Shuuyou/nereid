/** 全站枚举/内部词 → 中文展示映射。新增内部值一律走这里，禁止直出。 */

export const ITEM_TYPE: Record<string, string> = {
  vuln: "漏洞", advisory: "通报", exploit: "利用", article: "文章",
  paper: "论文", incident: "事件", policy: "政策",
};

export const REVIEW_STATUS: Record<string, string> = {
  needs_review: "待复核", confirmed: "已确认", auto: "自动通过",
  rejected: "已回炉",
};

export const RUN_STATUS: Record<string, string> = {
  done: "完成", error: "失败", running: "运行中", pending: "排队中",
};

export const ENRICH_STATUS: Record<string, string> = {
  ok: "成功", error: "失败", partial: "部分", skipped: "跳过",
};

export const CREDIBILITY: Record<string, string> = {
  trusted: "可信", community: "社区", suspicious: "存疑", malicious: "恶意",
};

export const SOURCE_TYPE: Record<string, string> = {
  official: "官方", vulndb: "漏洞库", rss: "RSS", api: "API",
  vendor: "厂商", community: "社区", paper: "论文", policy: "政策",
  mail: "邮件", git: "代码仓库", misc: "其他",
};

export const TIER: Record<string, string> = {
  "1": "准实时", "2": "常规", "3": "低频",
};

export const STEP_NODE: Record<string, string> = {
  collect: "采集", enrich: "富化", index: "索引", kg: "图谱", notify: "通知",
};

export const ENRICH_DIM: Record<string, string> = {
  scorers: "评分聚合", severity: "严重度", kev: "KEV", epss: "EPSS",
  cvss: "CVSS", ssvc: "SSVC", attack: "ATT&CK", atlas: "ATLAS",
  owasp: "OWASP", taxonomy: "AI 分类", ai_classify: "AI 分类",
  summary: "中文摘要", zh_summary: "中文摘要", version: "版本解析",
  fix: "修复建议", remediation: "修复建议", poc: "PoC", poc_scout: "PoC",
  asset: "资产测绘", exposure: "资产测绘", paper: "论文关联",
  similar: "相似情报", attack_chain: "攻击链", cwe: "CWE",
  capec: "CAPEC", mitre: "ATT&CK", ingest: "采集",
};

export const PROFILE_TAG: Record<string, string> = {
  product: "产品", vendor: "厂商", package: "包", pkg: "包",
  cpe: "CPE", cve: "CVE", layer: "层级", owasp: "OWASP",
  keyword: "关键词", technique: "技术", tech: "技术",
};

export const SEVERITY: Record<string, string> = {
  critical: "严重", high: "高危", medium: "中危", low: "低危",
  none: "未定级", info: "信息",
};

export const CVSS_SRC: Record<string, string> = {
  cna: "厂商填报", nvd: "NVD", collector: "采集器",
};
export const cvssSrcZh = (v?: string | null): string => {
  if (!v) return "—";
  if (v.startsWith("adp:")) return `CISA 富化（${v.slice(4)}）`;
  return CVSS_SRC[v.toLowerCase()] ?? v;
};

export const SSVC_EXPLOIT: Record<string, string> = {
  active: "已利用", poc: "有 PoC", none: "未见",
};
export const SSVC_BOOL: Record<string, string> = {
  yes: "是", no: "否",
};
export const SSVC_IMPACT: Record<string, string> = {
  total: "完全", partial: "部分",
};
export const EXPLOIT_MATURITY: Record<string, string> = {
  weaponized: "武器化", poc: "有 PoC", none: "未见利用",
};

export const REPORT_TYPE: Record<string, string> = {
  daily: "日报", weekly: "周报", monthly: "月报", custom: "定制",
};

/** 通用兜底：查表，查不到返回原值（ID/URL 类原样显示不算违规） */
export function zh(map: Record<string, string>, v?: string | null): string {
  if (v == null || v === "") return "—";
  return map[String(v).toLowerCase()] ?? String(v);
}
