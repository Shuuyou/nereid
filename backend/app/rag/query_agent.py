"""QueryAgent：LangGraph 编排的深度问答
路由 → (CVE 直连 | 检索+KG 扩展) → 重排 → 生成(引用) → 置信度/拒答 → trace
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.ids import extract_ids
from app.core.llm import chat, chat_structured, chat_stream
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


AGENT_TOOLS = [
    {"type": "function", "function": {
        "name": "retrieve_intel",
        "description": "混合检索情报库（向量+词面融合+重排）。按语义/关键词找相关情报条目",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "检索式（中文/英文/产品名/CVE均可）"},
            "top_k": {"type": "integer", "default": 6}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "kg_expand",
        "description": "知识图谱关联扩展：由实体（CVE/CWE/Product/ATT&CK技术）出发找关联情报与实体，适用于多跳推理",
        "parameters": {"type": "object", "properties": {
            "entities": {"type": "array", "items": {"type": "string"}},
            "hops": {"type": "integer", "default": 2}}, "required": ["entities"]}}},
    {"type": "function", "function": {
        "name": "get_item_detail",
        "description": "按 CVE 编号取完整情报卡（CVSS/EPSS/KEV/PoC/受影响版本/攻击链/富化摘要）",
        "parameters": {"type": "object", "properties": {
            "cve": {"type": "string", "description": "如 CVE-2024-37032"}}, "required": ["cve"]}}},
    {"type": "function", "function": {
        "name": "list_kev",
        "description": "列出情报库中被 CISA KEV 收录（确认遭在野利用）的条目清单",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "default": 15}}}}},
]

AGENT_SYS = """你是 AI 安全情报分析 Agent，可自主调用工具收集证据。
规则：
1. 分析问题后决定调用哪些工具（可多轮调用），收集足够证据后停止
2. 已有证据能覆盖问题时不再调用，直接结束
3. 每次调用有明确目的（查具体漏洞/找关联/枚举清单/多跳桥接）
"""

# DeepSeek 兼容参数：chat() 若支持 parallel_tool_calls 则透传（单轮决策即可并行发多个
# tool_calls）；不支持时保持现状——单轮返回的多个 tool_calls 仍由 gather 并发执行。
_PTC_KW: dict = {}
try:
    if "parallel_tool_calls" in inspect.signature(chat).parameters:
        _PTC_KW = {"parallel_tool_calls": True}
except Exception:  # noqa: BLE001
    pass


async def _agent_chat(msgs: list[dict]) -> dict:
    """单轮 Agent 决策调用（工具并行声明 + 失败优雅回退）"""
    if _PTC_KW:
        try:
            return await chat(msgs, tools=AGENT_TOOLS, max_tokens=1024, **_PTC_KW)
        except Exception as e:  # noqa: BLE001
            log.warning("parallel_tool_calls_unsupported", error=str(e)[:120])
    return await chat(msgs, tools=AGENT_TOOLS, max_tokens=1024)


async def _none():
    return None


async def _nil() -> list:
    return []


async def _guard(coro, default, stage: str = ""):
    """并发容错包装：单路失败返回 default，不拖垮 asyncio.gather"""
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        log.warning("concurrent_stage_failed", stage=stage, error=str(e)[:120])
        return default


async def _kg_expand(entities: list[str], hops: int = 2, limit: int = 40) -> list[dict]:
    """KG 实体扩展（空实体短路 + 容错；结果由 kg.entity_expand 进程内 TTL 缓存）"""
    if not entities:
        return []
    try:
        return await kg.entity_expand(list(entities), hops=hops, limit=limit)
    except Exception as e:  # noqa: BLE001
        log.warning("kg_expand_failed", error=str(e)[:120])
        return []


def _dedupe_facts(facts: list[dict]) -> list[dict]:
    """跨批次 KG 事实去重（与 kg.entity_expand 内部口径一致）"""
    seen, out = set(), []
    for f in facts:
        k = (f.get("item_id"), f.get("rel"), f.get("nid") or f.get("via_cwe"))
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _kg_context(kg_facts: list[dict], n: int) -> dict:
    """KG 关联事实 → 证据上下文块"""
    facts_txt = "\n".join(
        f"- {f.get('title','?')} [{f.get('item_id')}] 关联:{f.get('rel')} via {f.get('nid') or f.get('via_cwe','')}"
        for f in kg_facts[:15])
    return {"n": n, "item_id": "kg", "title": "知识图谱关联事实",
            "url": None, "text": facts_txt, "meta": {"kind": "kg_facts"}, "score": 0.6}


def _tool_args(tc: dict) -> dict:
    try:
        return json.loads((tc.get("function") or {}).get("arguments") or "{}")
    except Exception:  # noqa: BLE001
        return {}


async def _merged_rerank(question: str, hits: list[dict]) -> None:
    """候选合并后的单次交叉编码重排：截断 512 字（就地写 rerank_score）。
    注意：rerank 分是交叉编码 logit（负值域），与 RRF score（正值域）不同量纲——
    调用方必须先按 score 预排序取 top 段再调本函数，最终排序两段分开做。"""
    if len(hits) <= 1:
        return
    try:
        from app.rag import embedder
        docs = [(h.get("text") or "")[:512] for h in hits]
        ranked = await embedder.rerank(question, docs, top_n=len(docs))
        for idx, s in ranked:
            hits[idx]["rerank_score"] = s
    except Exception as e:  # noqa: BLE001
        log.warning("merged_rerank_failed", error=str(e)[:120])


async def _exec_tool(name: str, args: dict) -> dict:
    """执行一个工具调用，返回 {kind, title, summary, evidence}"""
    try:
        if name == "retrieve_intel":
            hits = await retriever.retrieve(str(args.get("query", ""))[:300],
                                            top_k=int(args.get("top_k") or 6), do_rerank=False)
            ev = [{"item_id": h["item_id"], "title": h.get("title_zh") or h.get("title"),
                   "url": h.get("url"), "text": h.get("text", "")[:1400],
                   "score": h.get("rerank_score", h["score"]), "kind": "retrieve"}
                  for h in hits]
            return {"kind": "retrieve", "title": f"检索:{args.get('query', '')[:30]}",
                    "summary": f"命中 {len(ev)} 条", "evidence": ev}
        if name == "kg_expand":
            facts = await kg.entity_expand([str(x) for x in args.get("entities", [])][:6],
                                         hops=min(int(args.get("hops") or 2), 3), limit=30)
            txt = "\n".join(f"- {f.get('title','?')} 关联:{f.get('rel')} via {f.get('nid') or f.get('via_cwe','')}"
                            for f in facts[:15]) or "无关联"
            return {"kind": "kg", "title": "图谱扩展",
                    "summary": txt[:1200], "evidence": [
                        {"item_id": f.get("item_id"), "title": f.get("title"), "url": f.get("url"),
                         "text": f.get("rel", ""), "score": 0.55, "kind": "kg"} for f in facts]}
        if name == "get_item_detail":
            d = await _cve_direct(str(args.get("cve", "")).upper())
            if not d:
                return {"kind": "detail", "title": args.get("cve"), "summary": "库内未收录", "evidence": []}
            blk = _format_item_block(d["item"], d["pocs"], d["mappings"])
            blk["kind"] = "detail"
            return {"kind": "detail", "title": args.get("cve"), "summary": "命中完整情报卡",
                    "evidence": [blk]}
        if name == "list_kev":
            k = await _kev_facts(limit=int(args.get("limit") or 15))
            if not k:
                return {"kind": "kev", "title": "KEV清单", "summary": "库内无 KEV 条目", "evidence": []}
            k["kind"] = "kev"
            return {"kind": "kev", "title": "KEV清单", "summary": k["text"][:1200],
                    "evidence": [k]}
    except Exception as e:  # noqa: BLE001
        return {"kind": name, "title": name, "summary": f"工具错误:{str(e)[:80]}", "evidence": []}
    return {"kind": name, "title": name, "summary": "未知工具", "evidence": []}


_STEP_MSG = {
    "extract": "解析问题实体…", "cve_direct": "命中 CVE 直连情报卡",
    "route": "规划检索路径…", "kev_facts": "注入 KEV 在野利用事实",
    "tool_call": "Agent 调用工具…", "agent_evidence": "汇总工具证据",
    "retrieve": "混合检索+重排…", "kg_expand": "知识图谱多跳扩展",
    "context": "组装证据上下文…", "generate": "DeepSeek 生成答案…",
    "fast_path": "快速通道检索…", "fallback_retrieve": "补充检索…",
    "agent_stop": "Agent 完成证据收集", "prepare_error": "流水线降级（部分证据）",
}


async def _agent_evidence(question: str, history: list[dict], step) -> list[dict]:
    """Agent 工具调用循环：1 轮决策 + 并行 tool_calls（gather 并发执行）；
    仅当去重证据命中 <2 条时才允许第 2 轮（省一整轮 LLM 决策延迟）"""
    msgs = [{"role": "system", "content": AGENT_SYS},
            *[{"role": h["role"], "content": h["content"]} for h in history[-4:]],
            {"role": "user", "content": question}]
    evidence: list[dict] = []
    for rnd in range(2):
        if rnd and len({e.get("item_id") for e in evidence if e.get("item_id")}) >= 2:
            step("agent_stop", round=rnd, reason="evidence_sufficient")
            break
        try:
            out = await _agent_chat(msgs)
        except Exception as e:  # noqa: BLE001
            step("agent_error", error=str(e)[:120])
            break
        tcs = out.get("tool_calls") or []
        if not tcs:
            step("agent_stop", round=rnd, reason=out.get("finish_reason"))
            break
        msgs.append({"role": "assistant", "content": out.get("content") or "",
                     "tool_calls": [{"id": t.get("id"), "type": "function",
                                     "function": t.get("function")} for t in tcs]})
        results = await asyncio.gather(*[
            _exec_tool((t.get("function") or {}).get("name") or "?", _tool_args(t))
            for t in tcs])
        for t, res in zip(tcs, results):
            fn = t.get("function") or {}
            step("tool_call", tool=fn.get("name"),
                 args=str(fn.get("arguments"))[:150], hits=len(res["evidence"]))
            msgs.append({"role": "tool", "tool_call_id": t.get("id"),
                         "content": json.dumps(res["summary"], ensure_ascii=False)[:1200]})
            evidence.extend(res["evidence"])
    return evidence


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


async def _prepare(question: str, session_id: str | None = None,
                   history: list[dict] | None = None, top_k: int = 8,
                   deep: bool = True, progress=None) -> tuple[list[dict], list[dict], dict, float]:
    """流水线准备阶段：返回 (contexts, cites, trace, t0)。生成由调用方决定（同步/流式）

    深路径三路并发：route ∥ 原句混合检索 ∥ KG 实体扩展（实体在 extract_ids 后即可知，
    不等 route）；route 返回后再并发 agent_evidence ∥ 子问句补检 ∥ 路由实体 KG 扩展。
    全函数容错：任何异常回传 (partial_contexts, cites, trace, t0) 并在 trace 记 error，
    不再上抛——保证 partial trace 随 done 事件下发。"""
    t0 = time.time()
    history = history or []
    trace: dict = {"steps": []}
    contexts: list[dict] = []
    cites: list[dict] = []

    def step(name, **kw):
        ev = {"step": name, "ts": datetime.now(timezone.utc).isoformat(),
              "ms": int((time.time() - t0) * 1000),
              "status": kw.pop("status", "error" if "error" in kw else "ok"), **kw}
        trace["steps"].append(ev)
        if progress is not None:
            try:
                progress.put_nowait({"step": name, "ms": ev["ms"],
                    "msg": _STEP_MSG.get(name, name),
                    **{k: v for k, v in kw.items() if k in ("tool", "hits", "n", "route", "facts")}})
            except asyncio.QueueFull:
                pass

    try:
        # ---- 1. 实体直提（确定性优先）----
        ids = extract_ids(question)
        cves = ids["cve"]
        cwes = ids["cwe"]
        all_ids = ids["cve"] + ids["ghsa"] + ids["edb"] + ids["cwe"] + ids["atlas"]
        step("extract", cves=cves, cwes=cwes, ids=all_ids[:10])

        # ---- 2. CVE 直连（绕过完整 RAG，高置信；补轻量 KG 扩展保证 trace ≥3 步）----
        if cves:
            direct = await _cve_direct(cves[0])
            if direct:
                step("cve_direct", cve=cves[0], found=True)
                kg_facts = await _kg_expand(cves, hops=1, limit=20)
                step("kg_expand", facts=len(kg_facts), entities=cves)
                item = direct["item"]
                contexts = [_format_item_block(item, direct["pocs"], direct["mappings"])]
                cites = [_cite(item, 1)]
                if kg_facts:
                    contexts.append(_kg_context(kg_facts, len(contexts) + 1))
                    trace["kg_facts"] = kg_facts[:15]
                step("context", n=len(contexts))
                step("generate")
                trace["note"] = f"CVE 直连 {cves[0]}"
                return contexts, cites, trace, t0

        # ---- 2.5 快速通道（deep=False：跳过路由/Agent/KG，直接检索生成，≤10s）----
        if not deep:
            step("fast_path")
            hits = await _guard(retriever.retrieve(question, top_k=top_k, do_rerank=False),
                                [], "retrieve")
            hit_items = await _guard(_hydrate([h["item_id"] for h in hits]), {}, "hydrate")
            for i, h in enumerate(hits, 1):
                it = hit_items.get(h["item_id"])
                struct = _struct_line(it) if it else ""
                contexts.append({"n": i, "item_id": h["item_id"], "title": h.get("title_zh") or h.get("title"),
                                 "url": h.get("url"), "text": (struct + "\n" + h.get("text", ""))[:1800],
                                 "meta": {"cve": h.get("cve")}, "score": h.get("rerank_score", h["score"])})
            cites = [{"n": c["n"], "item_id": c["item_id"], "title": c["title"], "url": c["url"],
                      "score": round(c["score"], 3)} for c in contexts]
            step("context", n=len(contexts))
            step("generate")
            return contexts, cites, trace, t0

        # ---- 3. 三路并发：路由 ∥ 原句混合检索 ∥ KG 种子实体扩展（+KEV 意图直查）----
        kg_seed = (cves + cwes + ids["ghsa"] + ids["edb"] + ids["atlas"])[:8]
        kev_intent = bool(re.search(r"kev|在野利用|已被利用|actively exploited", question, re.I))
        routed, base_hits, kg_facts, kev_ctx = await asyncio.gather(
            _route(question, history),
            _guard(retriever.retrieve(question, top_k=top_k, do_rerank=False), [], "retrieve"),
            _kg_expand(kg_seed, hops=2, limit=40),
            _guard(_kev_facts(), None, "kev") if kev_intent else _none(),
        )
        sub_qs = routed.sub_questions[:3] or [question]
        step("route", route=routed.route, sub_questions=sub_qs, entities=routed.entities)
        if kev_ctx:
            step("kev_facts", n=kev_ctx["meta"]["n_items"])

        # ---- 4. 第二轮并发：Agent 工具循环 ∥ 子问句补充检索 ∥ 路由实体 KG 扩展 ----
        extra_ents = [e for e in (routed.entities or [])[:5] if e not in kg_seed]
        sub_extra = [q for q in sub_qs if q != question]
        filters = routed.filters or {}
        agent_ev, sub_hit_lists, kg_facts2 = await asyncio.gather(
            _guard(_agent_evidence(question, history, step), [], "agent")
            if routed.route != "general" else _nil(),
            asyncio.gather(*[
                _guard(retriever.retrieve(q, top_k=top_k, do_rerank=False, **filters),
                       [], "retrieve")
                for q in sub_extra]),
            _kg_expand(extra_ents, hops=2, limit=40),
        )
        kg_facts = _dedupe_facts(kg_facts + kg_facts2)

        all_hits: list[dict] = []
        seen_iid: set[str] = set()
        for h in agent_ev:
            if h.get("item_id") and h["item_id"] not in seen_iid:
                seen_iid.add(h["item_id"])
                all_hits.append(h)
        step("agent_evidence", n=len(all_hits))
        n_agent = len(all_hits)
        for hits in (base_hits, *sub_hit_lists):
            for h in hits:
                if h.get("item_id") and h["item_id"] not in seen_iid:
                    seen_iid.add(h["item_id"])
                    all_hits.append(h)
        step("fallback_retrieve", hits=len(all_hits), added=len(all_hits) - n_agent)

        # ---- 5. 合并重排与 DB 结构化水合并发 ----
        # 量纲纪律：rerank_score 是 logit（负值）≠ RRF score（正值），不得混排。
        # 先按 RRF 预排序 → rerank 只处理真实 top 候选段 → 段内按 logit 排，尾部按 RRF 追加
        all_hits.sort(key=lambda h: h["score"], reverse=True)
        rerank_seg, tail_hits = all_hits[:24], all_hits[24:]
        hit_items, _ = await asyncio.gather(
            _guard(_hydrate([h["item_id"] for h in all_hits]), {}, "hydrate"),
            _merged_rerank(question, rerank_seg),
        )
        rerank_seg.sort(key=lambda h: h.get("rerank_score", h["score"]), reverse=True)
        all_hits = (rerank_seg + tail_hits)[:top_k * 2]
        step("retrieve", hits=len(all_hits), sub_qs=len(sub_qs))
        step("kg_expand", facts=len(kg_facts), entities=(kg_seed + extra_ents)[:8])

        # ---- 6. 组装上下文（检索文本 + 结构化字段 + KG 事实 + KEV 清单）----
        for i, h in enumerate(all_hits, 1):
            it = hit_items.get(h["item_id"])
            struct = _struct_line(it) if it else ""
            contexts.append({"n": i, "item_id": h["item_id"], "title": h.get("title_zh") or h.get("title"),
                             "url": h.get("url"), "text": (struct + "\n" + h.get("text", ""))[:1800],
                             "meta": {k: h.get(k) for k in ("cve", "severity", "cvss", "epss", "is_kev", "item_type", "published_at")},
                             "score": h.get("rerank_score", h["score"])})
        if kg_facts:
            contexts.append(_kg_context(kg_facts, len(contexts) + 1))
        if kev_ctx:
            kev_ctx = {**kev_ctx, "n": len(contexts) + 1}
            contexts.append(kev_ctx)
        step("context", n=len(contexts))
        step("generate")

        cites = [
            {"n": c["n"], "item_id": c["item_id"], "title": c["title"], "url": c["url"],
             "score": round(c["score"], 3),
             "snippet": (c["text"].split("\n", 1)[1] if "\n" in c["text"] else c["text"])[:200]}
            for c in contexts if c["item_id"] != "kg"]
        if kg_facts:
            trace["kg_facts"] = kg_facts[:15]
        return contexts, cites, trace, t0
    except Exception as e:  # noqa: BLE001
        log.error("prepare_failed", error=str(e)[:300])
        try:
            step("prepare_error", error=str(e)[:200])
            if not cites and contexts:
                cites = [{"n": c["n"], "item_id": c["item_id"], "title": c["title"],
                          "url": c["url"], "score": round(c.get("score", 0), 3),
                          "snippet": (c["text"].split("\n", 1)[1] if "\n" in c["text"] else c["text"])[:200]}
                         for c in contexts if c["item_id"] != "kg"]
            if len(trace["steps"]) < 3:  # 兜底：任意路径 trace ≥3 步
                step("context", n=len(contexts))
                step("generate")
        except Exception:  # noqa: BLE001
            pass
        return contexts, cites, trace, t0


async def answer(question: str, session_id: str | None = None,
                 history: list[dict] | None = None, top_k: int = 8,
                 deep: bool = True, progress=None) -> dict:
    """主入口（非流式，评测用）：返回 {answer, citations, trace, confidence, latency_ms}"""
    contexts, cites, trace, t0 = await _prepare(
        question, session_id, history, top_k, deep, progress)
    route = next((s.get("route") for s in trace.get("steps", []) if s.get("route")), "general")
    out = await _generate(question, history or [], contexts, route=route)
    return _final(out, cites, trace, t0)


async def _kev_facts(limit: int = 30) -> dict | None:
    """KEV 收录 + AI 相关条目的确定性清单（供"哪些被在野利用"类问题）"""
    async with get_session_factory()() as db:
        items = (await db.execute(
            select(Item).where(Item.is_kev.is_(True))
            .order_by(Item.ai_relevance_score.desc().nullslast(),
                      Item.epss_score.desc().nullslast()).limit(limit))).scalars().all()
    if not items:
        return None
    lines = []
    for i in items:
        flags = [f"AI相关度{i.ai_relevance_score:.2f}" if i.ai_relevance_score else "AI相关度低",
                 f"{i.severity}", f"EPSS{i.epss_score or 0:.2f}"]
        if i.attack_techniques:
            flags.append(f"ATT&CK:{','.join(i.attack_techniques[:3])}")
        if i.cwe_ids:
            flags.append(f"CWE:{','.join(i.cwe_ids[:2])}")
        if i.products:
            flags.append(f"产品:{','.join(i.products[:3])}")
        lines.append(f"- {','.join(i.cve_ids or [])} {i.title[:80]} [{'｜'.join(flags)}]")
    return {"n": 0, "item_id": "kev_facts", "title": f"CISA KEV 收录情报清单（库内 {len(items)} 条）",
            "url": None, "text": "以下为情报库中被 CISA KEV 收录（已遭在野利用）的条目：\n" + "\n".join(lines),
            "meta": {"kind": "kev_facts", "n_items": len(items)}, "score": 0.95}


async def _hydrate(item_ids: list[str]) -> dict[str, Item]:
    """检索命中后回查 DB，补齐 CWE/ATT&CK/ATLAS/版本等结构化字段"""
    if not item_ids:
        return {}
    async with get_session_factory()() as db:
        rows = (await db.execute(select(Item).where(Item.id.in_(item_ids)))).scalars().all()
        return {i.id: i for i in rows}


def _cap_ids(ids: list | None, k: int = 6) -> str:
    """证据侧枚举预聚合：>k 个同类 ID 只给前 k 个 + 总数（防模型把 30 个 CVE 铺进正文）"""
    ids = ids or []
    if len(ids) <= k:
        return ",".join(ids)
    return ",".join(ids[:k]) + f" 等{len(ids)}个"


def _struct_line(i: Item) -> str:
    parts = [f"CVE:{_cap_ids(i.cve_ids)}", f"严重度:{i.severity or '-'}"]
    if i.cwe_ids:
        parts.append(f"CWE:{_cap_ids(i.cwe_ids)}")
    if i.attack_techniques:
        parts.append(f"ATT&CK:{_cap_ids(i.attack_techniques)}")
    if i.atlas_techniques:
        parts.append(f"ATLAS:{_cap_ids(i.atlas_techniques)}")
    if i.products:
        parts.append(f"产品:{','.join(i.products[:6])}")
    if i.affected_versions:
        parts.append(f"受影响版本:{i.affected_versions}")
    if i.is_kev:
        parts.append("KEV在野利用:是")
    if i.has_poc:
        parts.append("公开PoC:有")
    return "｜".join(parts)


# 分类型回答形态（route → answer form），GraphRAG/Claude 式塑形
_FORM: dict[str, str] = {
    "vuln_lookup": "实体研判：首行给定性（严重度·是否KEV在野·有无公开PoC），随后关键属性、影响面，需要时给处置建议",
    "comparison": "对比：先一句结论，再用简表（≤6行）对比关键维度",
    "multi_hop": "分析：先 1-2 句直接结论，再列证据链要点；只有内容真正多维时才分小节",
    "trend": "枚举统计：先给命中总数与时间范围，再列要点条目",
    "general": "简答：直接回答，通常 2-5 句；除非问题确实多维，否则不分节",
}

_SYS_BODY = """你是资深安全情报分析师，在分析师工作台中回答同行的问题。

输出纪律：
1. 首行直接给答案（BLUF）——不重复问题、不要"根据提供的信息"式开场
2. 回答形态：{form}
3. 默认连贯段落、最小化格式；只有内容真正多维时才用小节/表格；一句话问题一句话答
4. 枚举纪律：同类实体（CVE/CWE/IOC/技术等）超过5个时，正文只写"共N个"+最多3个代表样例+"等"——总数与范围必须保留，但禁止逐条堆叠 ID
5. 引用证据用 [n] 内联标注；无证据支撑的内容不要编造
6. 证据不足时直说"当前情报库未收录相关信息"并指出缺什么，不要硬答
7. 中文回答，CVE/CWE/版本号等技术标识保留原文
8. 答完即停——不写"总结/综上所述"，不追加未被问到的建议
9. 拿不准时用"很可能/可能/尚不确定"等分级措辞，不要裸写百分比概率"""


def _sys_for(route: str, json_tail: str = "") -> str:
    return _SYS_BODY.format(form=_FORM.get(route, _FORM["general"])) + json_tail


async def _generate(question: str, history: list[dict], contexts: list[dict],
                    route: str = "general", trace_note: str = "") -> AnswerOut:
    ctx_txt = "\n\n".join(
        f"[{c['n']}] {c['title'] or ''}\nURL: {c['url'] or '-'}\n元数据: {c.get('meta')}\n{c['text']}"
        for c in contexts[:12])
    sys_p = _sys_for(route, '\n10. 输出 JSON: {"answer": "...", "confidence": 0-1, "followups": ["建议的追问"]}')
    # 消息顺序固定 system→证据→history→问题：证据块前置，前缀缓存友好
    msgs = [{"role": "system", "content": sys_p},
            {"role": "user", "content": f"证据：\n{ctx_txt}"},
            *[{"role": h["role"], "content": h["content"]} for h in history[-6:]],
            {"role": "user", "content": f"问题：{question}"}]
    try:
        return await chat_structured(msgs, AnswerOut, max_retries=1)
    except Exception as e:  # noqa: BLE001
        log.warning("generate_structured_failed", error=str(e)[:120])
        raw = await chat(msgs, max_tokens=2000)
        return AnswerOut(answer=raw["content"], confidence=0.4)


async def _generate_stream(question: str, history: list[dict], contexts: list[dict],
                           route: str = "general"):
    """真流式生成：yield 文本 delta"""
    ctx_txt = "\n\n".join(
        f"[{c['n']}] {c['title'] or ''}\nURL: {c['url'] or '-'}\n元数据: {c.get('meta')}\n{c['text']}"
        for c in contexts[:12])
    # 消息顺序固定 system→证据→history→问题：证据块前置，前缀缓存友好
    msgs = [{"role": "system", "content": _sys_for(route, "\n10. 直接输出答案正文（markdown），不要 JSON、不要前后缀")},
            {"role": "user", "content": f"证据：\n{ctx_txt}"},
            *[{"role": h["role"], "content": h["content"]} for h in history[-6:]],
            {"role": "user", "content": f"问题：{question}"}]
    async for piece in chat_stream(msgs, max_tokens=3000):
        yield piece


def _format_item_block(item: Item, pocs: list, maps: list) -> dict:
    poc_txt = "\n".join(f"- {p.url} ({p.platform}, {p.credibility})" for p in pocs[:8])
    map_txt = ", ".join(sorted({x for m in maps for x in (m.capec_id, m.atlas_technique, m.attack_technique) if x}))[:400]
    atlas = _cap_ids(item.atlas_techniques)
    attack = _cap_ids(item.attack_techniques)
    enr = item.enrichment or {}
    text = f"""标题: {item.title_zh or item.title}
类型: {item.item_type} | 严重性: {item.severity} | CVSS: {item.cvss_v31_score} | EPSS: {item.epss_score}
KEV: {item.is_kev} | PoC: {item.has_poc} | AI层: {item.ai_layer}
CWE: {_cap_ids(item.cwe_ids)} | ATLAS: {atlas} | ATT&CK: {attack}
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
    """SSE：status(实时进度) → trace/citations → token(真流式) → done"""
    yield {"type": "status", "data": {"msg": "正在检索情报库…"}}
    progress: asyncio.Queue = asyncio.Queue(maxsize=64)
    task = asyncio.create_task(_prepare(question, session_id, history, deep=deep, progress=progress))
    while not task.done():
        try:
            ev = await asyncio.wait_for(progress.get(), timeout=0.5)
            yield {"type": "status", "data": ev}
        except asyncio.TimeoutError:
            yield {"type": "status", "data": {"msg": "分析中…"}}
    while not progress.empty():
        yield {"type": "status", "data": progress.get_nowait()}
    try:
        contexts, cites, trace, t0 = task.result()
    except Exception as e:  # noqa: BLE001
        log.error("qa_failed", error=str(e)[:300])
        yield {"type": "error", "data": {"error": "问答服务暂时不可用"}}
        yield {"type": "done", "data": {"answer": "", "confidence": 0.0, "abstain": True,
                                       "error": True, "citations": [], "trace": {}}}
        return
    yield {"type": "trace", "data": {"trace": trace}}
    yield {"type": "citations", "data": {"citations": cites}}
    yield {"type": "status", "data": {"msg": "DeepSeek 生成答案…"}}
    # 真流式：LLM delta 直通 SSE（首 token 延迟即感知延迟）
    route = next((s.get("route") for s in trace.get("steps", []) if s.get("route")), "general")
    ans = ""
    try:
        async for piece in _generate_stream(question, history or [], contexts, route=route):
            ans += piece
            yield {"type": "token", "data": {"t": piece}}
    except Exception as e:  # noqa: BLE001
        log.error("generate_stream_failed", error=str(e)[:200])
        yield {"type": "error", "data": {"error": "答案生成中断"}}
        yield {"type": "done", "data": {"answer": ans or "", "confidence": 0.0, "abstain": True,
                                       "error": True, "citations": cites[:12], "trace": trace}}
        return
    # 置信度校准（引用覆盖+证据分，与 _final 同口径）
    top = max((c["score"] for c in cites), default=0)
    conf = round(min(1.0, 0.55 + min(top, 1.0) * 0.45), 3) if cites else 0.3
    abstain = conf < 0.25
    if abstain:
        ans = "（置信度不足，无法给出可靠答案）\n\n" + ans
    _observe_qa(trace, time.time() - t0)
    res = {"answer": ans, "confidence": conf, "abstain": abstain,
           "followups": [], "citations": cites[:12], "trace": trace,
           "latency_ms": int((time.time() - t0) * 1000)}
    yield {"type": "done", "data": res}


def _observe_qa(trace: dict, lat: float) -> None:
    from app.core.metrics import qa_latency, qa_queries, qa_route_latency
    try:
        route = next((s.get("route") for s in trace["steps"] if s.get("route")), "direct")
        qa_queries.labels(route=route).inc()
        qa_latency.observe(lat)
        steps = trace["steps"]
        for a, b in zip(steps, steps[1:]):
            stage_dur = (datetime.fromisoformat(b["ts"]) - datetime.fromisoformat(a["ts"])).total_seconds()
            if stage_dur > 0:
                qa_route_latency.labels(stage=b["step"]).observe(stage_dur)
    except Exception:  # noqa: BLE001
        pass


def _final(out: AnswerOut, cites: list[dict], trace: dict, t0: float) -> dict:
    lat = time.time() - t0
    _observe_qa(trace, lat)
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
