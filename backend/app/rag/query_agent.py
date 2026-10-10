"""QueryAgent：LangGraph 编排的深度问答
路由 → (CVE 直连 | 检索+KG 扩展) → 重排 → 生成(引用) → 置信度/拒答 → trace
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.ids import extract_ids
from app.core.llm import chat, chat_structured
from app.core.logging import get_logger
from app.db.models import Item, MappingLink, Poc
from app.db.session import get_session_factory
from app.rag import kg, retriever

log = get_logger("rag.query_agent")

ROUTE_SYS = """你是 AI 安全情报问答路由器。将用户问题分类：
- vuln_lookup: 查询具体漏洞详情/CVE 信息
- comparison: 对比多个漏洞/技术
- multi_hop: 需要跨多文档推理（如"影响 X 的所有漏洞"、"同弱点还有哪些"）
- trend: 趋势/统计类（最近/多少/哪些）
- general: 一般安全问答
返回 JSON：{"route":..., "sub_questions":[...], "entities":[...], "filters":{"severity":[...],"since":"YYYY-MM-DD"}}"""


class RouteOut(BaseModel):
    route: str = "general"
    sub_questions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)


class AnswerOut(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1, default=0.5)
    followups: list[str] = Field(default_factory=list)


async def _route(question: str, history: list[dict]) -> RouteOut:
    try:
        return await chat_structured(
            [{"role": "system", "content": ROUTE_SYS},
             *[{"role": h["role"], "content": h["content"]} for h in history[-4:]],
             {"role": "user", "content": question}], RouteOut)
    except Exception as e:  # noqa: BLE001
        log.warning("route_failed", error=str(e)[:120])
        return RouteOut(route="general", sub_questions=[question])


async def _cve_direct(cve: str) -> dict | None:
    """CVE 精确命中：DB 全量情报 + 富化"""
    async with get_session_factory()() as db:
        item = (await db.execute(
            select(Item).where(Item.cve_ids.any(cve)).order_by(Item.first_seen_at.desc()))).scalars().first()
        if not item:
            return None
        pocs = (await db.execute(select(Poc).where(Poc.item_id == item.id))).scalars().all()
        maps = (await db.execute(select(MappingLink).where(MappingLink.item_id == item.id))).scalars().all()
        return {"item": item, "pocs": pocs, "mappings": maps}


async def answer(question: str, session_id: str | None = None,
                 history: list[dict] | None = None, top_k: int = 8) -> dict:
    """主入口：返回 {answer, citations, trace, confidence, latency_ms}"""
    t0 = time.time()
    history = history or []
    trace: dict = {"steps": []}

    def step(name, **kw):
        trace["steps"].append({"step": name, "ts": datetime.now(timezone.utc).isoformat(), **kw})

    # ---- 1. 实体直提（确定性优先）----
    ids = extract_ids(question)
    cves = ids["cve"]
    cwes = ids["cwe"]
    all_ids = ids["cve"] + ids["ghsa"] + ids["edb"] + ids["cwe"] + ids["atlas"]
    step("extract", cves=cves, cwes=cwes, ids=all_ids[:10])

    # ---- 2. CVE 直连（绕过完整 RAG，高置信）----
    if cves:
        direct = await _cve_direct(cves[0])
        if direct:
            step("cve_direct", cve=cves[0], found=True)
            item = direct["item"]
            ctx = _format_item_block(item, direct["pocs"], direct["mappings"])
            out = await _generate(question, history, [ctx], trace_note=f"CVE 直连 {cves[0]}")
            cites = [_cite(item, 1)]
            return _final(out, cites, trace, t0)

    # ---- 3. 路由/分解 ----
    routed = await _route(question, history)
    sub_qs = routed.sub_questions[:3] or [question]
    step("route", route=routed.route, sub_questions=sub_qs, entities=routed.entities)

    # ---- 4. 混合检索 ----
    all_hits: list[dict] = []
    seen_iid: set[str] = set()
    for q in sub_qs:
        hits = await retriever.retrieve(q, top_k=top_k, **(routed.filters or {}))
        for h in hits:
            if h["item_id"] not in seen_iid:
                seen_iid.add(h["item_id"])
                all_hits.append(h)
    all_hits.sort(key=lambda h: h.get("rerank_score", h["score"]), reverse=True)
    all_hits = all_hits[:top_k * 2]
    step("retrieve", hits=len(all_hits))

    # ---- 5. KG 扩展（multi_hop 或实体存在时）----
    kg_facts: list[dict] = []
    kg_entities = cves + cwes + routed.entities[:5]
    if routed.route in ("multi_hop", "comparison", "trend") or kg_entities:
        kg_facts = await kg.entity_expand(kg_entities, hops=2, limit=40)
        step("kg_expand", facts=len(kg_facts), entities=kg_entities[:8])

    # ---- 6. 组装上下文（检索文本 + DB 结构化字段水合）----
    hit_items = await _hydrate([h["item_id"] for h in all_hits])
    contexts = []
    for i, h in enumerate(all_hits, 1):
        it = hit_items.get(h["item_id"])
        struct = _struct_line(it) if it else ""
        contexts.append({"n": i, "item_id": h["item_id"], "title": h.get("title_zh") or h.get("title"),
                         "url": h.get("url"), "text": (struct + "\n" + h.get("text", ""))[:1800],
                         "meta": {k: h.get(k) for k in ("cve", "severity", "cvss", "epss", "is_kev", "item_type", "published_at")},
                         "score": h.get("rerank_score", h["score"])})
    if kg_facts:
        facts_txt = "\n".join(
            f"- {f.get('title','?')} [{f.get('item_id')}] 关联:{f.get('rel')} via {f.get('nid') or f.get('via_cwe','')}"
            for f in kg_facts[:15])
        contexts.append({"n": len(contexts) + 1, "item_id": "kg", "title": "知识图谱关联事实",
                         "url": None, "text": facts_txt, "meta": {"kind": "kg_facts"}, "score": 0.6})
    step("context", n=len(contexts))

    # ---- 7. 生成 ----
    out = await _generate(question, history, contexts)
    cites = [
        {"n": c["n"], "item_id": c["item_id"], "title": c["title"], "url": c["url"], "score": round(c["score"], 3)}
        for c in contexts if c["item_id"] != "kg"]
    if kg_facts:
        trace["kg_facts"] = kg_facts[:15]
    return _final(out, cites, trace, t0)


async def _hydrate(item_ids: list[str]) -> dict[str, Item]:
    """检索命中后回查 DB，补齐 CWE/ATT&CK/ATLAS/版本等结构化字段"""
    if not item_ids:
        return {}
    async with get_session_factory()() as db:
        rows = (await db.execute(select(Item).where(Item.id.in_(item_ids)))).scalars().all()
        return {i.id: i for i in rows}


def _struct_line(i: Item) -> str:
    parts = [f"CVE:{','.join(i.cve_ids or [])}", f"严重度:{i.severity or '-'}"]
    if i.cwe_ids:
        parts.append(f"CWE:{','.join(i.cwe_ids)}")
    if i.attack_techniques:
        parts.append(f"ATT&CK:{','.join(i.attack_techniques)}")
    if i.atlas_techniques:
        parts.append(f"ATLAS:{','.join(i.atlas_techniques)}")
    if i.products:
        parts.append(f"产品:{','.join(i.products[:6])}")
    if i.affected_versions:
        parts.append(f"受影响版本:{i.affected_versions}")
    if i.is_kev:
        parts.append("KEV在野利用:是")
    if i.has_poc:
        parts.append("公开PoC:有")
    return "｜".join(parts)


async def _generate(question: str, history: list[dict], contexts: list[dict], trace_note: str = "") -> AnswerOut:
    ctx_txt = "\n\n".join(
        f"[{c['n']}] {c['title'] or ''}\nURL: {c['url'] or '-'}\n元数据: {c.get('meta')}\n{c['text']}"
        for c in contexts[:12])
    sys_p = """你是 AI 安全情报分析助手。基于给定证据回答，要求：
1. 引用证据用 [n] 标注；无证据支撑的内容不要编造
2. 证据不足时明确说"当前情报库信息有限"
3. 回答结构化：结论 → 关键事实 → 建议
4. 中文回答，技术名词保留原文
5. 输出 JSON: {"answer": "...", "confidence": 0-1, "followups": ["建议的追问"]}"""
    msgs = [{"role": "system", "content": sys_p},
            *[{"role": h["role"], "content": h["content"]} for h in history[-6:]],
            {"role": "user", "content": f"证据：\n{ctx_txt}\n\n问题：{question}"}]
    try:
        return await chat_structured(msgs, AnswerOut, max_retries=1)
    except Exception as e:  # noqa: BLE001
        log.warning("generate_structured_failed", error=str(e)[:120])
        raw = await chat(msgs, max_tokens=2000)
        return AnswerOut(answer=raw["content"], confidence=0.4)


def _format_item_block(item: Item, pocs: list, maps: list) -> dict:
    poc_txt = "\n".join(f"- {p.url} ({p.platform}, {p.credibility})" for p in pocs[:8])
    map_txt = ", ".join(sorted({x for m in maps for x in (m.capec_id, m.atlas_technique, m.attack_technique) if x}))
    atlas = ", ".join(item.atlas_techniques or [])
    attack = ", ".join(item.attack_techniques or [])
    enr = item.enrichment or {}
    text = f"""标题: {item.title_zh or item.title}
类型: {item.item_type} | 严重性: {item.severity} | CVSS: {item.cvss_v31_score} | EPSS: {item.epss_score}
KEV: {item.is_kev} | PoC: {item.has_poc} | AI层: {item.ai_layer}
CWE: {', '.join(item.cwe_ids or [])} | ATLAS: {atlas} | ATT&CK: {attack}
产品: {', '.join(item.products or [])} | 受影响版本: {item.affected_versions or '-'}
摘要: {item.summary_zh or item.summary or ''}
内容: {(item.content_text or '')[:2000]}
PoC:
{poc_txt or '无'}
富化: { {k: v.get('note') for k, v in enr.items() if isinstance(v, dict)} }"""
    return {"n": 1, "item_id": item.id, "title": item.title_zh or item.title,
            "url": item.url, "text": text, "meta": {"direct": True}, "score": 1.0}


def _cite(item: Item, n: int) -> dict:
    return {"n": n, "item_id": item.id, "title": item.title_zh or item.title, "url": item.url, "score": 1.0}


async def stream_answer(question: str, session_id: str | None = None,
                        history: list[dict] | None = None, deep: bool = True):
    """SSE 事件生成器：status → token → citations/trace → done"""
    yield {"type": "status", "data": {"msg": "正在检索情报库…"}}
    try:
        res = await answer(question, session_id, history)
    except Exception as e:  # noqa: BLE001
        log.error("qa_failed", error=str(e)[:300])
        yield {"type": "error", "data": {"error": "问答服务暂时不可用"}}
        return
    yield {"type": "trace", "data": {"trace": res["trace"]}}
    yield {"type": "citations", "data": {"citations": res["citations"]}}
    # 分段推送答案（伪流式：按句切）
    ans = res["answer"] or ""
    chunk = ""
    for ch in ans:
        chunk += ch
        if len(chunk) >= 24 or ch in "\n。；":
            yield {"type": "token", "data": {"t": chunk}}
            chunk = ""
    if chunk:
        yield {"type": "token", "data": {"t": chunk}}
    yield {"type": "done", "data": res}


def _final(out: AnswerOut, cites: list[dict], trace: dict, t0: float) -> dict:
    # 置信度校准：引用覆盖 + 证据分
    if cites:
        top = max((c["score"] for c in cites), default=0)
        cal = min(1.0, out.confidence * 0.6 + min(top, 1.0) * 0.4)
    else:
        cal = out.confidence * 0.5
    abstain = cal < 0.25
    if abstain:
        out.answer = "（置信度不足，无法给出可靠答案）\n\n" + out.answer
    return {
        "answer": out.answer, "confidence": round(cal, 3), "abstain": abstain,
        "followups": out.followups[:3], "citations": cites[:12],
        "trace": trace, "latency_ms": int((time.time() - t0) * 1000),
    }
