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
    """采集节点：run_source 返回本轮新增 item_id 列表 → 流入下游 enrich"""
    from app.collectors.registry import run_source
    stats = await run_source(state["source_id"]) or {}
    new_ids = stats.get("item_ids") or []
    return {**state, "item_ids": new_ids,
            "stats": {**state.get("stats", {}), "collected": stats.get("new", 0)}}


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
                select(Item.id).where(~Item.enrichment.has_key("scorers")).order_by(Item.first_seen_at.desc()).limit(30)
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
        from sqlalchemy import or_, and_
        cond = and_(Item.ai_relevance_score >= 0.5,
                    or_(Item.is_kev.is_(True), Item.severity == "critical"))
        q = select(Item).where(cond)
        if state.get("item_ids"):
            q = q.where(Item.id.in_(state["item_ids"]))
        rows = (await db.execute(q.order_by(Item.first_seen_at.desc()).limit(10))).scalars().all()
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


NODES_ORDER = ["collect", "enrich", "index", "kg", "notify"]


async def run_pipeline(source_id: int) -> dict:
    result = await get_pipeline().ainvoke({"source_id": source_id, "item_ids": []})
    return result


async def run_pipeline_tracked(source_id: int, run_id: str | None = None) -> dict:
    """带实时状态的 DAG 执行：astream 逐节点回写 Redis（前端轮询真实状态，非前端定时器动画）"""
    import json as _j
    import uuid as _u
    from datetime import datetime, timezone
    from app.core.rds import rds

    run_id = run_id or _u.uuid4().hex[:12]
    key = f"pipeline:run:{run_id}"
    now = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731
    try:
        await rds().hset(key, mapping={
            "run_id": run_id, "source_id": str(source_id), "status": "running",
            "started_at": now(), "nodes": _j.dumps({n: "pending" for n in NODES_ORDER})})
        await rds().expire(key, 86400)
        await rds().lpush("pipeline:runs", run_id)
        await rds().ltrim("pipeline:runs", 0, 99)
        nodes: dict[str, str] = {}
        result: dict = {}
        async for upd in get_pipeline().astream(
                {"source_id": source_id, "item_ids": []}, stream_mode="updates"):
            for node, st in upd.items():
                nodes[node] = "done"
                result = {**result, **(st or {})}
                if isinstance(st, dict) and st.get("stats"):
                    result.setdefault("stats", {}).update(st["stats"])
                await rds().hset(key, mapping={
                    "nodes": _j.dumps({**{n: "pending" for n in NODES_ORDER}, **nodes}),
                    "current": node})
        await rds().hset(key, mapping={"status": "done", "finished_at": now(),
                                       "result": _j.dumps(result, default=str)[:4000]})
        try:
            from app.db.session import get_session_factory
            from app.db.models import TaskRun
            async with get_session_factory()() as db:
                db.add(TaskRun(task_name=f"pipeline:{source_id}", status="success",
                               detail={"run_id": run_id, "stats": result.get("stats")}))
                await db.commit()
        except Exception:  # noqa: BLE001
            pass
        return {"run_id": run_id, "status": "done", "result": result}
    except Exception as e:  # noqa: BLE001
        await rds().hset(key, mapping={"status": "error", "finished_at": now(),
                                       "error": str(e)[:400]})
        return {"run_id": run_id, "status": "error", "error": str(e)[:400]}
