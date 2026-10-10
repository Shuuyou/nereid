"""rag 侧 embedding 入口：passage/query 分离"""
from __future__ import annotations

from app.core import embeddings as _emb


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """文档侧 embedding"""
    return await _emb.embed_dense(texts, is_query=False)


async def embed_query(q: str) -> list[float]:
    """查询侧 embedding（带 instruction 前缀）"""
    v = await _emb.embed_dense([q], is_query=True)
    return v[0]


async def sparse_texts(texts: list[str]):
    return await _emb.embed_sparse(texts)


async def rerank(query: str, docs: list[str], top_n: int = 12):
    return await _emb.rerank(query, docs, top_n)
