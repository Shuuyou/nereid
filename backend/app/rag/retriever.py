"""混合检索器：dense+sparse RRF → 交叉编码重排 → 去重聚合到 item 级"""
from __future__ import annotations

from app.core.logging import get_logger
from app.rag import embedder, qdrant

log = get_logger("rag.retriever")


async def retrieve(query: str, top_k: int = 8, rerank_top: int = 24,
                   do_rerank: bool = True, **filters) -> list[dict]:
    """返回 item 级证据：[{item_id,title,url,text,score,cve,...}]
    do_rerank=False 跳过重排——多子问场景先合并候选、单次重排，省 2/3 重排耗时"""
    dv = await embedder.embed_query(query)
    sv = (await embedder.sparse_texts([query]))[0]
    f = qdrant.build_filter(**{k: v for k, v in filters.items() if v})
    hits = await qdrant.hybrid_search(dv, sv, top_k=rerank_top, filters=f)
    if not hits:
        return []
    if do_rerank:
        docs = [h.get("text", "") for h in hits]
        try:
            ranked = await embedder.rerank(query, docs, top_n=min(len(docs), rerank_top))
            hits = [{**hits[i], "rerank_score": s} for i, s in ranked]
        except Exception as e:  # noqa: BLE001
            log.warning("rerank_failed", error=str(e)[:120])
    # 聚合到 item 级：同 item 取最高分 chunk，保留 top2 chunk 文本
    by_item: dict[str, dict] = {}
    for h in hits:
        iid = h.get("item_id")
        if not iid:
            continue
        rec = by_item.setdefault(iid, {**h, "chunks": []})
        if len(rec["chunks"]) < 2:
            rec["chunks"].append(h.get("text", ""))
        rec["score"] = max(rec["score"], h.get("rerank_score", h["score"]))
    out = sorted(by_item.values(), key=lambda r: r["score"], reverse=True)[:top_k]
    for r in out:
        r["text"] = "\n---\n".join(r.pop("chunks"))
    return out
