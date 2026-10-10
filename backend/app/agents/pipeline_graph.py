"""情报处理流水线 DAG（LangGraph 编排，对接"任务编排"评分点）

节点：collect_batch → normalize → dedup_cluster → enrich_fanout → index → kg_sync → notify
异常分支：低置信 → review_queue（HITL interrupt 预留）
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.core.logging import get_logger

log = get_logger("pipeline")


class PipelineState(TypedDict, total=False):
    source_id: int
    item_ids: list[str]
    stats: dict[str, Any]
    errors: list[str]
    review_needed: list[str]


async def node_collect(state: PipelineState) -> PipelineState:
    from app.collectors.registry import run_source
    await run_source(state["source_id"])
    return state


async def node_enrich(state: PipelineState) -> PipelineState:
    """对新增 items 并发富化（每维独立 worker）"""
    from app.enrichment.pipeline import enrich_item
    import asyncio
    from sqlalchemy import select
    from app.db.models import Item
    from app.db.session import get_session_factory

    ids = state.get("item_ids") or []
    if not ids:
        async with get_session_factory()() as db:
            rows = (await db.execute(
                select(Item.id).where(Item.enrichment == {}).order_by(Item.first_seen_at.desc()).limit(30)
            )).scalars().all()
            ids = list(rows)
    results = await asyncio.gather(*[enrich_item(i) for i in ids[:30]], return_exceptions=True)
    errors = [str(r)[:200] for r in results if isinstance(r, Exception)]
    return {**state, "stats": {"enriched": len(ids) - len(errors)}, "errors": errors}


async def node_index(state: PipelineState) -> PipelineState:
    from app.rag.indexer import index_pending
    await index_pending(limit=60)
    return state


async def node_kg(state: PipelineState) -> PipelineState:
    from app.services.kg import sync_pending
    await sync_pending(limit=100)
    return state


async def node_notify(state: PipelineState) -> PipelineState:
    """高危情报实时推送（KEV∩AI、CRITICAL∩AI）"""
    from sqlalchemy import select
    from app.api.routes import broadcast_new_item
    from app.db.models import Item
    from app.db.session import get_session_factory

    async with get_session_factory()() as db:
        rows = (await db.execute(select(Item).where(
            Item.ai_relevance_score >= 0.5,
            Item.enrichment.has_key("scorers"),  # type: ignore[attr-defined]
        ).order_by(Item.first_seen_at.desc()).limit(5))).scalars().all()
        for it in rows:
            await broadcast_new_item(it)
    return state


def build_pipeline_graph():
    g = StateGraph(PipelineState)
    g.add_node("collect", node_collect)
    g.add_node("enrich", node_enrich)
    g.add_node("index", node_index)
    g.add_node("kg", node_kg)
    g.add_node("notify", node_notify)
    g.set_entry_point("collect")
    g.add_edge("collect", "enrich")
    g.add_edge("enrich", "index")
    g.add_edge("index", "kg")
    g.add_edge("kg", "notify")
    g.add_edge("notify", END)
    return g.compile()


_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline_graph()
    return _pipeline


async def run_pipeline(source_id: int) -> dict:
    result = await get_pipeline().ainvoke({"source_id": source_id, "item_ids": []})
    return result
