"""AnalystAgent：情报分析与报告生成（Planner-Executor-Critic 模式）

- 日报/周报：聚合统计 + 重点情报 + LLM 撰写 + 自我校验
- 专题报告：按主题聚合知识库生成深度报告
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select

from app.core.llm import chat
from app.core.logging import get_logger
from app.core.taxonomy import LAYER_NAMES, OWASP_ASI_NAMES, OWASP_LLM_NAMES
from app.db.models import Item, Report
from app.db.session import get_session_factory

log = get_logger("analyst")


async def _collect_stats(hours: int = 24) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with get_session_factory()() as db:
        total = (await db.execute(select(func.count(Item.id)).where(Item.first_seen_at >= since))).scalar() or 0
        ai = (await db.execute(select(func.count(Item.id)).where(Item.first_seen_at >= since, Item.ai_relevance_score >= 0.3))).scalar() or 0
        kev = (await db.execute(select(func.count(Item.id)).where(Item.first_seen_at >= since, Item.is_kev.is_(True)))).scalar() or 0
        by_layer = dict((await db.execute(select(Item.ai_layer, func.count()).where(Item.first_seen_at >= since).group_by(Item.ai_layer))).all())
        top = (await db.execute(select(Item).where(
            Item.first_seen_at >= since, Item.ai_relevance_score >= 0.3
        ).order_by(desc(func.coalesce(Item.priority_score, 0))).limit(15))).scalars().all()
        top_data = [{
            "id": it.id, "title": it.title_zh or it.title, "cve": it.cve_ids,
            "severity": it.severity, "layer": it.ai_layer, "is_kev": it.is_kev,
            "epss": it.epss_score, "has_poc": it.has_poc, "sources": it.source_names,
            "summary": (it.summary_zh or it.summary or "")[:300],
        } for it in top]
        return {"total": total, "ai_items": ai, "kev": kev, "by_layer": by_layer, "top": top_data}


def _fallback_report(stats: dict, date_str: str) -> str:
    lines = [f"# AI 安全情报日报 · {date_str}\n",
             f"本期共采集情报 {stats['total']} 条，其中 AI 相关 {stats['ai_items']} 条，新增在野利用 {stats['kev']} 条。\n",
             "## 层级分布\n"]
    for k, v in sorted(stats["by_layer"].items(), key=lambda x: -x[1]):
        if k:
            lines.append(f"- {LAYER_NAMES.get(k, k)}（{k}）：{v} 条")
    lines.append("\n## 重点情报\n")
    for t in stats["top"][:10]:
        badges = []
        if t["is_kev"]:
            badges.append("KEV在野利用")
        if t["has_poc"]:
            badges.append("有POC")
        if t["severity"]:
            badges.append(t["severity"].upper())
        cve = ",".join(t["cve"]) if t["cve"] else "-"
        lines.append(f"- **[{cve}]** {t['title']}（{'、'.join(badges) or '常规'}）")
        if t["summary"]:
            lines.append(f"  {t['summary'][:150]}")
    return "\n".join(lines)


async def generate_daily_report() -> str:
    """Planner→Executor→Critic：统计→LLM撰写→校验修订"""
    stats = await _collect_stats(24)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        resp = await chat([
            {"role": "system", "content": (
                "你是资深AI安全情报分析师。基于给定统计与重点情报撰写专业中文日报，结构："
                "一、今日概览（数字+趋势判断）；二、重点漏洞解读（每条：影响组件/利用条件/修复建议）；"
                "三、AI安全风险态势（结合OWASP LLM/ASI与层级分布）；四、行动建议。"
                "引用情报时用其CVE-ID。语言精炼专业，面向安全运营负责人。")},
            {"role": "user", "content": f"统计数据：{stats}"},
        ], max_tokens=3000)
        content = resp["content"]
        # Critic：校验是否包含所有 KEV 条目
        kev_missing = [t for t in stats["top"] if t["is_kev"] and t["cve"] and not any(c in content for c in t["cve"])]
        if kev_missing:
            fix = await chat([
                {"role": "system", "content": "你是情报审核员。请补充日报中遗漏的KEV条目（在'重点漏洞解读'部分添加），其余内容保持不变。"},
                {"role": "user", "content": f"原报告：\n{content}\n\n遗漏KEV：{kev_missing}"},
            ], max_tokens=3500)
            content = fix["content"] or content
    except Exception as e:  # noqa: BLE001
        log.warning("daily_report_llm_fallback", error=str(e)[:200])
        content = _fallback_report(stats, date_str)

    async with get_session_factory()() as db:
        r = Report(report_type="daily", title=f"AI安全情报日报 {date_str}", content_md=content,
                   period_start=datetime.now(timezone.utc) - timedelta(hours=24),
                   period_end=datetime.now(timezone.utc), stats={"total": stats["total"], "ai": stats["ai_items"], "kev": stats["kev"]})
        db.add(r)
        await db.commit()
    log.info("daily_report_done", chars=len(content))
    return content


async def generate_topic_report(topic: str) -> str:
    """专题报告：按主题聚合知识库生成深度分析"""
    async with get_session_factory()() as db:
        from sqlalchemy import or_
        like = f"%{topic}%"
        rows = (await db.execute(select(Item).where(or_(
            Item.title.ilike(like), Item.title_zh.ilike(like), Item.products.overlap([topic]),
        ), Item.ai_relevance_score >= 0.2).order_by(desc(func.coalesce(Item.published_at, Item.first_seen_at))).limit(40))).scalars().all()
    data = [{"title": it.title_zh or it.title, "cve": it.cve_ids, "severity": it.severity,
             "layer": it.ai_layer, "date": it.published_at.isoformat() if it.published_at else None,
             "techniques": it.attack_techniques, "summary": (it.summary_zh or it.summary or "")[:200]}
            for it in rows]
    try:
        resp = await chat([
            {"role": "system", "content": (
                "你是AI安全研究员。基于知识库数据撰写专题分析报告，结构：背景→事件时间线→技术剖析"
                "（攻击技术/受影响组件）→影响面→防御建议→趋势展望。引用具体CVE-ID和数据。")},
            {"role": "user", "content": f"专题：{topic}\n知识库条目：{data}"},
        ], reasoning=True, max_tokens=4000)
        content = resp["content"]
    except Exception as e:  # noqa: BLE001
        content = f"# {topic} 专题报告\n\n共 {len(data)} 条相关情报。\n\n" + "\n".join(
            f"- {d['date'][:10] if d['date'] else '-'} [{','.join(d['cve']) or '-'}] {d['title']}" for d in data)
    async with get_session_factory()() as db:
        db.add(Report(report_type="topic", title=f"{topic} 专题分析", content_md=content,
                      stats={"items": len(data), "topic": topic}))
        await db.commit()
    return content
