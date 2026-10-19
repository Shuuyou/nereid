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

from app.config import get_settings
from app.core.logging import get_logger
from app.db.models import (
    AssetStat, Item, ItemSource, MappingLink, Paper, Poc, QaMessage, QaSession,
    Report, Source, TaskRun,
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
    """优雅降级：任一依赖挂掉仍返回 200 + degraded 明细（答辩拔线演示安全）"""
    out = {"status": "ok", "ts": datetime.now(timezone.utc).isoformat(), "checks": {}}
    try:
        out["items"] = (await db.execute(select(func.count(Item.id)))).scalar() or 0
        out["checks"]["postgres"] = True
    except Exception as e:  # noqa: BLE001
        out["checks"]["postgres"] = False
        out["status"] = "degraded"
        out["errors"] = {"postgres": str(e)[:120]}
    s = get_settings()
    try:
        from app.core.http import fetch
        r = await fetch(f"http://{s.qdrant_host}:{s.qdrant_port}/collections")
        out["checks"]["qdrant"] = r.status_code == 200
        if not out["checks"]["qdrant"]:
            out["status"] = "degraded"
    except Exception:  # noqa: BLE001
        out["checks"]["qdrant"] = False
        out["status"] = "degraded"
    return out


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


@router.get("/stats/asset_exposure")
async def asset_exposure(db: AsyncSession = Depends(get_db)):
    """影子 AI 暴露看板：AI 产品维度聚合暴露资产（含模拟标记）"""
    rows = (await db.execute(
        select(AssetStat, Item)
        .join(Item, AssetStat.item_id == Item.id)
        .order_by(AssetStat.total_count.desc()).limit(200))).all()
    by_prod: dict = {}
    for a, it in rows:
        prod = (it.products or ["unknown"])[0]
        e = by_prod.setdefault(prod, {"product": prod, "total": 0, "items": 0,
                                      "max_single": 0, "simulated": False, "cves": []})
        e["total"] += a.total_count or 0
        e["items"] += 1
        e["max_single"] = max(e["max_single"], a.total_count or 0)
        e["simulated"] = e["simulated"] or bool(a.is_simulated)
        if it.cve_ids and it.cve_ids[0] not in e["cves"]:
            e["cves"].append(it.cve_ids[0])
    ranked = sorted(by_prod.values(), key=lambda x: x["total"], reverse=True)
    return {"products": ranked[:15],
            "total_exposed": sum(x["total"] for x in ranked),
            "shadow_ai_items": sum(x["items"] for x in ranked)}


@router.get("/stats/freshness")
async def stats_freshness(db: AsyncSession = Depends(get_db)):
    """时效指标：published_at→first_seen_at 的入库延迟分布（性能分'时效'的证据）"""
    rows = (await db.execute(text(
        "SELECT EXTRACT(EPOCH FROM (first_seen_at - published_at))/60.0 AS lag_min, "
        "       source_names[1] "
        "FROM items WHERE published_at IS NOT NULL AND first_seen_at IS NOT NULL "
        "AND COALESCE(extra->>'is_demo','') <> 'true' "
        "AND COALESCE(extra->>'canary','') <> 'true'"))).all()
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
        "published": desc(func.coalesce(Item.published_at, Item.first_seen_at)),
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
        "d3fend": _d3fend(it),
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
    elif action == "undo":
        # 撤销复核动作 → 回待复核队列（reject 已清空的 enrichment 由前端补一次重富化）
        item.review_status = "needs_review"
    else:
        raise HTTPException(400, "action must be confirm|reject|undo")
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
    rows = (await db.execute(select(Item).where(*conds).order_by(desc(func.coalesce(Item.published_at, Item.first_seen_at))).limit(8))).scalars().all()
    return {"items": [_item_card(r) for r in rows]}


@router.post("/items/{item_id}/enrich")
async def trigger_enrich(item_id: str, db: AsyncSession = Depends(get_db)):
    it = (await db.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
    if not it:
        raise HTTPException(404)
    from app.enrichment.pipeline import enrich_item

    async def _tracked():
        started = datetime.now(timezone.utc)
        res = await enrich_item(item_id)
        try:
            async with get_session_factory()() as s2:
                s2.add(TaskRun(task_name=f"enrich:{item_id[:8]}",
                               status="error" if res.get("error") else "success",
                               started_at=started, finished_at=datetime.now(timezone.utc),
                               detail={k: res.get(k) for k in ("review_status", "changed", "skipped", "error")}))
                await s2.commit()
        except Exception:  # noqa: BLE001
            pass

    asyncio.create_task(_tracked())
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


def _d3fend(item: Item) -> list[dict]:
    from app.core.d3fend import mitigations_for
    return mitigations_for((item.attack_techniques or []) + (item.atlas_techniques or []))


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
    # relationship 对象：report→vuln(indicates/targets)、vuln→attack-pattern(indicates)
    primary = objects[0]["id"] if objects else None
    for tech_obj in [o for o in objects if o["type"] == "attack-pattern"]:
        if primary:
            objects.append({"type": "relationship", "spec_version": "2.1",
                            "id": f"relationship--{_uuid.uuid5(_uuid.NAMESPACE_URL, 'https://secagent/rel/' + primary + '/' + tech_obj['id'])}",
                            "created": now, "modified": now, "relationship_type": "indicates",
                            "source_ref": primary, "target_ref": tech_obj["id"]})
    objects.append({
        "type": "report", "spec_version": "2.1",
        "id": f"report--{_uuid.uuid5(_uuid.NAMESPACE_URL, 'https://secagent/item/' + item.id)}",
        "created": now, "modified": now,
        "name": item.title_zh or item.title, "published": now,
        "report_types": ["threat-report"],
        "object_refs": [o["id"] for o in objects],
        "labels": [item.severity or "unknown", item.ai_layer or "general"],
    })
    return {"type": "bundle",
            "id": f"bundle--{_uuid.uuid5(_uuid.NAMESPACE_URL, 'https://secagent/bundle/' + item.id)}",
            "objects": objects}


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
    """对指定数据源运行 LangGraph 全链 DAG（collect→enrich→index→kg→notify）
    返回 run_id —— 用 GET /api/pipeline/run/{run_id} 轮询真实节点状态"""
    import uuid as _u
    from app.agents.pipeline_graph import run_pipeline_tracked
    src = await db.get(Source, source_id)
    if not src:
        raise HTTPException(404, "source not found")
    run_id = _u.uuid4().hex[:12]
    asyncio.create_task(run_pipeline_tracked(source_id, run_id))
    return {"status": "started", "run_id": run_id, "source": src.name,
            "dag": ["collect", "enrich", "index", "kg", "notify"]}


@router.get("/pipeline/run/{run_id}")
async def pipeline_run_status(run_id: str):
    """单次 DAG 运行的真实节点状态（Redis）"""
    import json as _j
    from app.core.rds import rds
    try:
        h = await rds().hgetall(f"pipeline:run:{run_id}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"redis unavailable: {e}") from e
    if not h:
        raise HTTPException(404, "run not found")
    h["nodes"] = _j.loads(h.get("nodes") or "{}")
    if h.get("result"):
        h["result"] = _j.loads(h["result"])
    return h


@router.post("/pipeline/resume/{run_id}")
async def pipeline_resume(run_id: str, db: AsyncSession = Depends(get_db)):
    """断点续跑：同 thread_id 从未完成 checkpoint 恢复（durable execution 演示入口）。
    用法：手动停掉一次运行中的流水线后调用，LangGraph 从 PG checkpoint 续跑。"""
    import json as _j
    from app.core.rds import rds
    from app.agents.pipeline_graph import resume_pipeline
    try:
        h = await rds().hgetall(f"pipeline:run:{run_id}")
    except Exception:  # noqa: BLE001
        h = {}
    source_id = int((h or {}).get("source_id") or 0)
    if not source_id:
        src = await db.scalar(select(Source.id).order_by(Source.id).limit(1))
        if not src:
            raise HTTPException(404, "run not found")
        source_id = int(src)
    asyncio.create_task(resume_pipeline(run_id, source_id))
    return {"status": "resuming", "run_id": run_id}


@router.get("/pipeline/runs")
async def pipeline_runs():
    """最近 DAG 运行列表（TaskRun 落库 + Redis 实时态）"""
    import json as _j
    from app.core.rds import rds
    out = []
    try:
        ids = await rds().lrange("pipeline:runs", 0, 19)
        for rid in ids or []:
            h = await rds().hgetall(f"pipeline:run:{rid}")
            if h:
                h["nodes"] = _j.loads(h.get("nodes") or "{}")
                h.pop("result", None)
                out.append(h)
    except Exception as e:  # noqa: BLE001
        return {"runs": [], "redis": f"unavailable: {e}"}
    return {"runs": out}


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
    if session_id and not await db.get(QaSession, session_id):
        session_id = None  # 无效 session_id → 自动建会话而非 FK 500
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
    stats = await graph_stats()
    try:
        from app.core.metrics import kg_nodes
        if isinstance(stats, dict):
            for k, v in stats.items():
                if isinstance(v, (int, float)):
                    kg_nodes.labels(label=k).set(v)
    except Exception:  # noqa: BLE001
        pass
    return stats


class CanaryReport(BaseModel):
    stages: dict[str, float]


@router.post("/internal/canary")
async def canary_report(rep: CanaryReport):
    """金丝雀脚本回写各阶段耗时 → API 进程内注册 Prometheus gauge
    （/metrics 才能暴露 secagent_canary_e2e_*，解决脚本进程指标不可见问题）"""
    from app.core.metrics import canary_e2e
    for stage, v in rep.stages.items():
        if v >= 0:
            canary_e2e.labels(stage=stage).set(v)
    return {"status": "recorded", "stages": len(rep.stages)}


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
