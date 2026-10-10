#!/usr/bin/env python3
"""批量运维入口（具名进程，便于 ps/kill）
用法: PYTHONPATH=backend python3 scripts/batch_ops.py [enrich|index|kg] [limit]
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


async def enrich(limit: int = 500) -> None:
    from sqlalchemy import or_, select
    from app.db.models import Item
    from app.db.session import get_session_factory
    from app.enrichment.pipeline import enrich_item
    async with get_session_factory()() as db:
        items = (await db.execute(select(Item).where(
            or_(Item.ai_relevance_score >= 0.3, Item.is_kev.is_(True), Item.priority_score >= 1.5),
            Item.enrichment == {}
        ).order_by(Item.priority_score.desc().nullslast()).limit(limit))).scalars().all()
        ids = [i.id for i in items]
    print("to enrich:", len(ids), flush=True)
    done = err = 0
    for iid in ids:
        try:
            await enrich_item(iid)
            done += 1
        except Exception as e:  # noqa: BLE001
            err += 1
            print("ERR", iid[:8], str(e)[:80], flush=True)
        if done % 10 == 0:
            print(f"progress {done}/{len(ids)}", flush=True)
    print("enrich done", done, "errors", err)


async def index(limit: int = 700) -> None:
    from app.rag.indexer import index_pending
    n = await index_pending(limit=limit)
    print("indexed:", n)


async def kg(limit: int = 700) -> None:
    from app.services.kg import sync_pending
    n = await sync_pending(limit=limit)
    print("kg synced:", n)


if __name__ == "__main__":
    op = sys.argv[1] if len(sys.argv) > 1 else "enrich"
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    asyncio.run({"enrich": enrich, "index": index, "kg": kg}[op](lim))
