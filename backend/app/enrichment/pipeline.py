"""富化流水线编排：并发 worker fan-out → 确定性字段合并 + 子表幂等写回 + enrichment 审计"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.core.logging import get_logger
from app.db.models import AssetStat, Item, MappingLink, Paper, Poc
from app.db.session import get_session_factory
from app.enrichment import ai_classify, assets, chain, mappings, nlp, papers, poc, scorers

log = get_logger("enrich.pipeline")

# 执行顺序：确定性优先，LLM/检索类次之，依赖前序产出的最后
WORKERS = [
    ("scorers", scorers.run),
    ("mappings", mappings.run),
    ("poc", poc.run),
    ("papers", papers.run),
    ("assets", assets.run),
    ("nlp", nlp.run),
    ("chain", chain.run),
    ("ai_classify", ai_classify.run),
]

ROW_MODELS = {"pocs": Poc, "assets": AssetStat, "papers": Paper, "mappings": MappingLink}


async def enrich_item(item_id: str, dims: list[str] | None = None) -> dict:
    """对单条情报执行富化，返回各维度摘要。
    三阶段：读(detach)→并发 worker(不持会话)→写(短事务)——避免 180s LLM 调用期持行锁"""
    sf = get_session_factory()
    # ---- 阶段1：短事务读 + 加锁戳 + detach（跨进程互斥，15min 过期可窃取）----
    async with sf() as db:
        item = (await db.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
        if not item:
            return {"error": "item not found"}
        lock_ts = (item.extra or {}).get("_enrich_lock")
        if lock_ts:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(lock_ts)).total_seconds()
                if age < 900:
                    return {"skipped": "locked", "age_s": int(age)}
            except Exception:  # noqa: BLE001
                pass
        item.extra = {**(item.extra or {}), "_enrich_lock": datetime.now(timezone.utc).isoformat()}
        await db.commit()
        enrichment = dict(item.enrichment or {})
        db.expunge(item)

    wanted = set(dims) if dims else None
    changed_fields: set[str] = set()

    # ---- 阶段2：worker 扇出（纯计算/网络，无 DB 会话）----
    async def one(name, fn):
        if wanted and name not in wanted:
            return name, None
        try:
            return name, await asyncio.wait_for(fn(item, None), timeout=180)
        except Exception as e:  # noqa: BLE001
            log.error("worker_failed", item=item_id, worker=name, error=str(e)[:200])
            return name, {"status": "error", "confidence": 0.0, "note": str(e)[:300]}

    results = await asyncio.gather(*[one(n, f) for n, f in WORKERS])

    # ---- 阶段3：短事务写回（重取最新行，防覆盖并发更新）----
    async with sf() as db:
        item = (await db.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
        if not item:
            return {"error": "item deleted during enrich"}
        enrichment = {**(item.enrichment or {}), **enrichment}  # 并发安全合并

        for name, res in results:
            if res is None:
                continue
            enrichment[name] = {k: res.get(k) for k in ("status", "confidence", "note", "ts", "data_keys")}
            # 字段合并：worker 字段优先级低——只覆盖空值或明确更强的值
            for k, v in (res.get("fields") or {}).items():
                if v is None:
                    continue
                cur = getattr(item, k, None)
                if cur in (None, "", [], 0, 0.0, False) or k in ("epss_score", "epss_percentile", "is_kev", "has_poc", "ai_relevance_score"):
                    setattr(item, k, v)
                    changed_fields.add(k)
                elif k == "exploit_maturity" and _maturity_rank(v) > _maturity_rank(cur):
                    setattr(item, k, v)
            # extra 浅合并
            if res.get("extra"):
                item.extra = {**(item.extra or {}), **_json_safe(res["extra"])}
            # 子表幂等写回：delete+insert
            for rk, model in ROW_MODELS.items():
                rows = (res.get("rows") or {}).get(rk)
                if not rows:
                    continue
                await db.execute(delete(model).where(model.item_id == item_id))
                seen_keys = set()
                for r in rows[:50]:
                    key = r.get("url") or f"{r.get('title','')}-{r.get('cve_id')}-{r.get('capec_id')}-{r.get('atlas_technique')}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    db.add(model(item_id=item_id, **_filter_fields(model, r)))

        item.enrichment = enrichment
        item.extra = {k: v for k, v in (item.extra or {}).items() if k != "_enrich_lock"}
        item.updated_at = datetime.now(timezone.utc)

        # HITL：全 error/低置信/关键维度缺失 → needs_review
        errs = [k for k, v in enrichment.items() if isinstance(v, dict) and v.get("status") == "error"]
        confs = [v.get("confidence", 0) for v in enrichment.values() if isinstance(v, dict)]
        if len(errs) >= 3 or (confs and sum(confs) / len(confs) < 0.4):
            item.review_status = "needs_review"
        elif item.review_status == "needs_review":
            item.review_status = "auto"
        item.confidence = round(sum(confs) / len(confs), 3) if confs else item.confidence

        await db.commit()
        try:
            from app.core.metrics import enrich_runs
            status = "error" if errs else ("partial" if any(
                isinstance(v, dict) and v.get("status") == "partial" for v in enrichment.values()) else "ok")
            enrich_runs.labels(status=status).inc()
        except Exception:  # noqa: BLE001
            pass
        return {"item_id": item_id, "enrichment": enrichment,
                "review_status": item.review_status, "changed": sorted(changed_fields)}


def _json_safe(obj):
    """JSONB 安全化：datetime/其他不可序列化对象 → str"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _maturity_rank(v: str | None) -> int:
    return {"none": 0, "poc": 1, "weaponized": 2}.get(v or "", 0)


def _filter_fields(model, row: dict) -> dict:
    cols = {c.name for c in model.__table__.columns}
    return {k: v for k, v in row.items() if k in cols}


async def enrich_pending(limit: int = 30) -> int:
    """批量富化尚未富化的 item（按优先级排序）"""
    sf = get_session_factory()
    async with sf() as db:
        items = (await db.execute(
            select(Item).where(~Item.enrichment.has_key("scorers"))
            .order_by(Item.priority_score.desc().nullslast(), Item.first_seen_at.desc())
            .limit(limit))).scalars().all()
        ids = [i.id for i in items]
        # 补捞：任一维度 error 的条目重跑该维度（重试上限靠 review_status 兜底）
        stale = (await db.execute(
            select(Item).where(Item.enrichment != {})
            .order_by(Item.priority_score.desc().nullslast()).limit(limit))).scalars().all()
        for i in stale:
            err_dims = [k for k, v in (i.enrichment or {}).items()
                        if isinstance(v, dict) and v.get("status") == "error"]
            if err_dims:
                ids.append((i.id, err_dims))
    n = 0
    for ent in ids:
        iid, dims = (ent, None) if isinstance(ent, str) else ent
        try:
            await enrich_item(iid, dims=dims)
            n += 1
        except Exception as e:  # noqa: BLE001
            log.error("enrich_item_failed", item=iid, error=str(e)[:200])
    return n
