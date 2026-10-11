"""rag 侧 embedding 入口：passage/query 分离 + 查询向量 TTL 缓存"""
from __future__ import annotations

import time
from collections import OrderedDict

from app.core import embeddings as _emb

_QCACHE: OrderedDict[str, tuple[float, list[float]]] = OrderedDict()
_QCACHE_TTL = 600.0  # 10min
_QCACHE_MAX = 256


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """文档侧 embedding"""
    return await _emb.embed_dense(texts, is_query=False)


async def embed_query(q: str) -> list[float]:
    """查询侧 embedding（带 instruction 前缀，TTL 缓存）"""
    key = q.strip()
    hit = _QCACHE.get(key)
    if hit and time.time() - hit[0] < _QCACHE_TTL:
        _QCACHE.move_to_end(key)
        return hit[1]
    v = await _emb.embed_dense([key], is_query=True)
    _QCACHE[key] = (time.time(), v[0])
    if len(_QCACHE) > _QCACHE_MAX:
        _QCACHE.popitem(last=False)
    return v[0]


async def sparse_texts(texts: list[str]):
    return await _emb.embed_sparse(texts)


async def rerank(query: str, docs: list[str], top_n: int = 12):
    return await _emb.rerank(query, docs, top_n)
