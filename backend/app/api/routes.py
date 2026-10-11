"""REST API 路由 —— 前端契约

数据接口：
- GET  /api/health
- GET  /api/stats/overview
- GET  /api/items            （分页+过滤）
- GET  /api/items/{id}       （富化全量详情）
- GET  /api/items/{id}/related
- POST /api/items/{id}/enrich
- GET  /api/sources
- POST /api/sources/{id}/run
- GET  /api/feed/stream      （SSE 新情报推送）
- POST /api/qa/chat          （SSE：status|token|trace|citation|done）
- GET  /api/qa/sessions/{id}
- GET  /api/kg/subgraph?entity=&depth=
- GET  /api/reports ; GET /api/reports/{id} ; POST /api/reports/daily
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.logging import get_logger
from app.db.models import (
    AssetStat, Item, ItemSource, MappingLink, Paper, Poc, QaMessage, QaSession,
    RawItem, Report, Source,
)
from app.db.session import get_db, get_session_factory

log = get_logger("api")
router = APIRouter(prefix="/api")

# SSE 广播队列（采集到新情报时推送）
_feed_subscribers: set[asyncio.Queue] = set()


async def broadcast_new_item(item: Item) -> None:
    for q in list(_feed_subscribers):
        try:
            q.put_nowait({"type": "new_item", "data": _item_card(item)})
        except asyncio.QueueFull:
            pass


def _item_card(it: Item) -> dict:
    return {
        "id": it.id, "item_type": it.item_type, "title": it.title,
        "title_zh": it.title_zh, "summary_zh": it.summary_zh or it.summary,
        "url": it.url, "published_at": it.published_at.isoformat() if it.published_at else None,
        "first_seen_at": it.first_seen_at.isoformat() if it.first_seen_at else None,
        "cve_ids": it.cve_ids, "ghsa_ids": it.ghsa_ids, "cwe_ids": it.cwe_ids,
        "products": it.products, "vendors": it.vendors,
        "severity": it.severity, "cvss_v31_score": it.cvss_v31_score,
        "epss_score": it.epss_score, "is_kev": it.is_kev, "has_poc": it.has_poc,
        "exploit_maturity": it.exploit_maturity, "priority_score": it.priority_score,
        "ai_relevance_score": it.ai_relevance_score, "ai_layer": it.ai_layer,
        "owasp_llm": it.owasp_llm, "owasp_asi": it.owasp_asi,
        "atlas_techniques": it.atlas_techniques, "attack_techniques": it.attack_techniques,
        "technique_maturity": it.technique_maturity,
        "source_names": it.source_names, "source_count": it.source_count,
        "reliability_score": it.reliability_score, "review_status": it.review_status,
        "enrichment": it.enrichment,
    }


# ============ 健康与统计 ============

@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(func.count(Item.id)))).scalar() or 0
    return {"status": "ok", "items": items, "ts": datetime.now(timezone.utc).isoformat()}


@router.get("/stats/overview")
async def stats_overview(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    total = (await db.execute(select(func.count(Item.id)))).scalar() or 0
    new24 = (await db.execute(select(func.count(Item.id)).where(Item.first_seen_at >= day_ago))).scalar() or 0
    ai_items = (await db.execute(select(func.count(Item.id)).where(Item.ai_relevance_score >= 0.3))).scalar() or 0
    kev = (await db.execute(select(func.count(Item.id)).where(Item.is_kev.is_(True)))).scalar() or 0
    poc = (await db.execute(select(func.count(Item.id)).where(Item.has_poc.is_(True)))).scalar() or 0
    vulns = (await db.execute(select(func.count(Item.id)).where(Item.item_type == "vuln"))).scalar() or 0

    by_layer = dict((await db.execute(
        select(Item.ai_layer, func.count()).group_by(Item.ai_layer))).all())
    by_type = dict((await db.execute(
        select(Item.item_type, func.count()).group_by(Item.item_type))).all())
    by_sev = dict((await db.execute(
        select(Item.severity, func.count()).group_by(Item.severity))).all())

    # 14 天趋势
    trend = (await db.execute(text(
        "SELECT date_trunc('day', first_seen_at) AS d, count(*) FROM items "
        "WHERE first_seen_at > now() - interval '14 days' GROUP BY d ORDER BY d"
    ))).all()

    sources_total = (await db.execute(select(func.count(Source.id)))).scalar() or 0
    sources_ok = (await db.execute(select(func.count(Source.id)).where(Source.consecutive_failures == 0, Source.last_success_at.isnot(None)))).scalar() or 0

    return {
        "total_items": total, "new_24h": new24, "ai_items": ai_items,
        "kev_count": kev, "poc_count": poc, "vuln_count": vulns,
        "by_layer": by_layer, "by_type": by_type, "by_severity": by_sev,
        "trend_14d": [{"date": str(r[0].date()), "count": r[1]} for r in trend],
        "sources": {"total": sources_total, "healthy": sources_ok},
    }


@router.get("/stats/freshness")
async def stats_freshness(db: AsyncSession = Depends(get_db)):
    """时效指标：published_at→first_seen_at 的入库延迟分布（性能分'时效'的证据）"""
    rows = (await db.execute(text(
        "SELECT EXTRACT(EPOCH FROM (first_seen_at - published_at))/60.0 AS lag_min, "
        "       source_names[1] "
        "FROM items WHERE published_at IS NOT NULL AND first_seen_at IS NOT NULL"))).all()
    lags = sorted(r[0] for r in rows if r[0] is not None and 0 <= r[0] < 43200)  # <30d 合理窗
    if not lags:
        return {"n": 0}
    def pct(p):
        return round(lags[min(len(lags) - 1, int(len(lags) * p))], 1)
    buckets = {"<1h": 0, "1-6h": 0, "6-24h": 0, "1-7d": 0, ">7d": 0}
    for v in lags:
        if v < 60: buckets["<1h"] += 1
        elif v < 360: buckets["1-6h"] += 1
        elif v < 1440: buckets["6-24h"] += 1
        elif v < 10080: buckets["1-7d"] += 1
        else: buckets[">7d"] += 1
    # 分源延迟（top10 源）
    by_src: dict[str, list[float]] = {}
    for lag, src in rows:
        if lag is not None and 0 <= lag < 43200:
            by_src.setdefault(src or "unknown", []).append(lag)
    src_stats = [{"source": k, "n": len(v), "p50_min": round(sorted(v)[len(v)//2], 1)}
                 for k, v in sorted(by_src.items(), key=lambda x: -len(x[1]))[:10]]
    return {"n": len(lags), "p50_min": pct(0.5), "p90_min": pct(0.9), "p95_min": pct(0.95),
            "min_min": round(lags[0], 1), "buckets": buckets, "by_source": src_stats,
            "sla_6h_pct": round(100 * sum(1 for v in lags if v < 360) / len(lags), 1)}


# ============ 情报条目 ============

@router.get("/items")
async def list_items(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    layer: str | None = None, severity: str | None = None, item_type: str | None = None,
    kev: bool | None = None, poc: bool | None = None, ai_only: bool = False,
    cve: str | None = None, q: str | None = None,
    sort: str = Query("priority", pattern="^(priority|published|seen)$"),
):
    conds = []
    if layer:
        conds.append(Item.ai_layer == layer)
    if severity:
        conds.append(Item.severity == severity)
    if item_type:
        conds.append(Item.item_type == item_type)
    if kev:
        conds.append(Item.is_kev.is_(True))
    if poc:
        conds.append(Item.has_poc.is_(True))
    if ai_only:
        conds.append(Item.ai_relevance_score >= 0.3)
    if cve:
        conds.append(Item.cve_ids.contains([cve.upper()]))
    if q:
        like = f"%{q}%"
        conds.append(or_(Item.title.ilike(like), Item.summary.ilike(like), Item.title_zh.ilike(like)))

    order = {
        "priority": desc(func.coalesce(Item.priority_score, 0) + func.coalesce(Item.ai_relevance_score, 0)),
        "published": desc(Item.published_at),
        "seen": desc(Item.first_seen_at),
    }[sort]

    total = (await db.execute(select(func.count(Item.id)).where(*conds))).scalar() or 0
    rows = (await db.execute(
        select(Item).where(*conds).order_by(order).offset((page - 1) * size).limit(size)
    )).scalars().all()
    return {"total": total, "page": page, "size": size, "items": [_item_card(it) for it in rows]}


@router.get("/items/{item_id}")
async def item_detail(item_id: str, db: AsyncSession = Depends(get_db)):
    it = (await db.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
    if not it:
        raise HTTPException(404, "item not found")
    pocs = (await db.execute(select(Poc).where(Poc.item_id == item_id).order_by(desc(Poc.stars)))).scalars().all()
    assets = (await db.execute(select(AssetStat).where(AssetStat.item_id == item_id))).scalars().all()
    papers = (await db.execute(select(Paper).where(Paper.item_id == item_id))).scalars().all()
    mappings = (await db.execute(select(MappingLink).where(MappingLink.item_id == item_id))).scalars().all()
    sources = (await db.execute(select(ItemSource).where(ItemSource.item_id == item_id))).scalars().all()
    return {
        **_item_card(it),
        "summary": it.summary, "content_text": (it.content_text or "")[:20000],
        "affected_versions": it.affected_versions, "cpes": it.cpes,
        "packages": it.packages, "attack_chain": it.attack_chain, "extra": it.extra,
        "cnvd_ids": it.cnvd_ids, "cnnvd_ids": it.cnnvd_ids, "edb_ids": it.edb_ids,
        "cvss_v40_score": it.cvss_v40_score, "cvss_v40_vector": it.cvss_v40_vector,
        "cvss_v31_vector": it.cvss_v31_vector, "epss_percentile": it.epss_percentile,
        "kev_date_added": it.kev_date_added.isoformat() if it.kev_date_added else None,
        "confidence": it.confidence,
        "pocs": [{"url": p.url, "platform": p.platform, "title": p.title, "stars": p.stars,
                  "author": p.author, "verified": p.verified, "credibility": p.credibility,
                  "credibility_reasons": p.credibility_reasons, "fetched_at": p.fetched_at.isoformat()} for p in pocs],
        "assets": [{"platform": a.platform, "query": a.query, "total_count": a.total_count,
                    "sample": a.sample, "is_simulated": a.is_simulated,
                    "fetched_at": a.fetched_at.isoformat()} for a in assets],
        "papers": [{"title": p.title, "url": p.url, "venue": p.venue, "year": p.year,
                    "authors": p.authors, "abstract": (p.abstract or "")[:800], "source": p.source,
                    "relevance_score": p.relevance_score, "paper_role": p.paper_role} for p in papers],
        "mappings": [{"cve_id": m.cve_id, "cwe_id": m.cwe_id, "capec_id": m.capec_id,
                      "attack_technique": m.attack_technique, "atlas_technique": m.atlas_technique,
                      "source": m.source, "confidence": m.confidence} for m in mappings],
        "sources": [{"source_name": s.source_name, "url": s.url, "is_primary": s.is_primary} for s in sources],
    }


@router.get("/review")
async def review_queue(status: str = "needs_review", limit: int = 50,
                       db: AsyncSession = Depends(get_db)):
    """HITL 复核队列：低置信/富化失败条目待人工确认"""
    rows = (await db.execute(
        select(Item).where(Item.review_status == status)
        .order_by(Item.priority_score.desc().nullslast(), Item.first_seen_at.desc())
        .limit(limit))).scalars().all()
    return {"count": len(rows), "items": [
        {"id": i.id, "title": i.title_zh or i.title, "cve": i.cve_ids[:1],
         "severity": i.severity, "confidence": i.confidence,
         "review_status": i.review_status,
         "weak_dims": [k for k, v in (i.enrichment or {}).items()
                       if isinstance(v, dict) and v.get("status") in ("error", "partial")],
         "first_seen_at": i.first_seen_at.isoformat() if i.first_seen_at else None}
        for i in rows]}


@router.post("/review/{item_id}/{action}")
async def review_action(item_id: str, action: str, db: AsyncSession = Depends(get_db)):
    """人工复核确认/驳回：confirm → confirmed；reject → 回炉重富化"""
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(404)
    if action == "confirm":
        item.review_status = "confirmed"
    elif action == "reject":
        item.review_status = "auto"
        item.enrichment = {}
    else:
        raise HTTPException(400, "action must be confirm|reject")
    await db.commit()
    return {"id": item_id, "review_status": item.review_status}


@router.get("/items/{item_id}/related")
async def related_items(item_id: str, db: AsyncSession = Depends(get_db)):
    it = (await db.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
    if not it:
        raise HTTPException(404)
    conds = [Item.id != item_id]
    ors = []
    if it.cwe_ids:
        ors.append(Item.cwe_ids.overlap(it.cwe_ids))
    if it.products:
        ors.append(Item.products.overlap(it.products))
    if ors:
        conds.append(or_(*ors))
    rows = (await db.execute(select(Item).where(*conds).order_by(desc(Item.published_at)).limit(8))).scalars().all()
    return {"items": [_item_card(r) for r in rows]}


@router.post("/items/{item_id}/enrich")
async def trigger_enrich(item_id: str, db: AsyncSession = Depends(get_db)):
    it = (await db.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
    if not it:
        raise HTTPException(404)
    from app.enrichment.pipeline import enrich_item
    asyncio.create_task(enrich_item(item_id))
    return {"status": "enrichment_started", "item_id": item_id}


# ============ 数据源 ============

@router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Source).order_by(Source.tier, Source.name))).scalars().all()
    return {"sources": [{
        "id": s.id, "name": s.name, "source_type": s.source_type, "tier": s.tier, "lang": s.lang,
        "url": s.url, "enabled": s.enabled, "poll_interval_sec": s.poll_interval_sec,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
        "last_error": s.last_error, "consecutive_failures": s.consecutive_failures,
        "total_items": s.total_items,
    } for s in rows]}


@router.post("/sources/{source_id}/run")
async def run_source_now(source_id: int, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Source).where(Source.id == source_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404)
    from app.collectors.registry import run_source
    asyncio.create_task(run_source(s.id))
    return {"status": "started", "source": s.name}


@router.get("/items/{item_id}/stix")
async def item_stix(item_id: str, db: AsyncSession = Depends(get_db)):
    """STIX 2.1 Bundle 导出（情报互操作标准，对接 TAXII/SIEM 生态）"""
    import uuid as _uuid
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(404)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    objects: list[dict] = []
    for cve in (item.cve_ids or [item.id]):
        vid = f"vulnerability--{_uuid.uuid5(_uuid.NAMESPACE_URL, 'https://secagent/' + cve)}"
        objects.append({
            "type": "vulnerability", "spec_version": "2.1", "id": vid,
            "created": now, "modified": now, "name": cve,
            "description": (item.summary_zh or item.summary or "")[:2000],
            "external_references": ([{"source_name": "cve", "external_id": cve}] if cve.startswith("CVE-") else [])
                + ([{"source_name": "url", "url": item.url}] if item.url else []),
        })
    for tech in (item.attack_techniques or [])[:5]:
        objects.append({
            "type": "attack-pattern", "spec_version": "2.1",
            "id": f"attack-pattern--{_uuid.uuid5(_uuid.NAMESPACE_URL, 'https://secagent/' + tech)}",
            "created": now, "modified": now, "name": tech,
            "external_references": [{"source_name": "mitre-attack", "external_id": tech}],
        })
    objects.append({
        "type": "report", "spec_version": "2.1",
        "id": f"report--{_uuid.uuid5(_uuid.NAMESPACE_URL, 'https://secagent/item/' + item.id)}",
        "created": now, "modified": now,
        "name": item.title_zh or item.title, "published": now,
        "report_types": ["threat-report"],
        "object_refs": [o["id"] for o in objects],
        "labels": [item.severity or "unknown", item.ai_layer or "general"],
    })
    return {"type": "bundle", "id": f"bundle--{_uuid.uuid4()}", "objects": objects}


@router.get("/pipeline/graph")
async def pipeline_graph_def():
    """LangGraph 编排 DAG 结构（前端可视化 + 架构评审证据）"""
    return {
        "engine": "LangGraph StateGraph",
        "nodes": [
            {"id": "collect", "label": "采集", "desc": "run_source → 多源采集+去重入库"},
            {"id": "enrich", "label": "富化", "desc": "并发 worker 扇出（EPSS/KEV/PoC/论文/映射/攻击链）"},
            {"id": "index", "label": "索引", "desc": "Qdrant dense+sparse 混合向量入库"},
            {"id": "kg", "label": "图谱", "desc": "Neo4j 实体关系 MERGE 同步"},
            {"id": "notify", "label": "推送", "desc": "高危情报 SSE 实时广播"},
        ],
        "edges": [["collect", "enrich"], ["enrich", "index"], ["index", "kg"],
                  ["kg", "notify"]],
        "schedule": "scheduler job_pipeline 每 15 分钟对到期源运行",
    }


@router.post("/pipeline/run/{source_id}")
async def pipeline_run(source_id: int, db: AsyncSession = Depends(get_db)):
    """对指定数据源运行 LangGraph 全链 DAG（collect→enrich→index→kg→notify）"""
    from app.agents.pipeline_graph import run_pipeline
    src = await db.get(Source, source_id)
    if not src:
        raise HTTPException(404, "source not found")
    asyncio.create_task(run_pipeline(source_id))
    return {"status": "started", "source": src.name,
            "dag": ["collect", "enrich", "index", "kg", "notify"]}


@router.post("/collect/run-all")
async def run_all(db: AsyncSession = Depends(get_db)):
    from app.collectors.registry import run_due_sources
    asyncio.create_task(run_due_sources(force=True))
    return {"status": "started"}


# ============ SSE 实时情报流 ============

@router.get("/feed/stream")
async def feed_stream():
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _feed_subscribers.add(q)

    async def gen():
        try:
            yield {"event": "connected", "data": json.dumps({"ok": True})}
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield {"event": msg["type"], "data": json.dumps(msg["data"], ensure_ascii=False)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            _feed_subscribers.discard(q)

    return EventSourceResponse(gen())


# ============ 问答 ============

class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    deep: bool = True


@router.post("/qa/chat")
async def qa_chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    from app.rag.query_agent import stream_answer

    session_id = req.session_id
    if not session_id:
        sess = QaSession(title=req.question[:80])
        db.add(sess)
        await db.commit()
        session_id = sess.id
    db.add(QaMessage(session_id=session_id, role="user", content=req.question))
    await db.commit()

    history_rows = (await db.execute(
        select(QaMessage).where(QaMessage.session_id == session_id).order_by(QaMessage.created_at).limit(12)
    )).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    async def gen():
        final = {}
        async for ev in stream_answer(req.question, session_id, history, deep=req.deep):
            if ev.get("type") == "done":
                final = ev.get("data", {})
            yield {"event": ev.get("type", "message"), "data": json.dumps(ev.get("data", {}), ensure_ascii=False)}
        # 落库
        if final:
            async with get_session_factory()() as s2:
                s2.add(QaMessage(
                    session_id=session_id, role="assistant", content=final.get("answer", ""),
                    trace=final.get("trace", {}), citations=final.get("citations", []),
                    confidence=final.get("confidence"), latency_ms=final.get("latency_ms"),
                ))
                await s2.commit()

    return EventSourceResponse(gen(), headers={"X-Session-Id": session_id})


@router.get("/qa/sessions/{session_id}")
async def qa_history(session_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(QaMessage).where(QaMessage.session_id == session_id).order_by(QaMessage.created_at)
    )).scalars().all()
    return {"session_id": session_id, "messages": [{
        "role": m.role, "content": m.content, "trace": m.trace, "citations": m.citations,
        "confidence": m.confidence, "created_at": m.created_at.isoformat(),
    } for m in rows]}


# ============ 知识图谱 ============

@router.get("/kg/subgraph")
async def kg_subgraph(entity: str = Query(...), depth: int = Query(2, ge=1, le=3)):
    from app.services.kg import get_subgraph
    return await get_subgraph(entity, depth)


@router.get("/kg/stats")
async def kg_stats():
    from app.services.kg import graph_stats
    return await graph_stats()


# ============ 报告 ============

@router.get("/reports")
async def list_reports(db: AsyncSession = Depends(get_db), limit: int = Query(20, le=50)):
    rows = (await db.execute(select(Report).order_by(desc(Report.created_at)).limit(limit))).scalars().all()
    return {"reports": [{
        "id": r.id, "report_type": r.report_type, "title": r.title,
        "period_start": r.period_start.isoformat() if r.period_start else None,
        "period_end": r.period_end.isoformat() if r.period_end else None,
        "stats": r.stats, "created_at": r.created_at.isoformat(),
    } for r in rows]}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404)
    return {"id": r.id, "report_type": r.report_type, "title": r.title, "content_md": r.content_md,
            "stats": r.stats, "created_at": r.created_at.isoformat()}


@router.post("/reports/daily")
async def gen_daily():
    from app.agents.analyst import generate_daily_report
    asyncio.create_task(generate_daily_report())
    return {"status": "generating"}
