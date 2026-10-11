"""nlp worker：英译中 / TL;DR / 受影响版本 / 缓解建议 / 相似情报（LLM + 验证降级）"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.db.models import Item
from app.enrichment.common import (
    llm_enabled, llm_struct, llm_text, ok, partial, skipped, valid_version,
)

log = get_logger("enrich.nlp")


class TranslateOut(BaseModel):
    title_zh: str = ""
    summary_zh: str = Field(default="", description="中文摘要 200 字内")


class MetaOut(BaseModel):
    affected_versions: list[str] = Field(default_factory=list)
    mitigation: str = Field(default="", description="修复/缓解建议 200 字内")
    impact_zh: str = Field(default="", description="影响面 80 字内")
    exploitability_zh: str = Field(default="", description="利用难度 60 字内")


def _needs_translate(item: Item) -> bool:
    if item.title_zh:
        return False
    return not re.search(r"[一-鿿]", item.title or "")


async def run(item, ctx) -> dict:
    fields: dict = {}
    extra: dict = {}
    notes = []

    # 中文源直接回填（已中文无需翻译）
    if not item.title_zh and re.search(r"[一-鿿]", item.title or ""):
        fields["title_zh"] = (item.title or "")[:300]
    if not item.summary_zh and re.search(r"[一-鿿]", item.summary or ""):
        fields["summary_zh"] = (item.summary or "")[:2000]
        notes.append("zh_backfill")

    if llm_enabled():
        text = (item.content_text or item.summary or "")[:6000]
        title = item.title or ""
        if _needs_translate(item):
            out = await llm_struct(
                [{"role": "system", "content": "你是 AI 安全情报翻译专家，将英文情报译为准确的中文（保留 CVE/CWE/产品名原文）。"},
                 {"role": "user", "content": f"标题：{title}\n\n正文：\n{text[:3000]}"}],
                TranslateOut)
            if out:
                if out.title_zh:
                    fields["title_zh"] = out.title_zh[:300]
                if out.summary_zh:
                    fields["summary_zh"] = out.summary_zh[:2000]
                notes.append("translated")

        mout = await llm_struct(
            [{"role": "system", "content": "你是漏洞分析专家。从文本抽取受影响版本（尽量含范围如 <1.2.3）、缓解建议、影响面与利用难度。无依据就给空值，不要编造。"},
             {"role": "user", "content": f"标题：{title}\n产品：{', '.join(item.products or [])}\n\n{text[:4000]}"}],
            MetaOut)
        if mout:
            vers = [v for v in mout.affected_versions if valid_version(v) or re.search(r"[<>=]", v)]
            if vers:
                fields["affected_versions"] = "\n".join(vers[:20])
            if mout.mitigation:
                extra["mitigation_zh"] = mout.mitigation[:1500]
            extra["impact_zh"] = mout.impact_zh[:300]
            extra["exploitability_zh"] = mout.exploitability_zh[:200]
            notes.append("meta")
    else:
        notes.append("llm_disabled")

    # 相似情报（向量检索，找 top5）
    try:
        from app.rag.embedder import embed_texts
        from app.rag.qdrant import search_dense
        vec = await embed_texts([(item.title or "") + " " + (item.summary or "")[:500]])
        hits = await search_dense(vec[0], top_k=8, exclude_id=item.id)
        sims = [{"item_id": h["item_id"], "score": h["score"], "title": h.get("title", "")[:80]}
                for h in hits if h["item_id"] != item.id][:5]
        if sims:
            extra["similar_items"] = sims
            notes.append(f"similar={len(sims)}")
    except Exception as e:  # noqa: BLE001
        log.debug("similar_failed", error=str(e)[:120])

    if not fields and not extra:
        return skipped("nothing enriched")
    return ok("|".join(notes), confidence=0.75, fields=fields, extra=extra, data_keys=["nlp"])
