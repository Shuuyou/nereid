"""ai_classify worker：LLM 精判 AI 相关性（对规则分类的低分/边界项二次确认）"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.enrichment.common import llm_enabled, llm_struct, ok, skipped

log = get_logger("enrich.ai_classify")


class ClassifyOut(BaseModel):
    is_ai_related: bool
    confidence: float = Field(ge=0, le=1)
    ai_layers: list[str] = Field(default_factory=list, description="L1-L6")
    reason: str = ""


async def run(item, ctx) -> dict:
    score = item.ai_relevance_score or 0.0
    # 只对边界项（0.15~0.75）做 LLM 精判；高分/零分走规则结论
    if not (0.15 <= score <= 0.75):
        return skipped(f"rule score {score} out of refine band")
    if not llm_enabled():
        return skipped("llm disabled")

    text = (item.content_text or item.summary or "")[:3000]
    out = await llm_struct(
        [{"role": "system", "content": (
            "判断该安全情报是否与 AI/ML/LLM 系统安全相关（AI 基础设施、模型、框架、Agent、"
            "AI 供应链、提示注入、AI 滥用、AI 治理政策）。输出 is_ai_related、置信度、AI 层（"
            "L1=应用/Agent L2=模型/数据 L3=框架/组件 L4=部署/暴露 L5=平台/基础设施 L6=滥用/治理）与一句话理由。")},
         {"role": "user", "content": f"标题：{item.title}\n\n{text}"}],
        ClassifyOut)
    if not out:
        return skipped("llm no answer")

    extra = {"ai_classify_llm": {"is_ai": out.is_ai_related, "conf": out.confidence, "reason": out.reason[:200]}}
    fields = {}
    if out.is_ai_related and out.confidence >= 0.7:
        fields["ai_relevance_score"] = max(score, 0.7)
        valid = [l for l in out.ai_layers if l in ("L1", "L2", "L3", "L4", "L5", "L6")]
        if valid and not item.ai_layer:
            fields["ai_layer"] = valid[0]
    elif not out.is_ai_related and out.confidence >= 0.8:
        fields["ai_relevance_score"] = min(score, 0.3)
    return ok(f"llm: ai={out.is_ai_related}@{out.confidence}", confidence=out.confidence,
              fields=fields, data_keys=["ai_classify"])
