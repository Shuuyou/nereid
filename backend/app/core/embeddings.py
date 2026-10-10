"""Embedding / Sparse / Rerank 服务：fastembed ONNX，CPU 运行

- dense:  Qwen3-Embedding-0.6B（可配置 4B）
- sparse: BM42（Qdrant BM25 推断稀疏向量，标识符检索兜底）
- rerank: Qwen3-Reranker-0.6B（若 fastembed 不支持则回退 bge-reranker-v2-m3）
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger("embeddings")

_text_model = None
_sparse_model = None
_rerank_model = None


def _load_dense():
    global _text_model
    if _text_model is None:
        from fastembed import TextEmbedding
        name = get_settings().embedding_model
        try:
            _text_model = TextEmbedding(model_name=name)
        except Exception as e:
            log.warning("dense_model_fallback", wanted=name, error=str(e))
            _text_model = TextEmbedding(model_name="Qwen/Qwen3-Embedding-0.6B")
    return _text_model


def _load_sparse():
    global _sparse_model
    if _sparse_model is None:
        from fastembed import SparseTextEmbedding
        _sparse_model = SparseTextEmbedding(model_name="Qdrant/bm42-all-minilm-l6-v2-attentions")
    return _sparse_model


def _load_reranker():
    global _rerank_model
    if _rerank_model is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        name = get_settings().reranker_model
        for candidate in (name, "Qwen/Qwen3-Reranker-0.6B", "BAAI/bge-reranker-v2-m3", "BAAI/bge-reranker-base"):
            try:
                _rerank_model = TextCrossEncoder(model_name=candidate)
                log.info("reranker_loaded", model=candidate)
                break
            except Exception as e:  # noqa: BLE001
                log.warning("reranker_try_failed", model=candidate, error=str(e)[:120])
        if _rerank_model is None:
            raise RuntimeError("no reranker available")
    return _rerank_model


async def embed_dense(texts: list[str], is_query: bool = False) -> list[list[float]]:
    """dense 向量。query 侧加指令前缀（Qwen3 instruction-aware）"""
    model = _load_dense()
    if is_query:
        texts = [
            "Instruct: Given a security intelligence question, retrieve relevant passages that answer the question\nQuery:" + t
            for t in texts
        ]
    return await asyncio.to_thread(lambda: [v.tolist() for v in model.embed(texts)])


async def embed_sparse(texts: list[str]) -> list[dict[str, Any]]:
    """BM42 稀疏向量 → {indices: [...], values: [...]}"""
    model = _load_sparse()
    return await asyncio.to_thread(
        lambda: [{"indices": v.indices.tolist(), "values": v.values.tolist()} for v in model.embed(texts)]
    )


async def rerank(query: str, documents: list[str], top_n: int = 12) -> list[tuple[int, float]]:
    """交叉编码器重排 → [(doc_index, score)] 降序"""
    if not documents:
        return []
    model = _load_reranker()
    pairs = [(query, d[:2000]) for d in documents]
    scores = await asyncio.to_thread(lambda: list(model.rerank(query, [d for _, d in pairs], batch_size=8)))
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return ranked[:top_n]


def warmup() -> None:
    """启动预热：加载三个模型（避免首次请求卡顿）"""
    _load_dense()
    _load_sparse()
    _load_reranker()
    log.info("embeddings_warmup_done")
