"""Qdrant 集合管理与检索（dense + BM42 sparse 混合向量）"""
from __future__ import annotations

import asyncio
from functools import lru_cache

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger("rag.qdrant")

COLLECTION = "intel_chunks"
DENSE = "dense"
SPARSE = "sparse"


@lru_cache
def client() -> AsyncQdrantClient:
    s = get_settings()
    return AsyncQdrantClient(host=s.qdrant_host, port=s.qdrant_port, grpc_port=s.qdrant_port + 1,
                             prefer_grpc=False, timeout=30)


async def ensure_collection() -> None:
    c = client()
    s = get_settings()
    names = {x.name for x in (await c.get_collections()).collections}
    if COLLECTION in names:
        return
    await c.create_collection(
        collection_name=COLLECTION,
        vectors_config={DENSE: qm.VectorParams(size=s.embedding_dim, distance=qm.Distance.COSINE)},
        sparse_vectors_config={SPARSE: qm.SparseVectorParams(index=qm.SparseIndexParams(on_disk=False))},
    )
    for f, t in (("item_id", qm.PayloadSchemaType.KEYWORD), ("cve", qm.PayloadSchemaType.KEYWORD),
                 ("cwe", qm.PayloadSchemaType.KEYWORD), ("product", qm.PayloadSchemaType.KEYWORD),
                 ("severity", qm.PayloadSchemaType.KEYWORD), ("item_type", qm.PayloadSchemaType.KEYWORD),
                 ("ai_layer", qm.PayloadSchemaType.KEYWORD), ("source_name", qm.PayloadSchemaType.KEYWORD),
                 ("published_at", qm.PayloadSchemaType.DATETIME), ("is_kev", qm.PayloadSchemaType.BOOL),
                 ("has_poc", qm.PayloadSchemaType.BOOL), ("ai_relevance", qm.PayloadSchemaType.FLOAT)):
        try:
            await c.create_payload_index(COLLECTION, f, t)
        except Exception:  # noqa: BLE001
            pass
    log.info("qdrant_collection_ready", collection=COLLECTION)


async def upsert_chunks(points: list[qm.PointStruct]) -> None:
    if not points:
        return
    c = client()
    for i in range(0, len(points), 64):
        batch = points[i:i + 64]
        for attempt in range(4):
            try:
                await c.upsert(COLLECTION, batch)
                break
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt * 2)


def build_filter(cve: str | None = None, severity: list[str] | None = None,
                 item_type: list[str] | None = None, ai_layer: str | None = None,
                 since: str | None = None, must_keywords: list[str] | None = None):
    cond = []
    if cve:
        cond.append(qm.FieldCondition(key="cve", match=qm.MatchValue(value=cve)))
    if severity:
        cond.append(qm.FieldCondition(key="severity", match=qm.MatchAny(any=severity)))
    if item_type:
        cond.append(qm.FieldCondition(key="item_type", match=qm.MatchAny(any=item_type)))
    if ai_layer:
        cond.append(qm.FieldCondition(key="ai_layer", match=qm.MatchValue(value=ai_layer)))
    if since:
        cond.append(qm.FieldCondition(key="published_at",
                                      range=qm.DatetimeRange(gte=since)))  # type: ignore[arg-type]
    if must_keywords:
        for kw in must_keywords:
            cond.append(qm.FieldCondition(key="text", match=qm.MatchText(text=kw)))
    return qm.Filter(must=cond) if cond else None


async def hybrid_search(query_dense: list[float], query_sparse: dict,
                        top_k: int = 20, filters=None,
                        prefetch: int = 50) -> list[dict]:
    """dense+sparse 两路 prefetch → RRF 融合"""
    c = client()
    try:
        res = await c.query_points(
            COLLECTION,
            prefetch=[
                qm.Prefetch(query=query_dense, using=DENSE, limit=prefetch, filter=filters),
                qm.Prefetch(
                    query=qm.SparseVector(indices=query_sparse["indices"], values=query_sparse["values"]),
                    using=SPARSE, limit=prefetch, filter=filters),
            ],
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return [{"id": str(p.id), "score": p.score or 0.0, **(p.payload or {})} for p in res.points]
    except Exception as e:  # noqa: BLE001
        log.warning("hybrid_rrf_failed", error=str(e)[:200])
        return await search_dense(query_dense, top_k, filters)


async def search_dense(vec: list[float], top_k: int = 10, filters=None, exclude_id=None) -> list[dict]:
    c = client()
    try:
        res = await c.query_points(COLLECTION, query=vec, using=DENSE, limit=top_k + (1 if exclude_id else 0),
                                   query_filter=filters, with_payload=True)
        out = [{"id": str(p.id), "score": p.score or 0.0, **(p.payload or {})} for p in res.points]
        return [h for h in out if h.get("item_id") != exclude_id][:top_k]
    except Exception as e:  # noqa: BLE001
        log.warning("dense_search_failed", error=str(e)[:150])
        return []


async def delete_item(item_id: str) -> None:
    c = client()
    for attempt in range(4):
        try:
            await c.delete(COLLECTION, qm.FilterSelector(
                filter=qm.Filter(must=[qm.FieldCondition(key="item_id", match=qm.MatchValue(value=item_id))])))
            return
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            await asyncio.sleep(2 ** attempt * 2)


async def count() -> int:
    c = client()
    try:
        return (await c.count(COLLECTION, exact=True)).count
    except Exception:  # noqa: BLE001
        return 0
