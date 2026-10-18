#!/usr/bin/env python3
"""存量富化回填：按优先级并发富化未覆盖 item，断点可续

- 排序口径与 pipeline.enrich_pending 一致：
  is_kev DESC → item_type='vuln' 优先 → priority_score DESC NULLS LAST → first_seen_at DESC
- 并发：asyncio.gather + Semaphore(4)（worker 为 IO-bound：LLM/HTTP/DB，单 item ~10-40s）
- 断点可续：完成判据 = enrichment 含 "scorers" 键，重跑自动跳过已完成条目；
  中断残留的 extra._enrich_lock 由 enrich_item 按 15min 过期窃取，天然可续
- 进度：每 50 条打一行 + 末尾汇总

用法: cd backend && .venv/bin/python ../scripts/enrich_backfill.py [--limit 500] [--type vuln]
退出码: 0=正常  1=库不可用等致命错误
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

CONCURRENCY = 4       # Semaphore 并发度（与 enrich_pending 一致）
PROGRESS_EVERY = 50   # 进度打印间隔


def _prio_order(Item):
    """与 enrich_pending 相同的优先级 ORDER BY 列"""
    return (
        Item.is_kev.desc(),
        (Item.item_type == "vuln").desc(),
        Item.priority_score.desc().nullslast(),
        Item.first_seen_at.desc(),
    )


async def backfill(limit: int, item_type: str | None) -> int:
    from sqlalchemy import func, select
    from app.db.models import Item
    from app.db.session import get_session_factory
    from app.enrichment.pipeline import enrich_item

    sf = get_session_factory()
    async with sf() as db:
        cond = [~Item.enrichment.has_key("scorers")]
        if item_type:
            cond.append(Item.item_type == item_type)
        pending = (await db.execute(
            select(func.count()).select_from(Item).where(*cond))).scalar_one()
        ids = (await db.execute(
            select(Item.id).where(*cond)
            .order_by(*_prio_order(Item)).limit(limit))).scalars().all()

    if not ids:
        print("[backfill] 无待富化条目（完成判据=enrichment 含 scorers 键）")
        return 0
    print(f"[backfill] 待富化≈{pending}，本轮取 {len(ids)} 条"
          f"（type={item_type or '全部'}，并发={CONCURRENCY}，断点可续）", flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    t0 = time.monotonic()
    stats = {"done": 0, "ok": 0, "skipped": 0, "err": 0}

    async def one(iid: str) -> None:
        async with sem:
            try:
                res = await enrich_item(iid)
                if res.get("skipped"):
                    stats["skipped"] += 1   # 他进程持锁，留待下轮窃取
                else:
                    stats["ok"] += 1
            except Exception as e:  # noqa: BLE001
                stats["err"] += 1
                print(f"[backfill] ERR {iid[:8]} {str(e)[:100]}", flush=True)
            stats["done"] += 1
            if stats["done"] % PROGRESS_EVERY == 0 or stats["done"] == len(ids):
                el = time.monotonic() - t0
                rate = stats["done"] / el if el > 0 else 0
                print(f"[backfill] {stats['done']}/{len(ids)} "
                      f"ok={stats['ok']} skip={stats['skipped']} err={stats['err']} "
                      f"elapsed={el:.0f}s rate={rate:.2f}/s", flush=True)

    await asyncio.gather(*[one(i) for i in ids])
    el = time.monotonic() - t0
    print(f"[backfill] 完成：处理={stats['done']} 富化={stats['ok']} "
          f"锁跳过={stats['skipped']} 失败={stats['err']} 耗时={el:.0f}s；"
          f"剩余待富化≈{max(pending - stats['ok'], 0)}（重跑本脚本即可续）", flush=True)
    return 0


async def _cleanup() -> None:
    """释放 DB 连接池与 httpx client，避免事件循环关闭告警"""
    try:
        from app.db.session import get_engine
        await get_engine().dispose()
    except Exception:  # noqa: BLE001
        pass
    try:
        import app.core.http as http_mod
        if http_mod._client is not None:
            await http_mod._client.aclose()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="存量富化回填（并发+优先级+断点续跑）")
    ap.add_argument("--limit", type=int, default=500, help="本轮最多处理条数（默认 500）")
    ap.add_argument("--type", dest="item_type", default=None,
                    help="只处理指定 item_type（如 vuln/exploit；默认全部）")
    a = ap.parse_args()

    async def _run() -> int:
        try:
            return await backfill(a.limit, a.item_type)
        finally:
            await _cleanup()   # 必须在同一事件循环内释放连接
    try:
        code = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001 —— 库连接失败等致命错误
        print(f"[backfill] 致命错误: {e}")
        code = 1
    sys.exit(code)
