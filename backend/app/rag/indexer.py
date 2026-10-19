"""Item → chunk → 向量入库（幂等：先删后插）"""
from __future__ import annotations

import hashlib

from qdrant_client.http import models as qm
from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import Item
from app.db.session import get_session_factory
from app.rag import embedder, qdrant

log = get_logger("rag.indexer")

MAX_CHUNK = 900
OVERLAP = 120


def chunk_text(text: str) -> list[str]:
    """按段落切分 + 滑窗合并（中英混排友好）"""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= MAX_CHUNK:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) > MAX_CHUNK:
                step = MAX_CHUNK - OVERLAP
                chunks.extend(p[i:i + MAX_CHUNK] for i in range(0, len(p), step))
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks or [text[:MAX_CHUNK]]


def _payload(item: Item, chunk: str, idx: int) -> dict:
    return {
        "item_id": item.id, "chunk_idx": idx, "text": chunk,
        "title": (item.title or "")[:400], "title_zh": (item.title_zh or "")[:400],
        "url": item.url, "item_type": item.item_type,
        "cve": item.cve_ids or [], "cwe": item.cwe_ids or [],
        "product": item.products or [], "vendor": item.vendors or [],
        "severity": item.severity, "is_kev": bool(item.is_kev),
        "has_poc": bool(item.has_poc), "ai_layer": item.ai_layer,
        "ai_relevance": item.ai_relevance_score or 0.0,
        "source_name": (item.source_names or [None])[0],
        "published_at": (item.published_at or item.first_seen_at).isoformat()
                        if (item.published_at or item.first_seen_at) else None,
        "epss": item.epss_score, "cvss": item.cvss_v31_score,
        "summary_zh": (item.summary_zh or "")[:800],
    }


def _pid(item_id: str, idx: int) -> str:
    """确定性 point id（幂等重插）"""
    h = hashlib.md5(f"{item_id}:{idx}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


async def index_item(item: Item | str) -> int:
    sf = get_session_factory()
    if isinstance(item, str):
        async with sf() as db:
            item = (await db.execute(select(Item).where(Item.id == item))).scalar_one_or_none()
            if not item:
                return 0
    body = "\n".join(x for x in [
        item.title_zh or item.title, item.summary_zh or item.summary,
        (item.content_text or "")[:8000]] if x)
    chunks = chunk_text(body)
    if not chunks:
        return 0
    content_hash = hashlib.md5(body.encode()).hexdigest()[:16]
    if (item.extra or {}).get("indexed_hash") == content_hash:
        return 0  # 内容未变，跳过（幂等增量）
    await qdrant.ensure_collection()
    vecs = await embedder.embed_texts(chunks)
    sparses = await embedder.sparse_texts(chunks)
    points = [
        qm.PointStruct(id=_pid(item.id, i),
                       vector={qdrant.DENSE: vecs[i], qdrant.SPARSE: sparses[i]},
                       payload=_payload(item, chunks[i], i))
        for i in range(len(chunks))]
    # 先 upsert（确定性 id 覆盖同名旧块），再清残留旧块：崩溃窗口内检索不丢数据
    await qdrant.upsert_chunks(points)
    await qdrant.delete_item_except(item.id, [p.id for p in points])
    # 标记已索引（免迁移，存 extra）
    async with sf() as db:
        it = await db.get(Item, item.id)
        if it:
            it.extra = {**(it.extra or {}), "indexed_hash": content_hash}
            await db.commit()
    try:
        from app.core.metrics import index_size
        info = await qdrant.client().get_collection(qdrant.COLLECTION)
        index_size.set(info.points_count or 0)
    except Exception:  # noqa: BLE001
        pass
    log.info("item_indexed", item=item.id, chunks=len(points))
    return len(points)


async def index_pending(limit: int = 50) -> int:
    async with get_session_factory()() as db:
        items = (await db.execute(select(Item).order_by(Item.first_seen_at.desc()).limit(limit * 4))).scalars().all()
    n = 0
    for it in items:
        try:
            if await index_item(it):
                n += 1
                if n >= limit:
                    break
        except Exception as e:  # noqa: BLE001
            log.warning("index_item_failed", item=it.id, error=str(e)[:150])
    return n
