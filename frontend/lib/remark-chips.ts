/**
 * remark 插件：把回答正文里的引用标记与实体 ID 转成可交互节点
 *   [n]            → <citation-chip n>
 *   CVE/GHSA/CWE/CAPEC/ATT&CK-T####/ATLAS-AML.T#### → <entity-chip id>
 * 单文本节点内 >8 个实体 → 包进 <entity-group>（前端折叠为 top4 + "+N"）
 * 只处理 text 节点，link/code/inlineCode 父链自动跳过（mdast 结构保证）。
 */
const PATTERN = /\[(\d{1,3})\]|\b(CVE-\d{4}-\d{4,7}|GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}|CWE-\d{1,5}|CAPEC-\d{1,4}|AML\.T\d{4}|T\d{4}(?:\.\d{3})?)\b/g;

const ENT_GROUP_MIN = 8;

function splitText(value: string): any[] | null {
  PATTERN.lastIndex = 0;
  if (!PATTERN.test(value)) return null;
  PATTERN.lastIndex = 0;
  const parts: any[] = [];
  let cursor = 0, m: RegExpExecArray | null, entCount = 0;
  while ((m = PATTERN.exec(value)) !== null) {
    if (m.index > cursor) parts.push({ type: "text", value: value.slice(cursor, m.index) });
    if (m[1]) {
      parts.push({ type: "citationChip", data: { hName: "citation-chip", hProperties: { n: m[1] } } });
    } else {
      entCount++;
      parts.push({ type: "entityChip", data: { hName: "entity-chip", hProperties: { id: m[2] } } });
    }
    cursor = m.index + m[0].length;
  }
  if (cursor < value.length) parts.push({ type: "text", value: value.slice(cursor) });
  // >8 实体且全是"分隔符+实体"构成 → 包进 entity-group 折叠
  if (entCount > ENT_GROUP_MIN) {
    const onlyRuns = parts.every(
      (p) => p.type !== "text" || p.value.replace(/[\s,，、;；·.…-]/g, "").length <= 2,
    );
    if (onlyRuns) {
      return [{ type: "entityGroup", data: { hName: "entity-group" }, children: parts }];
    }
  }
  return parts;
}

function visit(node: any): void {
  if (!node || !Array.isArray(node.children)) return;
  if (node.type === "link" || node.type === "linkReference" || node.type === "image") return;
  const next: any[] = [];
  for (const child of node.children) {
    if (child.type === "text") {
      const parts = splitText(child.value);
      if (parts) next.push(...parts);
      else next.push(child);
    } else {
      visit(child);
      next.push(child);
    }
  }
  node.children = next;
}

export function remarkChips() {
  return (tree: any) => visit(tree);
}
