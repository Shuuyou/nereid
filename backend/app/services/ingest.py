"""Ingest 服务：raw 落库 → 规范化 → 去重 → 聚合为情报卡片 Item"""
from __future__ import annotations

from datetime import datetime, timezone

import trafilatura
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import RawItemData
from app.core.metrics import ingest_delay, item_freshness
from app.core.ids import extract_ids, simhash64, title_fingerprint, url_sha256
from app.core.logging import get_logger
from app.core.taxonomy import classify
from app.db.models import DedupCluster, Item, ItemSource, RawItem, Source
from app.services.dedup import find_match, register_minhash

log = get_logger("ingest")

TIER_RELIABILITY = {1: 0.95, 2: 0.9, 3: 0.75, 4: 0.6, 5: 0.4}


def extract_body(html_or_text: str | None, url: str | None = None) -> str | None:
    """trafilatura 正文提取（对 HTML 输入；纯文本原样返回）"""
    if not html_or_text:
        return None
    if "<" in html_or_text[:500]:
        try:
            out = trafilatura.extract(html_or_text, url=url, include_comments=False, include_tables=False)
            return out or html_or_text[:5000]
        except Exception:  # noqa: BLE001
            return html_or_text[:5000]
    return html_or_text


def _merge_list(a: list, b: list) -> list:
    return sorted(set(a or []) | set(b or []))


async def ingest_items(db: AsyncSession, source: Source, items: list[RawItemData]) -> dict:
    """批量入库+去重+聚合。返回统计。"""
    stats = {"received": len(items), "inserted": 0, "merged": 0, "new_items": 0, "errors": 0}
    new_items: list[Item] = []
    for data in items:
        try:
            async with db.begin_nested():  # SAVEPOINT：单条失败不污染整批
                item = await _ingest_one(db, source, data, stats)
            if item is not None and not (item.enrichment or {}).get("scorers") and item.id:
                new_items.append(item)
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            log.error("ingest_one_failed", source=source.name, title=(data.title or "")[:80], error=str(e)[:300])
    await db.commit()
    source.total_items = (source.total_items or 0) + stats["inserted"]
    await db.commit()
    # 下游：富化 → 索引 → KG（后台任务，不阻塞采集）；整批进队列保证大批量不漏
    stats["new_item_ids"] = [i.id for i in new_items]
    _post_process(stats["new_item_ids"])
    return stats


def _post_process(item_ids: list[str]) -> None:
    if not item_ids:
        return
    import asyncio

    async def _run():
        from app.enrichment.pipeline import enrich_item
        from app.rag.indexer import index_item
        from app.rag.kg import sync_item
        from sqlalchemy import select as _sel
        from app.db.session import get_session_factory
        # 实时推送前移：入库完成即广播（不等富化链），卡片先行、富化后字段由 detail 接口补
        async with get_session_factory()() as db:
            fresh = (await db.execute(_sel(Item).where(Item.id.in_(item_ids)))).scalars().all()
        for it in fresh[:50]:
            try:
                from app.api.routes import broadcast_new_item
                await broadcast_new_item(it)
            except Exception:  # noqa: BLE001
                pass
        sem = asyncio.Semaphore(4)  # 有限并发富化，防大批量打满 LLM/外部配额

        async def _one(iid):
            async with sem:
                await enrich_item(iid)
                await index_item(iid)
                async with get_session_factory()() as db:
                    it = (await db.execute(_sel(Item).where(Item.id == iid))).scalar_one_or_none()
                    if it:
                        await sync_item(it)
        results = await asyncio.gather(
            *[_one(iid) for iid in item_ids[:120]], return_exceptions=True)
        for iid, r in zip(item_ids[:120], results):
            if isinstance(r, Exception):
                log.warning("post_process_failed", item=iid, error=str(r)[:150])

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        asyncio.run(_run())


async def _ingest_one(db: AsyncSession, source: Source, data: RawItemData, stats: dict) -> Item | None:
    # 幂等检查
    if data.native_id:
        exists = (await db.execute(
            select(RawItem.id).where(RawItem.source_id == source.id, RawItem.native_id == data.native_id)
        )).scalar_one_or_none()
        if exists:
            stats["merged"] += 1
            return None

    content = extract_body(data.content_text, data.url)
    raw = RawItem(
        source_id=source.id, native_id=data.native_id,
        url=data.url, url_sha256=url_sha256(data.url),
        title=(data.title or "")[:2000], author=data.author,
        published_at=data.published_at, lang=data.lang or source.lang,
        content_text=content, raw=data.raw,
    )
    db.add(raw)
    await db.flush()
    stats["inserted"] += 1
    # 时效指标：披露→raw 落库
    if data.published_at:
        lag = (datetime.now(timezone.utc) - _aware(data.published_at)).total_seconds()
        if 0 <= lag < 30 * 86400:
            ingest_delay.labels(source=source.name).observe(lag)

    # 实体提取（文本 + 结构化字段并集）
    text_for_ids = " ".join(filter(None, [data.title, content]))
    ids = extract_ids(text_for_ids)
    for k, v in (("cve", data.cve_ids), ("ghsa", data.ghsa_ids), ("cwe", data.cwe_ids)):
        ids[k] = sorted(set(ids[k]) | {x.upper() for x in v})

    # 去重匹配
    match, method, score = await find_match(db, raw, ids)
    if match:
        item = match
        _merge_into(item, data, ids, source, method)
        raw.process_status = "clustered"
        stats["merged"] += 1
    else:
        item = _new_item(data, ids, source)
        db.add(item)
        await db.flush()
        stats["new_items"] += 1
        if item.published_at:
            lag = (item.first_seen_at - _aware(item.published_at)).total_seconds()
            if 0 <= lag < 30 * 86400:
                item_freshness.observe(lag)

    db.add(ItemSource(item_id=item.id, raw_item_id=raw.id, source_name=source.name, url=data.url, is_primary=(method == "new")))
    db.add(DedupCluster(raw_item_id=raw.id, item_id=item.id, match_method=method, match_score=score))
    register_minhash(raw)
    return item


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _base_reliability(source: Source) -> float:
    return TIER_RELIABILITY.get(source.tier, 0.5)


def _classify_item(title: str, content: str | None, products: list) -> dict:
    return classify(f"{title}\n{(content or '')[:3000]}", products)


def _priority(item: Item) -> float:
    """情报优先级：KEV×3 + EPSS×2 + CVSS + AI相关 + 多源印证"""
    s = 0.0
    if item.is_kev:
        s += 3.0
    s += (item.epss_score or 0) * 2
    s += (item.cvss_v31_score or item.cvss_v40_score or 0) / 10
    s += (item.ai_relevance_score or 0)
    s += min((item.source_count or 1) - 1, 3) * 0.15
    if item.has_poc:
        s += 0.5
    return round(s, 3)


def _new_item(data: RawItemData, ids: dict, source: Source) -> Item:
    content = data.content_text
    cls = _classify_item(data.title or "", content, data.products)
    it = Item(
        item_type=data.item_type,
        title=data.title or "", content_text=content, url=data.url, url_sha256=url_sha256(data.url),
        summary=(data.summary or (content or "")[:400]) or None,
        published_at=data.published_at,
        cve_ids=ids["cve"], ghsa_ids=ids["ghsa"], cnvd_ids=ids["cnvd"], cnnvd_ids=ids["cnnvd"],
        edb_ids=ids["edb"], cwe_ids=ids["cwe"],
        vendors=data.vendors, products=data.products,
        severity=data.severity, cvss_v31_score=data.cvss_v31_score, cvss_v31_vector=data.cvss_v31_vector,
        cvss_v40_score=data.cvss_v40_score, cvss_v40_vector=data.cvss_v40_vector,
        ai_relevance_score=cls["ai_relevance_score"], ai_layer=cls["ai_layer"],
        owasp_llm=cls["owasp_llm"], owasp_asi=cls["owasp_asi"],
        source_names=[source.name],
        reliability_score=_base_reliability(source),
        title_fingerprint=title_fingerprint(data.title or ""),
        simhash64=simhash64((data.title or "") + " " + (content or "")[:500]),
        extra={"atlas": ids["atlas"], "attack": ids["attack"], "arxiv": ids["arxiv"], "capec_ids": ids["capec"], "cpe": ids["cpe"]},
        attack_techniques=ids["attack"], atlas_techniques=ids["atlas"],
    )
    # KEV 源条目即权威在野利用标记（不等下游 worker）
    if source.source_type == "kev" or (data.raw or {}).get("kev"):
        it.is_kev = True
        it.exploit_maturity = "weaponized"
    it.priority_score = _priority(it)
    return it


def _merge_into(item: Item, data: RawItemData, ids: dict, source: Source, method: str) -> None:
    """多源合并：字段补全 + 可靠性提升 + 来源计数"""
    item.cve_ids = _merge_list(item.cve_ids, ids["cve"])
    item.ghsa_ids = _merge_list(item.ghsa_ids, ids["ghsa"])
    item.cnvd_ids = _merge_list(item.cnvd_ids, ids["cnvd"])
    item.cnnvd_ids = _merge_list(item.cnnvd_ids, ids["cnnvd"])
    item.edb_ids = _merge_list(item.edb_ids, ids["edb"])
    item.cwe_ids = _merge_list(item.cwe_ids, ids["cwe"])
    item.vendors = _merge_list(item.vendors, data.vendors)
    item.products = _merge_list(item.products, data.products)
    item.attack_techniques = _merge_list(item.attack_techniques, ids["attack"])
    item.atlas_techniques = _merge_list(item.atlas_techniques, ids["atlas"])
    if source.source_type == "kev" or (data.raw or {}).get("kev"):
        item.is_kev = True
        if (item.exploit_maturity or "none") == "none":
            item.exploit_maturity = "weaponized"
    if source.name not in (item.source_names or []):
        item.source_names = (item.source_names or []) + [source.name]
    item.source_count = len(item.source_names or [])
    # 高 tier 源补齐评分字段
    if data.cvss_v31_score and not item.cvss_v31_score:
        item.cvss_v31_score = data.cvss_v31_score
        item.cvss_v31_vector = data.cvss_v31_vector
    if data.cvss_v40_score and not item.cvss_v40_score:
        item.cvss_v40_score = data.cvss_v40_score
        item.cvss_v40_vector = data.cvss_v40_vector
    if data.severity and not item.severity:
        item.severity = data.severity
    # 结构化源正文更完整则更新；发布时间取最早
    if data.content_text and (not item.content_text or len(data.content_text) > len(item.content_text)):
        item.content_text = data.content_text
    if data.published_at and (not item.published_at or data.published_at < item.published_at):
        item.published_at = data.published_at
    item.updated_at = datetime.now(timezone.utc)
    # 可靠性：多源印证加分
    corroboration = min(0.15, 0.05 * (item.source_count - 1))
    item.reliability_score = min(1.0, max(item.reliability_score or 0.5, _base_reliability(source)) + corroboration)
    # AI 相关性重算（合并后信息更全）
    cls = _classify_item(item.title, item.content_text, item.products)
    item.ai_relevance_score = max(item.ai_relevance_score or 0, cls["ai_relevance_score"])
    item.ai_layer = item.ai_layer or cls["ai_layer"]
    item.owasp_llm = _merge_list(item.owasp_llm, cls["owasp_llm"])
    item.owasp_asi = _merge_list(item.owasp_asi, cls["owasp_asi"])
    item.priority_score = _priority(item)
